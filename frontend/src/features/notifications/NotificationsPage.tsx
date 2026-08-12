import { useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, getErrorMessage } from "../../lib/api";
import { Alert, Button, Card, Select } from "../../components/ui";
import type { AppNotification, Envelope, Meta } from "../../types";

const PER_PAGE = 20;

export function NotificationsPage() {
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["notifications", "list", { page, unreadOnly }],
    placeholderData: keepPreviousData,
    queryFn: async () => {
      const res = await api.get<Envelope<AppNotification[]>>("/notifications", {
        params: {
          page,
          per_page: PER_PAGE,
          unread_only: unreadOnly || undefined,
        },
      });
      return {
        items: res.data.data ?? [],
        meta: res.data.meta ?? (null as Meta | null),
      };
    },
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["notifications"] });

  const markRead = useMutation({
    mutationFn: async (id: string) => {
      setError(null);
      await api.post(`/notifications/${id}/read`);
    },
    onSuccess: invalidate,
    onError: (err) => setError(getErrorMessage(err, "Could not mark as read.")),
  });

  const markAll = useMutation({
    mutationFn: async () => {
      setError(null);
      await api.post("/notifications/read-all");
    },
    onSuccess: invalidate,
    onError: (err) => setError(getErrorMessage(err, "Could not mark all as read.")),
  });

  const total = data?.meta?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PER_PAGE));

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-2xl font-bold text-slate-800">Notifications</h2>
        <div className="flex flex-wrap items-center gap-2">
          <Select
            value={unreadOnly ? "unread" : "all"}
            onChange={(e) => {
              setUnreadOnly(e.target.value === "unread");
              setPage(1);
            }}
            className="w-40"
          >
            <option value="all">All</option>
            <option value="unread">Unread only</option>
          </Select>
          <Button
            variant="secondary"
            loading={markAll.isPending}
            onClick={() => markAll.mutate()}
          >
            Mark all read
          </Button>
        </div>
      </div>

      {error && <Alert message={error} />}

      <Card className="divide-y divide-slate-100 p-0">
        {isLoading && (
          <p className="px-4 py-8 text-sm text-slate-500">Loading…</p>
        )}
        {isError && (
          <p className="px-4 py-8 text-sm text-red-600">
            Failed to load notifications.
          </p>
        )}
        {data && data.items.length === 0 && (
          <p className="px-4 py-8 text-sm text-slate-500">
            {unreadOnly ? "No unread notifications." : "No notifications yet."}
          </p>
        )}
        {data?.items.map((n) => (
          <div
            key={n.id}
            className={`flex items-start justify-between gap-4 px-4 py-3 ${
              n.is_read ? "" : "bg-indigo-50/30"
            }`}
          >
            <div>
              <p className="text-sm font-medium text-slate-800">
                {n.title ?? "Notification"}
                {!n.is_read && (
                  <span className="ml-2 rounded bg-indigo-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-indigo-700">
                    New
                  </span>
                )}
              </p>
              <p className="mt-1 text-sm text-slate-600">{n.body}</p>
              <p className="mt-1 text-xs text-slate-400">
                {new Date(n.created_at).toLocaleString()}
                {n.sent_via_email ? " · emailed" : ""}
              </p>
            </div>
            {!n.is_read && (
              <Button
                variant="ghost"
                className="shrink-0 px-2 py-1 text-xs"
                loading={markRead.isPending && markRead.variables === n.id}
                onClick={() => markRead.mutate(n.id)}
              >
                Mark read
              </Button>
            )}
          </div>
        ))}
      </Card>

      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm text-slate-600">
          <span>
            Page {page} of {totalPages} · {total} total
          </span>
          <div className="flex gap-2">
            <Button
              variant="secondary"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
            >
              Previous
            </Button>
            <Button
              variant="secondary"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
