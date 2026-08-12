import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { api } from "../../lib/api";
import type { AppNotification, Envelope } from "../../types";

export function NotificationBell() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  const { data: unread = 0 } = useQuery({
    queryKey: ["notifications", "unread-count"],
    queryFn: async () => {
      const res = await api.get<Envelope<{ unread: number }>>(
        "/notifications/unread-count",
      );
      return res.data.data?.unread ?? 0;
    },
    refetchInterval: 30_000,
  });

  const { data: recent = [] } = useQuery({
    queryKey: ["notifications", "recent"],
    enabled: open,
    queryFn: async () => {
      const res = await api.get<Envelope<AppNotification[]>>("/notifications", {
        params: { per_page: 10 },
      });
      return res.data.data ?? [];
    },
  });

  const markRead = useMutation({
    mutationFn: async (id: string) => {
      await api.post(`/notifications/${id}/read`);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notifications"] });
    },
  });

  useEffect(() => {
    if (!open) return;
    function onClick(event: MouseEvent) {
      if (
        panelRef.current &&
        !panelRef.current.contains(event.target as Node)
      ) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  return (
    <div className="relative" ref={panelRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="relative rounded-lg p-2 text-slate-600 hover:bg-slate-100"
        aria-label="Notifications"
      >
        <Bell className="h-5 w-5" />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-semibold text-white">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 z-20 mt-2 w-80 rounded-lg border border-slate-200 bg-white shadow-lg">
          <div className="flex items-center justify-between border-b border-slate-100 px-3 py-2">
            <p className="text-sm font-semibold text-slate-800">Notifications</p>
            <Link
              to="/notifications"
              onClick={() => setOpen(false)}
              className="text-xs font-medium text-indigo-600 hover:text-indigo-700"
            >
              View all
            </Link>
          </div>
          <ul className="max-h-80 overflow-y-auto">
            {recent.length === 0 && (
              <li className="px-3 py-6 text-center text-sm text-slate-500">
                No notifications yet.
              </li>
            )}
            {recent.map((n) => (
              <li key={n.id} className="border-b border-slate-50 last:border-0">
                <button
                  type="button"
                  className={`w-full px-3 py-2.5 text-left hover:bg-slate-50 ${
                    n.is_read ? "" : "bg-indigo-50/40"
                  }`}
                  onClick={() => {
                    if (!n.is_read) markRead.mutate(n.id);
                  }}
                >
                  <p className="text-sm font-medium text-slate-800">
                    {n.title ?? "Notification"}
                  </p>
                  <p className="mt-0.5 line-clamp-2 text-xs text-slate-600">
                    {n.body}
                  </p>
                  <p className="mt-1 text-[11px] text-slate-400">
                    {new Date(n.created_at).toLocaleString()}
                  </p>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
