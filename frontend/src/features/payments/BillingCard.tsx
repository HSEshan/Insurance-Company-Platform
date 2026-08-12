import { useState } from "react";
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
import { useAuthStore } from "../../stores/authStore";
import type {
  Envelope,
  Payment,
  PaymentMethod,
  PremiumSchedule,
} from "../../types";
import { formatMoney } from "../../types";

const METHOD_LABELS: Record<PaymentMethod, string> = {
  ach: "ACH transfer",
  credit_card: "Credit / debit card",
  check: "Check",
  wire: "Wire transfer",
  cash: "Cash",
};

/** Paper instruments carry their own number; the server generates the rest. */
const METHODS_NEEDING_REFERENCE: PaymentMethod[] = ["check", "wire"];

function sum(values: string[]): number {
  return values.reduce((total, value) => total + Number(value || 0), 0);
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className="text-lg font-semibold text-slate-800">{value}</p>
    </div>
  );
}

interface BillingCardProps {
  policyId: string;
  schedules: PremiumSchedule[];
}

export function BillingCard({ policyId, schedules }: BillingCardProps) {
  const role = useAuthStore((s) => s.user?.role);
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [openInstallment, setOpenInstallment] = useState<string | null>(null);
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState<PaymentMethod>("ach");
  const [reference, setReference] = useState("");
  const [voidingId, setVoidingId] = useState<string | null>(null);

  const canRecord =
    role === "agent" || role === "manager" || role === "super_admin";
  const canVoid = role === "manager" || role === "super_admin";

  const { data: payments } = useQuery({
    queryKey: ["policy-payments", policyId],
    enabled: !!policyId,
    queryFn: async () => {
      const res = await api.get<Envelope<Payment[]>>(
        `/policies/${policyId}/payments`,
      );
      return res.data.data ?? [];
    },
  });

  const refresh = () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: ["policy", policyId] }),
      qc.invalidateQueries({ queryKey: ["policy-payments", policyId] }),
    ]);

  const record = useMutation({
    mutationFn: async (scheduleId: string) => {
      setError(null);
      await api.post("/payments", {
        schedule_id: scheduleId,
        amount,
        method,
        reference_number: reference || undefined,
      });
    },
    onSuccess: async () => {
      closeForm();
      await refresh();
    },
    onError: (err) => setError(getErrorMessage(err, "Could not record payment.")),
  });

  const voidPayment = useMutation({
    mutationFn: async ({ id, reason }: { id: string; reason: string }) => {
      setError(null);
      await api.post(`/payments/${id}/void`, { reason });
    },
    onSuccess: async () => {
      setVoidingId(null);
      await refresh();
    },
    onError: (err) => setError(getErrorMessage(err, "Could not void payment.")),
  });

  function openForm(schedule: PremiumSchedule) {
    setError(null);
    setOpenInstallment(schedule.id);
    // Default to settling the installment outright, which is the common case.
    setAmount(schedule.balance);
    setMethod("ach");
    setReference("");
  }

  function closeForm() {
    setOpenInstallment(null);
    setAmount("");
    setReference("");
  }

  const totalBilled = sum(schedules.map((s) => s.amount_due));
  const totalPaid = sum(schedules.map((s) => s.amount_paid));
  const outstanding = sum(schedules.map((s) => s.balance));
  const nextDue = schedules.find((s) => Number(s.balance) > 0);

  return (
    <>
      <Card className="space-y-5">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-800">
            Premium billing
          </h3>
          {nextDue && (
            <span className="text-xs text-slate-500">
              Next due {nextDue.due_date}
            </span>
          )}
        </div>

        {error && <Alert message={error} />}

        <div className="grid grid-cols-2 gap-4 border-b border-slate-100 pb-4 sm:grid-cols-4">
          <Stat label="Billed" value={formatMoney(totalBilled)} />
          <Stat label="Collected" value={formatMoney(totalPaid)} />
          <Stat label="Outstanding" value={formatMoney(outstanding)} />
          <Stat
            label="Installments"
            value={`${schedules.filter((s) => s.status === "paid").length}/${schedules.length}`}
          />
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase text-slate-500">
              <tr className="border-b border-slate-200">
                <th className="py-2 pr-3 font-medium">Due</th>
                <th className="py-2 pr-3 font-medium">Amount</th>
                <th className="py-2 pr-3 font-medium">Paid</th>
                <th className="py-2 pr-3 font-medium">Balance</th>
                <th className="py-2 pr-3 font-medium">Status</th>
                {canRecord && <th className="py-2 font-medium" />}
              </tr>
            </thead>
            <tbody>
              {schedules.map((s) => (
                <tr key={s.id} className="border-b border-slate-100 last:border-0">
                  <td className="py-2 pr-3 text-slate-700">{s.due_date}</td>
                  <td className="py-2 pr-3 text-slate-700">
                    {formatMoney(s.amount_due)}
                  </td>
                  <td className="py-2 pr-3 text-slate-600">
                    {formatMoney(s.amount_paid)}
                  </td>
                  <td className="py-2 pr-3 font-medium text-slate-800">
                    {formatMoney(s.balance)}
                  </td>
                  <td className="py-2 pr-3">
                    <Badge value={s.status} />
                  </td>
                  {canRecord && (
                    <td className="py-2 text-right">
                      {Number(s.balance) > 0 && s.status !== "waived" && (
                        <Button
                          variant="ghost"
                          className="px-2 py-1 text-xs"
                          onClick={() =>
                            openInstallment === s.id ? closeForm() : openForm(s)
                          }
                        >
                          {openInstallment === s.id ? "Cancel" : "Record payment"}
                        </Button>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {openInstallment && (
          <form
            className="grid gap-3 border-t border-slate-100 pt-4 sm:grid-cols-3"
            onSubmit={(e) => {
              e.preventDefault();
              record.mutate(openInstallment);
            }}
          >
            <Field label="Amount" htmlFor="pay-amount">
              <Input
                id="pay-amount"
                type="number"
                step="0.01"
                min="0.01"
                required
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
              />
            </Field>
            <Field label="Method" htmlFor="pay-method">
              <Select
                id="pay-method"
                value={method}
                onChange={(e) => setMethod(e.target.value as PaymentMethod)}
              >
                {(Object.keys(METHOD_LABELS) as PaymentMethod[]).map((m) => (
                  <option key={m} value={m}>
                    {METHOD_LABELS[m]}
                  </option>
                ))}
              </Select>
            </Field>
            <Field
              label={
                METHODS_NEEDING_REFERENCE.includes(method)
                  ? "Reference number"
                  : "Reference (optional)"
              }
              htmlFor="pay-reference"
            >
              <Input
                id="pay-reference"
                required={METHODS_NEEDING_REFERENCE.includes(method)}
                placeholder={
                  METHODS_NEEDING_REFERENCE.includes(method)
                    ? "Check or wire number"
                    : "Generated automatically"
                }
                value={reference}
                onChange={(e) => setReference(e.target.value)}
              />
            </Field>
            <div className="sm:col-span-3">
              <Button type="submit" loading={record.isPending}>
                Record payment
              </Button>
            </div>
          </form>
        )}
      </Card>

      <Card className="space-y-4">
        <h3 className="text-sm font-semibold text-slate-800">Payment history</h3>
        {payments && payments.length === 0 && (
          <p className="text-sm text-slate-500">No payments recorded yet.</p>
        )}
        {payments && payments.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase text-slate-500">
                <tr className="border-b border-slate-200">
                  <th className="py-2 pr-3 font-medium">Date</th>
                  <th className="py-2 pr-3 font-medium">Amount</th>
                  <th className="py-2 pr-3 font-medium">Method</th>
                  <th className="py-2 pr-3 font-medium">Reference</th>
                  <th className="py-2 pr-3 font-medium">Status</th>
                  {canVoid && <th className="py-2 font-medium" />}
                </tr>
              </thead>
              <tbody>
                {payments.map((p) => (
                  <tr
                    key={p.id}
                    className="border-b border-slate-100 last:border-0"
                  >
                    <td className="py-2 pr-3 text-slate-700">
                      {new Date(p.created_at).toLocaleDateString()}
                    </td>
                    <td className="py-2 pr-3 text-slate-800">
                      {formatMoney(p.amount)}
                    </td>
                    <td className="py-2 pr-3 text-slate-600">
                      {p.method ? METHOD_LABELS[p.method] : "—"}
                    </td>
                    <td className="py-2 pr-3 font-mono text-xs text-slate-500">
                      {p.reference_number ?? "—"}
                    </td>
                    <td className="py-2 pr-3">
                      <Badge value={p.status} />
                    </td>
                    {canVoid && (
                      <td className="py-2 text-right">
                        {p.status === "completed" && (
                          <Button
                            variant="ghost"
                            className="px-2 py-1 text-xs text-red-600 hover:bg-red-50"
                            loading={
                              voidPayment.isPending && voidingId === p.id
                            }
                            onClick={() => {
                              const reason = window.prompt(
                                "Reason for voiding this payment?",
                              );
                              if (!reason) return;
                              setVoidingId(p.id);
                              voidPayment.mutate({ id: p.id, reason });
                            }}
                          >
                            Void
                          </Button>
                        )}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
