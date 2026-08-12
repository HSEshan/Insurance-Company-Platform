import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, getErrorMessage } from "../../lib/api";
import { Alert, Badge, Button, Card, Select } from "../../components/ui";
import { useAuthStore } from "../../stores/authStore";
import type {
  Envelope,
  PaymentFrequency,
  Quote,
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

export function QuoteDetailPage() {
  const { id } = useParams<{ id: string }>();
  const role = useAuthStore((s) => s.user?.role);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [frequency, setFrequency] = useState<PaymentFrequency>("monthly");

  const isStaff =
    role === "agent" || role === "manager" || role === "super_admin";

  const { data: quote, isLoading, isError } = useQuery({
    queryKey: ["quote", id],
    enabled: !!id,
    queryFn: async () => {
      const res = await api.get<Envelope<Quote>>(`/quotes/${id}`);
      return res.data.data!;
    },
  });

  const invalidate = async () => {
    await qc.invalidateQueries({ queryKey: ["quote", id] });
    await qc.invalidateQueries({ queryKey: ["quotes"] });
  };

  const action = useMutation({
    mutationFn: async (path: string) => {
      setError(null);
      if (path.endsWith("/bind")) {
        const res = await api.post<Envelope<{ id: string }>>(path, {
          payment_frequency: frequency,
        });
        return res.data.data;
      }
      const res = await api.post<Envelope<Quote>>(path);
      return res.data.data;
    },
    onSuccess: async (data, path) => {
      await invalidate();
      if (path.endsWith("/bind") && data && "id" in data) {
        navigate(`/policies/${data.id}`);
      }
    },
    onError: (err) => setError(getErrorMessage(err, "Action failed.")),
  });

  if (isLoading) return <p className="text-slate-500">Loading quote…</p>;
  if (isError || !quote)
    return <p className="text-red-600">Failed to load quote.</p>;

  const run = (suffix: string) =>
    action.mutate(`/quotes/${quote.id}${suffix}`);

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm text-slate-500">
            <Link to="/quotes" className="text-indigo-600 hover:underline">
              Quotes
            </Link>{" "}
            / {quote.id.slice(0, 8)}
          </p>
          <h2 className="mt-1 text-2xl font-bold capitalize text-slate-800">
            {quote.policy_type} quote
          </h2>
        </div>
        <Badge value={quote.status} />
      </div>

      {error && <Alert message={error} />}

      <Card>
        <dl>
          <Row label="Annual premium">{formatMoney(quote.quoted_premium)}</Row>
          <Row label="Monthly">{formatMoney(quote.monthly_premium)}</Row>
          <Row label="Risk tier">
            <Badge value={quote.risk_tier} />
          </Row>
          <Row label="Effective">{quote.effective_date ?? "—"}</Row>
          <Row label="Expires">{quote.expiry_date ?? "—"}</Row>
          <Row label="Customer ID">
            <span className="font-mono text-xs">{quote.customer_id}</span>
          </Row>
          {quote.notes && <Row label="Notes">{quote.notes}</Row>}
          {quote.decline_reasons && quote.decline_reasons.length > 0 && (
            <Row label="Decline reasons">
              <ul className="list-disc pl-4 text-red-700">
                {quote.decline_reasons.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            </Row>
          )}
        </dl>
      </Card>

      {quote.rating_factors && quote.rating_factors.length > 0 && (
        <Card>
          <h3 className="mb-3 text-sm font-semibold text-slate-800">
            Rating factors
          </h3>
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase text-slate-500">
              <tr>
                <th className="pb-2">Factor</th>
                <th className="pb-2">Multiplier</th>
              </tr>
            </thead>
            <tbody>
              {quote.rating_factors.map((f) => (
                <tr key={f.name} className="border-t border-slate-100">
                  <td className="py-2 capitalize text-slate-700">
                    {f.name.replace(/_/g, " ")}
                  </td>
                  <td className="py-2 text-slate-600">{f.multiplier.toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {isStaff && (
        <Card>
          <h3 className="mb-3 text-sm font-semibold text-slate-800">Actions</h3>
          <div className="flex flex-wrap items-end gap-3">
            {quote.status === "draft" && (
              <Button
                loading={action.isPending}
                onClick={() => run("/submit")}
              >
                Submit for review
              </Button>
            )}
            {quote.status === "pending_review" && (
              <>
                <Button
                  loading={action.isPending}
                  onClick={() => run("/approve")}
                >
                  Approve
                </Button>
                <Button
                  variant="danger"
                  loading={action.isPending}
                  onClick={() => run("/reject")}
                >
                  Reject
                </Button>
              </>
            )}
            {quote.status === "approved" && (
              <>
                <div>
                  <label className="mb-1 block text-xs text-slate-500">
                    Payment frequency
                  </label>
                  <Select
                    value={frequency}
                    onChange={(e) =>
                      setFrequency(e.target.value as PaymentFrequency)
                    }
                  >
                    <option value="monthly">Monthly</option>
                    <option value="quarterly">Quarterly</option>
                    <option value="semi_annual">Semi-annual</option>
                    <option value="annual">Annual</option>
                  </Select>
                </div>
                <Button
                  loading={action.isPending}
                  onClick={() => run("/bind")}
                >
                  Bind policy
                </Button>
              </>
            )}
            {quote.status !== "draft" &&
              quote.status !== "pending_review" &&
              quote.status !== "approved" && (
                <p className="text-sm text-slate-500">
                  No further underwriting actions for this status.
                </p>
              )}
          </div>
        </Card>
      )}
    </div>
  );
}
