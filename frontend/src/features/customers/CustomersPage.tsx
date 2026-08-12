import { useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { api } from "../../lib/api";
import { Badge, Card, Input } from "../../components/ui";
import type { CustomerListItem, Envelope, Meta } from "../../types";

interface CustomerListResponse {
  items: CustomerListItem[];
  meta: Meta | null;
}

const PER_PAGE = 10;

export function CustomersPage() {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["customers", { search, page }],
    placeholderData: keepPreviousData,
    queryFn: async (): Promise<CustomerListResponse> => {
      const res = await api.get<Envelope<CustomerListItem[]>>("/customers", {
        params: { search: search || undefined, page, per_page: PER_PAGE },
      });
      return { items: res.data.data ?? [], meta: res.data.meta ?? null };
    },
  });

  const total = data?.meta?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PER_PAGE));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-slate-800">Customers</h2>
        <div className="relative w-72">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <Input
            placeholder="Search by name or email"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            className="w-full pl-9"
          />
        </div>
      </div>

      <Card className="p-0">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-6 py-3">Name</th>
              <th className="px-6 py-3">Email</th>
              <th className="px-6 py-3">Location</th>
              <th className="px-6 py-3">Risk Tier</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td colSpan={4} className="px-6 py-8 text-center text-slate-400">
                  Loading customers…
                </td>
              </tr>
            )}
            {isError && (
              <tr>
                <td colSpan={4} className="px-6 py-8 text-center text-red-500">
                  Failed to load customers.
                </td>
              </tr>
            )}
            {data && data.items.length === 0 && !isLoading && (
              <tr>
                <td colSpan={4} className="px-6 py-8 text-center text-slate-400">
                  No customers found.
                </td>
              </tr>
            )}
            {data?.items.map((c) => (
              <tr key={c.id} className="border-b border-slate-100 last:border-0">
                <td className="px-6 py-3 font-medium text-slate-800">
                  {c.first_name} {c.last_name}
                </td>
                <td className="px-6 py-3 text-slate-600">{c.email}</td>
                <td className="px-6 py-3 text-slate-600">
                  {[c.city, c.state].filter(Boolean).join(", ") || "—"}
                </td>
                <td className="px-6 py-3">
                  <Badge value={c.risk_tier} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <div className="flex items-center justify-between text-sm text-slate-500">
        <span>{total} total customers</span>
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
