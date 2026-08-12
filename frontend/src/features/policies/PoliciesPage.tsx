import { useState } from "react";
import { Link } from "react-router-dom";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { Badge, Card, Select } from "../../components/ui";
import type {
  Envelope,
  Meta,
  PolicyListItem,
  PolicyStatus,
  PolicyType,
} from "../../types";
import { formatMoney } from "../../types";

const PER_PAGE = 10;

export function PoliciesPage() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<PolicyStatus | "">("");
  const [policyType, setPolicyType] = useState<PolicyType | "">("");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["policies", { page, status, policyType }],
    placeholderData: keepPreviousData,
    queryFn: async () => {
      const res = await api.get<Envelope<PolicyListItem[]>>("/policies", {
        params: {
          page,
          per_page: PER_PAGE,
          status: status || undefined,
          policy_type: policyType || undefined,
        },
      });
      return { items: res.data.data ?? [], meta: res.data.meta ?? (null as Meta | null) };
    },
  });

  const total = data?.meta?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PER_PAGE));

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-slate-800">Policies</h2>

      <div className="flex flex-wrap gap-3">
        <Select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value as PolicyStatus | "");
            setPage(1);
          }}
          className="w-48"
        >
          <option value="">All statuses</option>
          {(
            [
              "active",
              "lapsed",
              "cancelled",
              "expired",
              "draft",
              "under_review",
            ] as PolicyStatus[]
          ).map((s) => (
            <option key={s} value={s}>
              {s.replace(/_/g, " ")}
            </option>
          ))}
        </Select>
        <Select
          value={policyType}
          onChange={(e) => {
            setPolicyType(e.target.value as PolicyType | "");
            setPage(1);
          }}
          className="w-40"
        >
          <option value="">All types</option>
          <option value="auto">Auto</option>
          <option value="home">Home</option>
          <option value="life">Life</option>
        </Select>
      </div>

      <Card className="p-0">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-6 py-3">Policy #</th>
              <th className="px-6 py-3">Type</th>
              <th className="px-6 py-3">Status</th>
              <th className="px-6 py-3">Premium</th>
              <th className="px-6 py-3">Term</th>
              <th className="px-6 py-3" />
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td colSpan={6} className="px-6 py-8 text-center text-slate-400">
                  Loading policies…
                </td>
              </tr>
            )}
            {isError && (
              <tr>
                <td colSpan={6} className="px-6 py-8 text-center text-red-500">
                  Failed to load policies.
                </td>
              </tr>
            )}
            {data && data.items.length === 0 && !isLoading && (
              <tr>
                <td colSpan={6} className="px-6 py-8 text-center text-slate-400">
                  No policies found.
                </td>
              </tr>
            )}
            {data?.items.map((p) => (
              <tr key={p.id} className="border-b border-slate-100 last:border-0">
                <td className="px-6 py-3 font-medium text-slate-800">
                  {p.policy_number}
                </td>
                <td className="px-6 py-3 capitalize text-slate-600">
                  {p.policy_type}
                </td>
                <td className="px-6 py-3">
                  <Badge value={p.status} />
                </td>
                <td className="px-6 py-3 text-slate-700">
                  {formatMoney(p.annual_premium)}
                </td>
                <td className="px-6 py-3 text-slate-600">
                  {p.effective_date} → {p.expiration_date}
                </td>
                <td className="px-6 py-3 text-right">
                  <Link
                    to={`/policies/${p.id}`}
                    className="text-indigo-600 hover:underline"
                  >
                    View
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <div className="flex items-center justify-between text-sm text-slate-500">
        <span>{total} total policies</span>
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
    </div>
  );
}
