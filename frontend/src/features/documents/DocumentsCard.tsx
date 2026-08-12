import { useRef, useState } from "react";
import axios from "axios";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, getErrorMessage } from "../../lib/api";
import { Alert, Button, Card, Field, Select } from "../../components/ui";
import { useAuthStore } from "../../stores/authStore";
import type {
  DocumentDownload,
  DocumentOwnerType,
  DocumentPresign,
  DocumentRecord,
  DocumentType,
  Envelope,
} from "../../types";
import { formatFileSize } from "../../types";

const MAX_UPLOAD_BYTES = 25 * 1024 * 1024;

// Mirrors the server-side whitelist in document_service._ALLOWED_MIME_TYPES.
const ACCEPTED_MIME_TYPES = [
  "image/jpeg",
  "image/png",
  "image/webp",
  "image/heic",
  "image/tiff",
  "application/pdf",
  "text/plain",
];

const DOCUMENT_TYPE_LABELS: Record<DocumentType, string> = {
  policy_pdf: "Declaration page",
  claim_decision_letter: "Decision letter",
  id_document: "ID document",
  vehicle_photo: "Vehicle photo",
  property_photo: "Property photo",
  police_report: "Police report",
  medical_report: "Medical report",
  repair_estimate: "Repair estimate",
  proof_of_ownership: "Proof of ownership",
  receipt: "Receipt",
  other: "Other",
};

/** Only offer the document types that make sense for what we're attached to.
 *  System-generated types (declaration pages, decision letters) are omitted:
 *  the carrier issues those, users do not upload them. */
const TYPES_BY_OWNER: Record<DocumentOwnerType, DocumentType[]> = {
  claim: [
    "vehicle_photo",
    "property_photo",
    "police_report",
    "repair_estimate",
    "medical_report",
    "proof_of_ownership",
    "receipt",
    "other",
  ],
  policy: ["proof_of_ownership", "receipt", "other"],
  customer: ["id_document", "proof_of_ownership", "other"],
  quote: ["id_document", "vehicle_photo", "property_photo", "other"],
};

async function sha256Hex(file: File): Promise<string | undefined> {
  // crypto.subtle needs a secure context; skip the checksum rather than fail
  // the upload if the app is served over plain HTTP from a non-localhost host.
  if (!crypto?.subtle) return undefined;
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

interface DocumentsCardProps {
  ownerType: DocumentOwnerType;
  ownerId: string;
  title?: string;
  /** Hide the upload form on read-only views. */
  canUpload?: boolean;
}

export function DocumentsCard({
  ownerType,
  ownerId,
  title = "Documents",
  canUpload = true,
}: DocumentsCardProps) {
  const role = useAuthStore((s) => s.user?.role);
  const qc = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [documentType, setDocumentType] = useState<DocumentType>(
    TYPES_BY_OWNER[ownerType][0],
  );

  const canVerify =
    role === "agent" ||
    role === "adjuster" ||
    role === "manager" ||
    role === "super_admin";
  const canDelete =
    role === "agent" || role === "manager" || role === "super_admin";
  const isManagerUp = role === "manager" || role === "super_admin";

  const queryKey = ["documents", ownerType, ownerId];

  const { data: documents, isLoading } = useQuery({
    queryKey,
    enabled: !!ownerId,
    queryFn: async () => {
      const res = await api.get<Envelope<DocumentRecord[]>>("/documents", {
        params: { owner_type: ownerType, owner_id: ownerId },
      });
      return res.data.data ?? [];
    },
  });

  const invalidate = () => qc.invalidateQueries({ queryKey });

  const upload = useMutation({
    mutationFn: async (file: File) => {
      setError(null);
      const presign = await api.post<Envelope<DocumentPresign>>(
        "/documents/presign-upload",
        {
          owner_type: ownerType,
          owner_id: ownerId,
          document_type: documentType,
          file_name: file.name,
          mime_type: file.type,
          file_size_bytes: file.size,
        },
      );
      const slot = presign.data.data!;

      // Send the bytes straight to object storage. This deliberately uses a
      // bare axios call: our api instance attaches an Authorization header,
      // which would invalidate the presigned URL's query-string signature.
      await axios.put(slot.upload_url, file, {
        headers: { "Content-Type": file.type },
      });

      await api.post<Envelope<DocumentRecord>>("/documents", {
        owner_type: ownerType,
        owner_id: ownerId,
        document_type: documentType,
        file_name: file.name,
        mime_type: file.type,
        storage_bucket: slot.storage_bucket,
        storage_key: slot.storage_key,
        file_size_bytes: file.size,
        checksum_sha256: await sha256Hex(file),
      });
    },
    onSuccess: () => {
      if (fileInputRef.current) fileInputRef.current.value = "";
      return invalidate();
    },
    onError: (err) => setError(getErrorMessage(err, "Upload failed.")),
  });

  const download = useMutation({
    mutationFn: async (documentId: string) => {
      setError(null);
      const res = await api.get<Envelope<DocumentDownload>>(
        `/documents/${documentId}/download`,
      );
      window.open(res.data.data!.download_url, "_blank", "noopener");
    },
    onError: (err) => setError(getErrorMessage(err, "Could not open file.")),
  });

  const verify = useMutation({
    mutationFn: async (documentId: string) => {
      setError(null);
      await api.post(`/documents/${documentId}/verify`);
    },
    onSuccess: invalidate,
    onError: (err) => setError(getErrorMessage(err, "Verification failed.")),
  });

  const remove = useMutation({
    mutationFn: async (documentId: string) => {
      setError(null);
      await api.delete(`/documents/${documentId}`);
    },
    onSuccess: invalidate,
    onError: (err) => setError(getErrorMessage(err, "Delete failed.")),
  });

  const handleFile = (file: File | undefined) => {
    if (!file) return;
    if (file.size > MAX_UPLOAD_BYTES) {
      setError("File exceeds the 25 MB upload limit.");
      return;
    }
    if (!ACCEPTED_MIME_TYPES.includes(file.type)) {
      setError("Only images, PDFs, and text files can be uploaded.");
      return;
    }
    upload.mutate(file);
  };

  return (
    <Card className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
        <span className="text-xs text-slate-500">
          {documents?.length ?? 0} file{documents?.length === 1 ? "" : "s"}
        </span>
      </div>

      {error && <Alert message={error} />}

      {isLoading ? (
        <p className="text-sm text-slate-500">Loading documents…</p>
      ) : documents && documents.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase text-slate-500">
              <tr className="border-b border-slate-200">
                <th className="py-2 pr-3 font-medium">File</th>
                <th className="py-2 pr-3 font-medium">Type</th>
                <th className="py-2 pr-3 font-medium">Size</th>
                <th className="py-2 pr-3 font-medium">Uploaded</th>
                <th className="py-2 pr-3 font-medium">Status</th>
                <th className="py-2 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((doc) => (
                <tr key={doc.id} className="border-b border-slate-100 last:border-0">
                  <td className="max-w-56 truncate py-2 pr-3 text-slate-800">
                    {doc.file_name}
                  </td>
                  <td className="py-2 pr-3 text-slate-600">
                    {DOCUMENT_TYPE_LABELS[doc.document_type]}
                  </td>
                  <td className="py-2 pr-3 text-slate-600">
                    {formatFileSize(doc.file_size_bytes)}
                  </td>
                  <td className="py-2 pr-3 text-slate-600">
                    {new Date(doc.created_at).toLocaleDateString()}
                  </td>
                  <td className="py-2 pr-3">
                    {doc.is_verified ? (
                      <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700">
                        Verified
                      </span>
                    ) : (
                      <span className="text-xs text-slate-400">Unverified</span>
                    )}
                  </td>
                  <td className="py-2">
                    <div className="flex flex-wrap gap-1">
                      <Button
                        variant="ghost"
                        className="px-2 py-1 text-xs"
                        loading={
                          download.isPending && download.variables === doc.id
                        }
                        onClick={() => download.mutate(doc.id)}
                      >
                        Download
                      </Button>
                      {canVerify && !doc.is_verified && (
                        <Button
                          variant="ghost"
                          className="px-2 py-1 text-xs"
                          loading={verify.isPending && verify.variables === doc.id}
                          onClick={() => verify.mutate(doc.id)}
                        >
                          Verify
                        </Button>
                      )}
                      {canDelete && (!doc.is_verified || isManagerUp) && (
                        <Button
                          variant="ghost"
                          className="px-2 py-1 text-xs text-red-600 hover:bg-red-50"
                          loading={remove.isPending && remove.variables === doc.id}
                          onClick={() => {
                            if (
                              window.confirm(`Delete "${doc.file_name}"?`)
                            )
                              remove.mutate(doc.id);
                          }}
                        >
                          Delete
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-sm text-slate-500">No documents attached yet.</p>
      )}

      {canUpload && (
        <div className="grid gap-3 border-t border-slate-100 pt-4 sm:grid-cols-2">
          <Field label="Document type" htmlFor={`doctype-${ownerId}`}>
            <Select
              id={`doctype-${ownerId}`}
              value={documentType}
              onChange={(e) => setDocumentType(e.target.value as DocumentType)}
            >
              {TYPES_BY_OWNER[ownerType].map((t) => (
                <option key={t} value={t}>
                  {DOCUMENT_TYPE_LABELS[t]}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="File" htmlFor={`file-${ownerId}`}>
            <input
              id={`file-${ownerId}`}
              ref={fileInputRef}
              type="file"
              accept={ACCEPTED_MIME_TYPES.join(",")}
              disabled={upload.isPending}
              onChange={(e) => handleFile(e.target.files?.[0])}
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm file:mr-3 file:rounded file:border-0 file:bg-slate-100 file:px-2 file:py-1 file:text-sm file:text-slate-700 disabled:opacity-60"
            />
          </Field>
          <p className="text-xs text-slate-500 sm:col-span-2">
            {upload.isPending
              ? "Uploading…"
              : "Images, PDFs, and text files up to 25 MB. Uploads go directly to secure storage."}
          </p>
        </div>
      )}
    </Card>
  );
}
