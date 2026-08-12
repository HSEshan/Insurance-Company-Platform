import { useState } from "react";
import { Link } from "react-router-dom";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { FilePlus2 } from "lucide-react";
import { api } from "../../lib/api";
import { Badge, Button, Card, Select } from "../../components/ui";
import { useAuthStore } from "../../stores/authStore";
import type {
  ClaimListItem,
  ClaimStatus,
  Envelope,
  Meta,
} from "../../types";
import { formatMoney } from "../../types";

const PER_PAGE = 10;

export function ClaimsPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canSubmit =
    role === "customer" || role === "agent" || role === "super_admin";
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<ClaimStatus | "">("");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["claims", { page, status }],
    placeholderData: keepPreviousData,
    queryFn: async () => {
      const res = await api.get<Envelope<ClaimListItem[]>>("/claims", {
        params: {
          page,
          per_page: PER_PAGE,
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
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-2xl font-bold text-slate-800">Claims</h2>
        {canSubmit && (
          <Link to="/claims/new">
            <Button>
              <FilePlus2 className="h-4 w-4" />
              File claim
            </Button>
          </Link>
        )}
      </div>

      <Select
        value={status}
        onChange={(e) => {
          setStatus(e.target.value as ClaimStatus | "");
          setPage(1);
        }}
        className="w-52"
      >
        <option value="">All statuses</option>
        {(
          [
            "submitted",
            "assigned",
            "investigating",
            "info_requested",
            "approved",
            "rejected",
            "disputed",
            "paid",
            "closed",
          ] as ClaimStatus[]
        ).map((s) => (
          <option key={s} value={s}>
            {s.replace(/_/g, " ")}
          </option>
        ))}
      </Select>

      <Card className="p-0">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-6 py-3">Claim #</th>
              <th className="px-6 py-3">Type</th>
              <th className="px-6 py-3">Status</th>
              <th className="px-6 py-3">Estimate</th>
              <th className="px-6 py-3">Incident</th>
              <th className="px-6 py-3" />
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td colSpan={6} className="px-6 py-8 text-center text-slate-400">
                  Loading claims…
                </td>
              </tr>
            )}
            {isError && (
              <tr>
                <td colSpan={6} className="px-6 py-8 text-center text-red-500">
                  Failed to load claims.
                </td>
              </tr>
            )}
            {data && data.items.length === 0 && !isLoading && (
              <tr>
                <td colSpan={6} className="px-6 py-8 text-center text-slate-400">
                  No claims found.
                </td>
              </tr>
            )}
            {data?.items.map((c) => (
              <tr key={c.id} className="border-b border-slate-100 last:border-0">
                <td className="px-6 py-3 font-medium text-slate-800">
                  {c.claim_number}
                  {c.fraud_flag && (
                    <span className="ml-2 text-xs font-semibold text-red-600">
                      FRAUD
                    </span>
                  )}
                </td>
                <td className="px-6 py-3 capitalize text-slate-600">
                  {c.claim_type.replace(/_/g, " ")}
                </td>
                <td className="px-6 py-3">
                  <Badge value={c.status} />
                </td>
                <td className="px-6 py-3">
                  {formatMoney(c.estimated_damage)}
                </td>
                <td className="px-6 py-3 text-slate-600">{c.incident_date}</td>
                <td className="px-6 py-3 text-right">
                  <Link
                    to={`/claims/${c.id}`}
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
        <span>{total} total claims</span>
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
