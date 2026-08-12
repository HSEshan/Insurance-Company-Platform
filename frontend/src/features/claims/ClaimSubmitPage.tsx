import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, getErrorMessage } from "../../lib/api";
import {
  Alert,
  Button,
  Card,
  Field,
  Input,
  Select,
} from "../../components/ui";
import { useAuthStore } from "../../stores/authStore";
import type {
  Claim,
  ClaimType,
  Envelope,
  PolicyListItem,
  PolicyType,
} from "../../types";

const TYPES_BY_POLICY: Record<PolicyType, ClaimType[]> = {
  auto: ["auto_collision", "auto_comprehensive", "auto_liability"],
  home: ["home_dwelling", "home_personal_property", "home_liability"],
  life: ["life_death_benefit"],
};

export function ClaimSubmitPage() {
  const navigate = useNavigate();
  const role = useAuthStore((s) => s.user?.role);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [policyId, setPolicyId] = useState("");
  const [claimType, setClaimType] = useState<ClaimType>("auto_collision");
  const [incidentDate, setIncidentDate] = useState(
    () => new Date().toISOString().slice(0, 10),
  );
  const [location, setLocation] = useState("");
  const [estimate, setEstimate] = useState("");
  const [description, setDescription] = useState("");

  const { data: policies } = useQuery({
    queryKey: ["policies", { forClaim: true, status: "active" }],
    queryFn: async () => {
      const res = await api.get<Envelope<PolicyListItem[]>>("/policies", {
        params: { page: 1, per_page: 100, status: "active" },
      });
      return res.data.data ?? [];
    },
  });

  const selected = policies?.find((p) => p.id === policyId);
  const typeOptions = selected
    ? TYPES_BY_POLICY[selected.policy_type]
    : TYPES_BY_POLICY.auto;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!policyId) {
      setError("Select a policy.");
      return;
    }
    if (description.trim().length < 10) {
      setError("Description must be at least 10 characters.");
      return;
    }
    setSubmitting(true);
    try {
      const res = await api.post<Envelope<Claim>>("/claims", {
        policy_id: policyId,
        claim_type: claimType,
        incident_date: incidentDate,
        incident_location: location || null,
        estimated_damage: estimate || null,
        description,
      });
      const claim = res.data.data;
      if (!claim) throw new Error("No claim returned");
      navigate(`/claims/${claim.id}`);
    } catch (err) {
      setError(getErrorMessage(err, "Could not submit claim."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <div>
        <p className="text-sm text-slate-500">
          <Link to="/claims" className="text-indigo-600 hover:underline">
            Claims
          </Link>{" "}
          / New
        </p>
        <h2 className="mt-1 text-2xl font-bold text-slate-800">File a claim</h2>
        <p className="mt-1 text-sm text-slate-500">
          {role === "customer"
            ? "Select one of your active policies and describe the incident."
            : "Select an active policy and describe the incident."}
        </p>
      </div>

      {error && <Alert message={error} />}

      <Card>
        <form className="space-y-4" onSubmit={handleSubmit}>
          <Field label="Policy" htmlFor="policy_id">
            <Select
              id="policy_id"
              value={policyId}
              onChange={(e) => {
                setPolicyId(e.target.value);
                const p = policies?.find((x) => x.id === e.target.value);
                if (p) setClaimType(TYPES_BY_POLICY[p.policy_type][0]);
              }}
            >
              <option value="">Select active policy…</option>
              {policies?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.policy_number} ({p.policy_type})
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Claim type" htmlFor="claim_type">
            <Select
              id="claim_type"
              value={claimType}
              onChange={(e) => setClaimType(e.target.value as ClaimType)}
            >
              {typeOptions.map((t) => (
                <option key={t} value={t}>
                  {t.replace(/_/g, " ")}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Incident date" htmlFor="incident_date">
            <Input
              id="incident_date"
              type="date"
              value={incidentDate}
              onChange={(e) => setIncidentDate(e.target.value)}
            />
          </Field>
          <Field label="Location (optional)" htmlFor="location">
            <Input
              id="location"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
            />
          </Field>
          <Field label="Estimated damage (optional)" htmlFor="estimate">
            <Input
              id="estimate"
              value={estimate}
              onChange={(e) => setEstimate(e.target.value)}
              placeholder="2500.00"
            />
          </Field>
          <Field label="Description" htmlFor="description">
            <textarea
              id="description"
              rows={4}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </Field>
          <Button type="submit" loading={submitting}>
            Submit claim
          </Button>
        </form>
      </Card>
    </div>
  );
}
