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
import { BillingCard } from "../payments/BillingCard";
import { useAuthStore } from "../../stores/authStore";
import type {
  Endorsement,
  EndorsementType,
  Envelope,
  Policy,
} from "../../types";
import { formatMoney } from "../../types";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-3 gap-2 border-b border-slate-100 py-2 text-sm last:border-0">
      <dt className="text-slate-500">{label}</dt>
      <dd className="col-span-2 text-slate-800">{children}</dd>
    </div>
  );
}

const ENDORSEMENT_TYPES: EndorsementType[] = [
  "coverage_change",
  "address_change",
  "deductible_change",
  "limits_change",
  "add_vehicle",
  "remove_vehicle",
  "beneficiary_change",
  "other",
];

export function PolicyDetailPage() {
  const { id } = useParams<{ id: string }>();
  const role = useAuthStore((s) => s.user?.role);
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [cancelReason, setCancelReason] = useState("");
  const [showCancel, setShowCancel] = useState(false);

  const [endType, setEndType] = useState<EndorsementType>("coverage_change");
  const [endDate, setEndDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [endDesc, setEndDesc] = useState("");
  const [endImpact, setEndImpact] = useState("0");

  const isAgentUp =
    role === "agent" || role === "manager" || role === "super_admin";
  const isManagerUp = role === "manager" || role === "super_admin";

  const { data: policy, isLoading, isError } = useQuery({
    queryKey: ["policy", id],
    enabled: !!id,
    queryFn: async () => {
      const res = await api.get<Envelope<Policy>>(`/policies/${id}`);
      return res.data.data!;
    },
  });

  const { data: endorsements } = useQuery({
    queryKey: ["endorsements", id],
    enabled: !!id,
    queryFn: async () => {
      const res = await api.get<Envelope<Endorsement[]>>(
        `/policies/${id}/endorsements`,
      );
      return res.data.data ?? [];
    },
  });

  const invalidate = async () => {
    await qc.invalidateQueries({ queryKey: ["policy", id] });
    await qc.invalidateQueries({ queryKey: ["endorsements", id] });
    await qc.invalidateQueries({ queryKey: ["policies"] });
  };

  const cancelMut = useMutation({
    mutationFn: async () => {
      setError(null);
      await api.post(`/policies/${id}/cancel`, { reason: cancelReason });
    },
    onSuccess: invalidate,
    onError: (err) => setError(getErrorMessage(err, "Cancel failed.")),
  });

  const reinstateMut = useMutation({
    mutationFn: async () => {
      setError(null);
      await api.post(`/policies/${id}/reinstate`);
    },
    onSuccess: invalidate,
    onError: (err) => setError(getErrorMessage(err, "Reinstate failed.")),
  });

  const createEnd = useMutation({
    mutationFn: async () => {
      setError(null);
      await api.post(`/policies/${id}/endorsements`, {
        type: endType,
        effective_date: endDate,
        description: endDesc || null,
        premium_impact: endImpact,
      });
    },
    onSuccess: async () => {
      setEndDesc("");
      setEndImpact("0");
      await invalidate();
    },
    onError: (err) => setError(getErrorMessage(err, "Endorsement failed.")),
  });

  const decideEnd = useMutation({
    mutationFn: async ({
      endorsementId,
      action,
    }: {
      endorsementId: string;
      action: "approve" | "reject";
    }) => {
      setError(null);
      await api.post(
        `/policies/${id}/endorsements/${endorsementId}/${action}`,
      );
    },
    onSuccess: invalidate,
    onError: (err) => setError(getErrorMessage(err, "Action failed.")),
  });

  if (isLoading) return <p className="text-slate-500">Loading policy…</p>;
  if (isError || !policy)
    return <p className="text-red-600">Failed to load policy.</p>;

  const details =
    policy.auto_details ?? policy.home_details ?? policy.life_details ?? null;

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm text-slate-500">
            <Link to="/policies" className="text-indigo-600 hover:underline">
              Policies
            </Link>{" "}
            / {policy.policy_number}
          </p>
          <h2 className="mt-1 text-2xl font-bold text-slate-800">
            {policy.policy_number}
          </h2>
        </div>
        <Badge value={policy.status} />
      </div>

      {error && <Alert message={error} />}

      <Card>
        <dl>
          <Row label="Type">
            <span className="capitalize">{policy.policy_type}</span>
          </Row>
          <Row label="Annual premium">
            {formatMoney(policy.annual_premium)}
          </Row>
          <Row label="Payment">
            <span className="capitalize">
              {policy.payment_frequency.replace(/_/g, " ")}
            </span>
          </Row>
          <Row label="Term">
            {policy.effective_date} → {policy.expiration_date}
          </Row>
          {policy.cancellation_reason && (
            <Row label="Cancel reason">{policy.cancellation_reason}</Row>
          )}
        </dl>
      </Card>

      {details && (
        <Card>
          <h3 className="mb-3 text-sm font-semibold text-slate-800">
            Coverage details
          </h3>
          <dl>
            {Object.entries(details).map(([k, v]) => (
              <Row key={k} label={k.replace(/_/g, " ")}>
                {typeof v === "boolean" ? (v ? "Yes" : "No") : String(v ?? "—")}
              </Row>
            ))}
          </dl>
        </Card>
      )}

      {policy.beneficiaries.length > 0 && (
        <Card>
          <h3 className="mb-3 text-sm font-semibold text-slate-800">
            Beneficiaries
          </h3>
          <ul className="space-y-2 text-sm">
            {policy.beneficiaries.map((b) => (
              <li key={b.id} className="flex justify-between border-b border-slate-100 py-2">
                <span>
                  {b.full_name}
                  {b.is_contingent ? " (contingent)" : ""}
                </span>
                <span className="text-slate-600">{b.allocation_pct}%</span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <BillingCard policyId={policy.id} schedules={policy.premium_schedules} />

      <DocumentsCard ownerType="policy" ownerId={policy.id} />

      <Card className="space-y-4">
        <h3 className="text-sm font-semibold text-slate-800">Endorsements</h3>
        {endorsements && endorsements.length === 0 && (
          <p className="text-sm text-slate-500">No endorsements yet.</p>
        )}
        <ul className="space-y-3">
          {endorsements?.map((e) => (
            <li
              key={e.id}
              className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3 text-sm"
            >
              <div>
                <p className="font-medium text-slate-800">
                  {e.endorsement_number ?? e.id.slice(0, 8)} ·{" "}
                  <span className="capitalize">{e.type.replace(/_/g, " ")}</span>
                </p>
                <p className="text-slate-500">
                  {e.effective_date} · impact {formatMoney(e.premium_impact)}
                </p>
                {e.description && (
                  <p className="mt-1 text-slate-600">{e.description}</p>
                )}
              </div>
              <div className="flex items-center gap-2">
                <Badge value={e.status} />
                {e.status === "pending" && isAgentUp && (
                  <Button
                    variant="secondary"
                    loading={decideEnd.isPending}
                    onClick={() =>
                      decideEnd.mutate({
                        endorsementId: e.id,
                        action: "approve",
                      })
                    }
                  >
                    Approve
                  </Button>
                )}
                {e.status === "pending" && isManagerUp && (
                  <Button
                    variant="danger"
                    loading={decideEnd.isPending}
                    onClick={() =>
                      decideEnd.mutate({
                        endorsementId: e.id,
                        action: "reject",
                      })
                    }
                  >
                    Reject
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ul>

        {isAgentUp && policy.status === "active" && (
          <div className="grid gap-3 border-t border-slate-100 pt-4 sm:grid-cols-2">
            <Field label="Type" htmlFor="end_type">
              <Select
                id="end_type"
                value={endType}
                onChange={(e) => setEndType(e.target.value as EndorsementType)}
              >
                {ENDORSEMENT_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t.replace(/_/g, " ")}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Effective date" htmlFor="end_date">
              <Input
                id="end_date"
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
              />
            </Field>
            <Field label="Premium impact (+/−)" htmlFor="end_impact">
              <Input
                id="end_impact"
                value={endImpact}
                onChange={(e) => setEndImpact(e.target.value)}
              />
            </Field>
            <Field label="Description" htmlFor="end_desc">
              <Input
                id="end_desc"
                value={endDesc}
                onChange={(e) => setEndDesc(e.target.value)}
              />
            </Field>
            <div className="sm:col-span-2">
              <Button
                loading={createEnd.isPending}
                onClick={() => createEnd.mutate()}
              >
                Request endorsement
              </Button>
            </div>
          </div>
        )}
      </Card>

      {isAgentUp &&
        (policy.status === "active" || policy.status === "lapsed") && (
          <Card className="space-y-3">
            <h3 className="text-sm font-semibold text-slate-800">Cancel policy</h3>
            {!showCancel ? (
              <Button variant="danger" onClick={() => setShowCancel(true)}>
                Cancel policy…
              </Button>
            ) : (
              <>
                <Field label="Reason" htmlFor="cancel_reason">
                  <Input
                    id="cancel_reason"
                    value={cancelReason}
                    onChange={(e) => setCancelReason(e.target.value)}
                  />
                </Field>
                <div className="flex gap-2">
                  <Button
                    variant="danger"
                    loading={cancelMut.isPending}
                    disabled={!cancelReason.trim()}
                    onClick={() => cancelMut.mutate()}
                  >
                    Confirm cancel
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => setShowCancel(false)}
                  >
                    Never mind
                  </Button>
                </div>
              </>
            )}
          </Card>
        )}

      {isManagerUp && policy.status === "lapsed" && (
        <Card>
          <h3 className="mb-3 text-sm font-semibold text-slate-800">
            Reinstate policy
          </h3>
          <Button
            loading={reinstateMut.isPending}
            onClick={() => reinstateMut.mutate()}
          >
            Reinstate to active
          </Button>
        </Card>
      )}
    </div>
  );
}
