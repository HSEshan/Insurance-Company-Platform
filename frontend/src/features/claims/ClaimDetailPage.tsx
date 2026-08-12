import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, getErrorMessage } from "../../lib/api";
import {
  Alert,
  Badge,
  Button,
  Card,
  Field,
  Input,
  Select,
} from "../../components/ui";
import { DocumentsCard } from "../documents/DocumentsCard";
import { useAuthStore } from "../../stores/authStore";
import type { Claim, Envelope, User } from "../../types";
import { formatMoney } from "../../types";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-3 gap-2 border-b border-slate-100 py-2 text-sm last:border-0">
      <dt className="text-slate-500">{label}</dt>
      <dd className="col-span-2 text-slate-800">{children}</dd>
    </div>
  );
}

const LIFECYCLE: Claim["status"][] = [
  "submitted",
  "assigned",
  "investigating",
  "approved",
  "paid",
  "closed",
];

/** Alternate happy-path index when claim took reject/dispute branches. */
function lifecycleIndex(status: Claim["status"]): number {
  const map: Partial<Record<Claim["status"], number>> = {
    submitted: 0,
    assigned: 1,
    investigating: 2,
    info_requested: 2,
    approved: 3,
    rejected: 3,
    disputed: 3,
    paid: 4,
    closed: 5,
  };
  return map[status] ?? 0;
}

function ClaimLifecycleStrip({ status }: { status: Claim["status"] }) {
  const current = lifecycleIndex(status);
  return (
    <Card className="overflow-x-auto">
      <ol className="flex min-w-max gap-1">
        {LIFECYCLE.map((step, i) => {
          const done = i < current;
          const active = i === current;
          return (
            <li
              key={step}
              className={`rounded-lg px-3 py-2 text-xs font-medium capitalize ${
                active
                  ? "bg-indigo-600 text-white"
                  : done
                    ? "bg-indigo-50 text-indigo-700"
                    : "bg-slate-50 text-slate-400"
              }`}
            >
              {step.replace(/_/g, " ")}
              {status === "info_requested" && step === "investigating"
                ? " (info)"
                : ""}
              {status === "rejected" && step === "approved" ? " / rejected" : ""}
              {status === "disputed" && step === "approved" ? " / disputed" : ""}
            </li>
          );
        })}
      </ol>
    </Card>
  );
}

export function ClaimDetailPage() {
  const { id } = useParams<{ id: string }>();
  const role = useAuthStore((s) => s.user?.role);
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [approveAmount, setApproveAmount] = useState("");
  const [rejectReason, setRejectReason] = useState("");
  const [noteBody, setNoteBody] = useState("");
  const [adjusterId, setAdjusterId] = useState("");
  const [disputeReason, setDisputeReason] = useState("");

  const isCustomer = role === "customer";
  const isAdjusterUp =
    role === "adjuster" || role === "manager" || role === "super_admin";
  const isManagerUp = role === "manager" || role === "super_admin";

  const { data: claim, isLoading, isError } = useQuery({
    queryKey: ["claim", id],
    enabled: !!id,
    queryFn: async () => {
      const res = await api.get<Envelope<Claim>>(`/claims/${id}`);
      return res.data.data!;
    },
  });

  const { data: adjusters } = useQuery({
    queryKey: ["adjusters"],
    enabled: isManagerUp,
    queryFn: async () => {
      const res = await api.get<Envelope<User[]>>("/claims/adjusters");
      return res.data.data ?? [];
    },
  });

  const invalidate = async () => {
    await qc.invalidateQueries({ queryKey: ["claim", id] });
    await qc.invalidateQueries({ queryKey: ["claims"] });
  };

  const run = useMutation({
    mutationFn: async ({
      path,
      body,
    }: {
      path: string;
      body?: Record<string, unknown>;
    }) => {
      setError(null);
      await api.post(`/claims/${id}${path}`, body);
    },
    onSuccess: invalidate,
    onError: (err) => setError(getErrorMessage(err, "Action failed.")),
  });

  if (isLoading) return <p className="text-slate-500">Loading claim…</p>;
  if (isError || !claim)
    return <p className="text-red-600">Failed to load claim.</p>;

  const openStatuses = ["assigned", "investigating", "info_requested"];

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm text-slate-500">
            <Link to="/claims" className="text-indigo-600 hover:underline">
              Claims
            </Link>{" "}
            / {claim.claim_number}
          </p>
          <h2 className="mt-1 text-2xl font-bold text-slate-800">
            {claim.claim_number}
          </h2>
        </div>
        <div className="flex items-center gap-2">
          {claim.fraud_flag && (
            <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-semibold text-red-700">
              Fraud flag
            </span>
          )}
          <Badge value={claim.status} />
        </div>
      </div>

      {error && <Alert message={error} />}

      <ClaimLifecycleStrip status={claim.status} />

      <Card>
        <dl>
          <Row label="Type">
            <span className="capitalize">
              {claim.claim_type.replace(/_/g, " ")}
            </span>
          </Row>
          <Row label="Incident">{claim.incident_date}</Row>
          <Row label="Reported">{claim.reported_date}</Row>
          <Row label="Location">{claim.incident_location ?? "—"}</Row>
          <Row label="Estimate">{formatMoney(claim.estimated_damage)}</Row>
          <Row label="Approved">{formatMoney(claim.approved_amount)}</Row>
          <Row label="Payout">{formatMoney(claim.final_payout)}</Row>
          <Row label="Fraud score">
            {claim.fraud_score != null ? String(claim.fraud_score) : "—"}
          </Row>
          <Row label="Policy">
            <Link
              to={`/policies/${claim.policy_id}`}
              className="text-indigo-600 hover:underline"
            >
              View policy
            </Link>
          </Row>
          <Row label="Description">{claim.description}</Row>
        </dl>
      </Card>

      <DocumentsCard ownerType="claim" ownerId={claim.id} />

      <Card>
        <h3 className="mb-3 text-sm font-semibold text-slate-800">Timeline / notes</h3>
        {claim.notes.length === 0 && (
          <p className="text-sm text-slate-500">No notes yet.</p>
        )}
        <ul className="space-y-3">
          {claim.notes.map((n) => (
            <li key={n.id} className="border-b border-slate-100 pb-3 text-sm last:border-0">
              <div className="flex justify-between text-xs text-slate-500">
                <span className="capitalize">{n.note_type.replace(/_/g, " ")}</span>
                <span>{new Date(n.created_at).toLocaleString()}</span>
              </div>
              <p className="mt-1 text-slate-800">{n.body}</p>
            </li>
          ))}
        </ul>
      </Card>

      {isManagerUp && claim.status === "submitted" && (
        <Card className="space-y-3">
          <h3 className="text-sm font-semibold text-slate-800">Assign adjuster</h3>
          <Field label="Adjuster" htmlFor="adj">
            <Select
              id="adj"
              value={adjusterId}
              onChange={(e) => setAdjusterId(e.target.value)}
            >
              <option value="">Select adjuster…</option>
              {adjusters?.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.first_name} {a.last_name} ({a.email})
                </option>
              ))}
            </Select>
          </Field>
          <Button
            loading={run.isPending}
            disabled={!adjusterId}
            onClick={() =>
              run.mutate({ path: "/assign", body: { adjuster_id: adjusterId } })
            }
          >
            Assign
          </Button>
        </Card>
      )}

      {isAdjusterUp && openStatuses.includes(claim.status) && (
        <Card className="space-y-4">
          <h3 className="text-sm font-semibold text-slate-800">Adjuster actions</h3>
          <div className="flex flex-wrap gap-2">
            {(claim.status === "assigned" ||
              claim.status === "info_requested") && (
              <Button
                variant="secondary"
                loading={run.isPending}
                onClick={() => run.mutate({ path: "/investigate" })}
              >
                Start investigation
              </Button>
            )}
            <Button
              variant="secondary"
              loading={run.isPending}
              onClick={() => {
                const reason = window.prompt("Message to customer?");
                if (reason)
                  run.mutate({ path: "/request-info", body: { reason } });
              }}
            >
              Request info
            </Button>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Approve amount" htmlFor="amt">
              <Input
                id="amt"
                value={approveAmount}
                onChange={(e) => setApproveAmount(e.target.value)}
              />
            </Field>
            <div className="flex items-end">
              <Button
                loading={run.isPending}
                disabled={!approveAmount}
                onClick={() =>
                  run.mutate({
                    path: "/approve",
                    body: { approved_amount: approveAmount },
                  })
                }
              >
                Approve
              </Button>
            </div>
            <Field label="Reject reason" htmlFor="rej">
              <Input
                id="rej"
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
              />
            </Field>
            <div className="flex items-end">
              <Button
                variant="danger"
                loading={run.isPending}
                disabled={!rejectReason}
                onClick={() =>
                  run.mutate({
                    path: "/reject",
                    body: { reason: rejectReason },
                  })
                }
              >
                Reject
              </Button>
            </div>
          </div>
          <Field label="Add note" htmlFor="note">
            <Input
              id="note"
              value={noteBody}
              onChange={(e) => setNoteBody(e.target.value)}
            />
          </Field>
          <Button
            variant="secondary"
            loading={run.isPending}
            disabled={!noteBody.trim()}
            onClick={() =>
              run.mutate({
                path: "/notes",
                body: {
                  body: noteBody,
                  note_type: "investigation",
                  is_visible_to_customer: false,
                },
              })
            }
          >
            Save note
          </Button>
        </Card>
      )}

      {isCustomer && claim.status === "rejected" && (
        <Card className="space-y-3">
          <h3 className="text-sm font-semibold text-slate-800">Dispute</h3>
          <Field label="Reason" htmlFor="disp">
            <Input
              id="disp"
              value={disputeReason}
              onChange={(e) => setDisputeReason(e.target.value)}
            />
          </Field>
          <Button
            loading={run.isPending}
            disabled={!disputeReason.trim()}
            onClick={() =>
              run.mutate({
                path: "/dispute",
                body: { reason: disputeReason },
              })
            }
          >
            Dispute rejection
          </Button>
        </Card>
      )}

      {isManagerUp && claim.status === "disputed" && (
        <Card className="flex flex-wrap gap-2">
          <Button
            variant="danger"
            loading={run.isPending}
            onClick={() =>
              run.mutate({
                path: "/resolve-dispute",
                body: { uphold_rejection: true },
              })
            }
          >
            Uphold rejection
          </Button>
          <Button
            loading={run.isPending}
            onClick={() => {
              const amt = window.prompt("Approved amount?");
              if (amt)
                run.mutate({
                  path: "/resolve-dispute",
                  body: { uphold_rejection: false, approved_amount: amt },
                });
            }}
          >
            Overturn → approve
          </Button>
        </Card>
      )}

      {isManagerUp && claim.status === "approved" && (
        <Card>
          <Button
            loading={run.isPending}
            onClick={() => run.mutate({ path: "/pay" })}
          >
            Record payout
          </Button>
        </Card>
      )}

      {(isAdjusterUp || role === "agent") &&
        (claim.status === "paid" || claim.status === "rejected") && (
          <Card>
            <Button
              variant="secondary"
              loading={run.isPending}
              onClick={() => run.mutate({ path: "/close" })}
            >
              Close claim
            </Button>
          </Card>
        )}
    </div>
  );
}
