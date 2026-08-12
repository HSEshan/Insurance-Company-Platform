import { useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { api, getErrorMessage } from "../../lib/api";
import { Button, Card, Input, Select } from "../../components/ui";
import type { AuditLog, Envelope, Meta } from "../../types";

const PER_PAGE = 25;

const ENTITY_TYPES = [
  "user",
  "customer",
  "quote",
  "policy",
  "claim",
  "payment",
  "document",
  "endorsement",
];

export function AuditPage() {
  const [page, setPage] = useState(1);
  const [entityType, setEntityType] = useState("");
  const [action, setAction] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [exportError, setExportError] = useState<string | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["audit", { page, entityType, action, dateFrom, dateTo }],
    placeholderData: keepPreviousData,
    queryFn: async () => {
      const res = await api.get<Envelope<AuditLog[]>>("/audit", {
        params: {
          page,
          per_page: PER_PAGE,
          entity_type: entityType || undefined,
          action: action || undefined,
          date_from: dateFrom ? new Date(dateFrom).toISOString() : undefined,
          date_to: dateTo ? new Date(`${dateTo}T23:59:59`).toISOString() : undefined,
        },
      });
      return {
        items: res.data.data ?? [],
        meta: res.data.meta ?? (null as Meta | null),
      };
    },
  });

  const total = data?.meta?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PER_PAGE));

  async function handleExport() {
    setExportError(null);
    try {
      const res = await api.get("/audit/export", {
        params: {
          entity_type: entityType || undefined,
          action: action || undefined,
          date_from: dateFrom ? new Date(dateFrom).toISOString() : undefined,
          date_to: dateTo ? new Date(`${dateTo}T23:59:59`).toISOString() : undefined,
        },
        responseType: "blob",
      });
      const url = URL.createObjectURL(res.data as Blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "audit-log-export.csv";
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      setExportError(getErrorMessage(error));
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">Audit log</h2>
          <p className="mt-1 text-sm text-slate-500">
            Append-only trail of privileged writes and authentication events.
          </p>
        </div>
        <Button variant="secondary" onClick={handleExport}>
          <Download className="h-4 w-4" />
          Export CSV
        </Button>
      </div>

      {exportError && (
        <p className="text-sm text-red-600">{exportError}</p>
      )}

      <div className="flex flex-wrap gap-3">
        <Select
          value={entityType}
          onChange={(e) => {
            setEntityType(e.target.value);
            setPage(1);
          }}
          className="w-44"
        >
          <option value="">All entities</option>
          {ENTITY_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </Select>
        <Input
          placeholder="Action prefix (e.g. claim.)"
          value={action}
          onChange={(e) => {
            setAction(e.target.value);
            setPage(1);
          }}
          className="w-56"
        />
        <Input
          type="date"
          value={dateFrom}
          onChange={(e) => {
            setDateFrom(e.target.value);
            setPage(1);
          }}
          className="w-40"
        />
        <Input
          type="date"
          value={dateTo}
          onChange={(e) => {
            setDateTo(e.target.value);
            setPage(1);
          }}
          className="w-40"
        />
      </div>

      <Card className="p-0">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3">When</th>
              <th className="px-4 py-3">Actor</th>
              <th className="px-4 py-3">Action</th>
              <th className="px-4 py-3">Entity</th>
              <th className="px-4 py-3">Change</th>
              <th className="px-4 py-3">IP</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {isLoading && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-slate-500">
                  Loading…
                </td>
              </tr>
            )}
            {isError && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-red-600">
                  Could not load audit log.
                </td>
              </tr>
            )}
            {!isLoading && !isError && (data?.items.length ?? 0) === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-slate-500">
                  No audit entries match these filters.
                </td>
              </tr>
            )}
            {data?.items.map((row) => (
              <tr key={row.id} className="hover:bg-slate-50">
                <td className="whitespace-nowrap px-4 py-3 text-slate-600">
                  {new Date(row.created_at).toLocaleString()}
                </td>
                <td className="px-4 py-3">
                  <div className="font-medium text-slate-800">
                    {row.actor_name || row.actor_email || "—"}
                  </div>
                  <div className="text-xs capitalize text-slate-500">
                    {row.actor_role?.replace(/_/g, " ") || "anonymous"}
                  </div>
                </td>
                <td className="px-4 py-3 font-mono text-xs text-indigo-700">
                  {row.action}
                </td>
                <td className="px-4 py-3">
                  <div className="text-slate-800">{row.entity_type}</div>
                  <div className="font-mono text-xs text-slate-400">
                    {row.entity_id.slice(0, 8)}…
                  </div>
                </td>
                <td className="max-w-xs truncate px-4 py-3 font-mono text-xs text-slate-600">
                  {summarizeChange(row)}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-slate-500">
                  {row.ip_address || "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <div className="flex items-center justify-between text-sm text-slate-600">
        <span>
          {total} entr{total === 1 ? "y" : "ies"}
        </span>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            Previous
          </Button>
          <span>
            Page {page} of {totalPages}
          </span>
          <Button
            variant="secondary"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
          >
            Next
          </Button>
        </div>
      </div>
    </div>
  );
}

function summarizeChange(row: AuditLog): string {
  const parts: string[] = [];
  if (row.old_value?.status != null) {
    parts.push(`${String(row.old_value.status)} →`);
  }
  if (row.new_value?.status != null) {
    parts.push(String(row.new_value.status));
  } else if (row.new_value) {
    const keys = Object.keys(row.new_value).slice(0, 3);
    parts.push(keys.map((k) => `${k}=${String(row.new_value![k])}`).join(", "));
  }
  return parts.join(" ") || "—";
}
