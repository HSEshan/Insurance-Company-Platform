import { useState } from "react";
import { Link } from "react-router-dom";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { Badge, Card, Select } from "../../components/ui";
import type {
  Envelope,
  Meta,
  Payment,
  PaymentStatus,
  PaymentType,
} from "../../types";
import { formatMoney } from "../../types";

const PER_PAGE = 20;

const TYPES: PaymentType[] = ["premium", "claim_payout", "refund", "fee"];
const STATUSES: PaymentStatus[] = [
  "pending",
  "completed",
  "failed",
  "voided",
  "refunded",
];

export function PaymentsPage() {
  const [page, setPage] = useState(1);
  const [type, setType] = useState<PaymentType | "">("");
  const [status, setStatus] = useState<PaymentStatus | "">("");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["payments", { page, type, status }],
    placeholderData: keepPreviousData,
    queryFn: async () => {
      const res = await api.get<Envelope<Payment[]>>("/payments", {
        params: {
          page,
          per_page: PER_PAGE,
          payment_type: type || undefined,
          status: status || undefined,
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

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-slate-800">Payments</h2>

      <div className="flex flex-wrap gap-3">
        <Select
          value={type}
          onChange={(e) => {
            setType(e.target.value as PaymentType | "");
            setPage(1);
          }}
          className="w-52"
        >
          <option value="">All types</option>
          {TYPES.map((t) => (
            <option key={t} value={t}>
              {t.replace(/_/g, " ")}
            </option>
          ))}
        </Select>
        <Select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value as PaymentStatus | "");
            setPage(1);
          }}
          className="w-52"
        >
          <option value="">All statuses</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </Select>
      </div>

      <Card className="p-0">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-6 py-3">Date</th>
              <th className="px-6 py-3">Reference</th>
              <th className="px-6 py-3">Type</th>
              <th className="px-6 py-3">Applied to</th>
              <th className="px-6 py-3">Customer</th>
              <th className="px-6 py-3">Amount</th>
              <th className="px-6 py-3">Status</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td colSpan={7} className="px-6 py-8 text-center text-slate-400">
                  Loading payments…
                </td>
              </tr>
            )}
            {isError && (
              <tr>
                <td colSpan={7} className="px-6 py-8 text-center text-red-500">
                  Failed to load payments.
                </td>
              </tr>
            )}
            {data && data.items.length === 0 && !isLoading && (
              <tr>
                <td colSpan={7} className="px-6 py-8 text-center text-slate-400">
                  No payments found.
                </td>
              </tr>
            )}
            {data?.items.map((p) => (
              <tr key={p.id} className="border-b border-slate-100 last:border-0">
                <td className="px-6 py-3 text-slate-600">
                  {new Date(p.created_at).toLocaleDateString()}
                </td>
                <td className="px-6 py-3 font-mono text-xs text-slate-500">
                  {p.reference_number ?? "—"}
                </td>
                <td className="px-6 py-3">
                  <Badge value={p.payment_type} />
                </td>
                <td className="px-6 py-3 text-slate-700">
                  {p.policy_number ?? p.claim_number ?? "—"}
                </td>
                <td className="px-6 py-3 text-slate-600">
                  {p.customer_name ?? "—"}
                </td>
                <td className="px-6 py-3 font-medium text-slate-800">
                  {formatMoney(p.amount)}
                </td>
                <td className="px-6 py-3">
                  <Badge value={p.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <div className="flex items-center justify-between text-sm text-slate-500">
        <span>{total} total payments</span>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="rounded-lg border border-slate-300 px-3 py-1 disabled:opacity-50"
          >
            Previous
          </button>
          <span>
            Page {page} of {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
            className="rounded-lg border border-slate-300 px-3 py-1 disabled:opacity-50"
          >
            Next
          </button>
        </div>
      </div>

      <p className="text-xs text-slate-500">
        Premium payments are recorded from a policy's billing card.{" "}
        <Link to="/policies" className="text-indigo-600 hover:underline">
          Go to policies
        </Link>
      </p>
    </div>
  );
}
