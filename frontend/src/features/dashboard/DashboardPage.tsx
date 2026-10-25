import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuthStore } from "../../stores/authStore";
import { api } from "../../lib/api";
import { Card } from "../../components/ui";
import { ChatWidget } from "../chat/ChatWidget";
import type {
  AdjusterDashboard,
  AgentDashboard,
  CustomerDashboard,
  Envelope,
  ManagerDashboard,
  MonthCount,
  NamedCount,
  UserRole,
} from "../../types";
import { formatMoney } from "../../types";

const ROLE_LINKS: Record<
  UserRole,
  { title: string; hint: string; to?: string }[]
> = {
  customer: [
    { title: "File a claim", hint: "Report a new loss", to: "/claims/new" },
    { title: "Request a quote", hint: "Start a new quote", to: "/quotes/new" },
    { title: "Policies", hint: "Coverage you hold", to: "/policies" },
  ],
  agent: [
    { title: "Customers", hint: "Accounts in your book", to: "/customers" },
    { title: "Quotes", hint: "Underwriting queue", to: "/quotes" },
    { title: "Policies", hint: "Bind, endorse, cancel", to: "/policies" },
  ],
  adjuster: [
    { title: "Claims queue", hint: "Assigned work", to: "/claims" },
    { title: "Policies", hint: "Coverage context", to: "/policies" },
  ],
  manager: [
    { title: "Reports", hint: "CSV downloads & loss ratio", to: "/reports" },
    { title: "Claims", hint: "Assign & large payouts", to: "/claims" },
    { title: "Audit log", hint: "Compliance trail", to: "/audit" },
  ],
  super_admin: [
    { title: "Staff admin", hint: "Create & manage employees", to: "/admin" },
    { title: "Reports", hint: "CSV downloads & loss ratio", to: "/reports" },
    { title: "Customers", hint: "All accounts", to: "/customers" },
    { title: "Audit log", hint: "Compliance trail", to: "/audit" },
  ],
};

export function DashboardPage() {
  const user = useAuthStore((s) => s.user);
  if (!user) return null;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-slate-800">
          Welcome back, {user.first_name}
        </h2>
        <p className="text-sm text-slate-500">
          Overview for your{" "}
          <span className="font-medium capitalize">
            {user.role.replace(/_/g, " ")}
          </span>{" "}
          role.
        </p>
      </div>

      {user.role === "manager" || user.role === "super_admin" ? (
        <ManagerPanel />
      ) : null}
      {user.role === "agent" ? <AgentPanel /> : null}
      {user.role === "adjuster" ? <AdjusterPanel /> : null}
      {user.role === "customer" ? <CustomerPanel /> : null}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {ROLE_LINKS[user.role].map((card) => (
          <Card key={card.title}>
            <p className="text-sm font-medium text-slate-500">{card.title}</p>
            <p className="mt-1 text-xs text-slate-400">{card.hint}</p>
            {card.to && (
              <Link
                to={card.to}
                className="mt-3 inline-block text-sm font-medium text-indigo-600 hover:underline"
              >
                Open →
              </Link>
            )}
          </Card>
        ))}
      </div>

      {user.role === "customer" ? (
        <ChatWidget context="customer_dashboard" />
      ) : null}
    </div>
  );
}

function Kpi({
  label,
  value,
  hint,
}: {
  label: string;
  value: string | number;
  hint?: string;
}) {
  return (
    <Card>
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
        {label}
      </p>
      <p className="mt-2 text-2xl font-semibold text-slate-900">{value}</p>
      {hint && <p className="mt-1 text-xs text-slate-400">{hint}</p>}
    </Card>
  );
}

function StatusBars({ items }: { items: NamedCount[] }) {
  const max = Math.max(1, ...items.map((i) => i.count));
  if (items.length === 0) {
    return <p className="text-sm text-slate-500">No claims yet.</p>;
  }
  return (
    <div className="space-y-2">
      {items.map((item) => (
        <div key={item.key}>
          <div className="mb-1 flex justify-between text-xs text-slate-600">
            <span className="capitalize">{item.label}</span>
            <span>{item.count}</span>
          </div>
          <div className="h-2 rounded bg-slate-100">
            <div
              className="h-2 rounded bg-indigo-500"
              style={{ width: `${(item.count / max) * 100}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

function monthAbbrev(ym: string): string {
  const [year, month] = ym.split("-").map(Number);
  if (!year || !month) return ym;
  return new Date(year, month - 1, 1).toLocaleString("en-US", { month: "short" });
}

function monthRangeLabel(points: MonthCount[]): string {
  if (points.length === 0) return "";
  const first = points[0].month.split("-").map(Number);
  const last = points[points.length - 1].month.split("-").map(Number);
  const fmt = (y: number, m: number) =>
    new Date(y, m - 1, 1).toLocaleString("en-US", {
      month: "short",
      year: "numeric",
    });
  return `${fmt(first[0], first[1])} – ${fmt(last[0], last[1])}`;
}

function yAxisTicks(max: number): number[] {
  if (max <= 5) {
    return Array.from({ length: max + 1 }, (_, i) => i);
  }
  const step = Math.ceil(max / 4);
  const ticks: number[] = [];
  for (let value = 0; value <= max; value += step) {
    ticks.push(value);
  }
  if (ticks[ticks.length - 1] !== max) {
    ticks.push(max);
  }
  return ticks;
}

function MonthChart({ points }: { points: MonthCount[] }) {
  if (points.length === 0) {
    return <p className="text-sm text-slate-500">No policies in this window.</p>;
  }

  const yMax = Math.max(1, ...points.map((p) => p.count));
  const ticks = yAxisTicks(yMax);
  const width = 720;
  const height = 240;
  const pad = { top: 24, right: 16, bottom: 40, left: 40 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const gap = 10;
  const barW = Math.max(12, (innerW - gap * (points.length - 1)) / points.length);
  const yOf = (count: number) => pad.top + innerH - (count / yMax) * innerH;
  const baseline = pad.top + innerH;

  return (
    <div>
      <p className="mb-2 text-xs text-slate-500">{monthRangeLabel(points)}</p>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="h-56 w-full"
        role="img"
        aria-label="New policies written by month"
      >
        {ticks.map((tick) => {
          const y = yOf(tick);
          return (
            <g key={tick}>
              <line
                x1={pad.left}
                x2={width - pad.right}
                y1={y}
                y2={y}
                stroke="#e2e8f0"
                strokeWidth="1"
              />
              <text
                x={pad.left - 8}
                y={y + 4}
                textAnchor="end"
                fontSize="12"
                fill="#475569"
              >
                {tick}
              </text>
            </g>
          );
        })}
        <line
          x1={pad.left}
          x2={width - pad.right}
          y1={baseline}
          y2={baseline}
          stroke="#94a3b8"
          strokeWidth="1.5"
        />
        {points.map((point, index) => {
          const x = pad.left + index * (barW + gap);
          const barH = (point.count / yMax) * innerH;
          const y = yOf(point.count);
          return (
            <g key={point.month}>
              {point.count > 0 ? (
                <rect
                  x={x}
                  y={y}
                  width={barW}
                  height={Math.max(barH, 2)}
                  rx="3"
                  fill="#4f46e5"
                />
              ) : null}
              {point.count > 0 ? (
                <text
                  x={x + barW / 2}
                  y={y - 6}
                  textAnchor="middle"
                  fontSize="12"
                  fontWeight="600"
                  fill="#1e293b"
                >
                  {point.count}
                </text>
              ) : null}
              <text
                x={x + barW / 2}
                y={baseline + 16}
                textAnchor="middle"
                fontSize="12"
                fill="#475569"
              >
                {monthAbbrev(point.month)}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function ManagerPanel() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["reports", "manager"],
    queryFn: async () => {
      const res = await api.get<Envelope<ManagerDashboard>>(
        "/reports/dashboard/manager",
      );
      return res.data.data!;
    },
  });

  if (isLoading) return <p className="text-sm text-slate-500">Loading KPIs…</p>;
  if (isError || !data) {
    return <p className="text-sm text-red-600">Could not load manager KPIs.</p>;
  }

  const ratio =
    data.loss_ratio_12m != null
      ? `${(Number(data.loss_ratio_12m) * 100).toFixed(1)}%`
      : "—";

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Kpi
          label="Active policies"
          value={data.active_policies_total}
          hint={data.active_policies_by_type
            .map((t) => `${t.label}: ${t.count}`)
            .join(" · ")}
        />
        <Kpi
          label="New policies (MTD)"
          value={data.new_policies_this_month}
          hint={`Last month: ${data.new_policies_last_month}`}
        />
        <Kpi
          label="Open claims"
          value={data.open_claims}
          hint={
            data.avg_days_to_close != null
              ? `Avg days to close: ${data.avg_days_to_close}`
              : "No closed claims yet"
          }
        />
        <Kpi
          label="Overdue installments"
          value={data.payments_overdue}
          hint={`Loss ratio (12m): ${ratio}`}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <p className="text-sm font-medium text-slate-700">
            Premium collected vs target (MTD)
          </p>
          <p className="mt-2 text-xl font-semibold text-slate-900">
            {formatMoney(data.premium_collected_mtd)}{" "}
            <span className="text-sm font-normal text-slate-500">
              / {formatMoney(data.premium_target_mtd)}
            </span>
          </p>
          <div className="mt-3 h-2 rounded bg-slate-100">
            <div
              className="h-2 rounded bg-emerald-500"
              style={{
                width: `${Math.min(
                  100,
                  Number(data.premium_target_mtd) > 0
                    ? (Number(data.premium_collected_mtd) /
                        Number(data.premium_target_mtd)) *
                      100
                    : 0,
                )}%`,
              }}
            />
          </div>
        </Card>

        <Card>
          <p className="mb-3 text-sm font-medium text-slate-700">
            Claims by status
          </p>
          <StatusBars items={data.claims_by_status} />
        </Card>
      </div>

      <Card>
        <p className="mb-1 text-sm font-medium text-slate-700">
          New policies (12 months)
        </p>
        <MonthChart points={data.new_policies_sparkline} />
      </Card>

      <Card className="p-0">
        <div className="border-b border-slate-200 px-4 py-3 text-sm font-medium text-slate-700">
          Top agents by policies written
        </div>
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-2">Agent</th>
              <th className="px-4 py-2">Policies</th>
              <th className="px-4 py-2">Annual premium</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {data.top_agents.length === 0 && (
              <tr>
                <td colSpan={3} className="px-4 py-4 text-slate-500">
                  No agent production yet.
                </td>
              </tr>
            )}
            {data.top_agents.map((row) => (
              <tr key={row.agent_id}>
                <td className="px-4 py-2 font-medium text-slate-800">
                  {row.agent_name}
                </td>
                <td className="px-4 py-2">{row.policies_written}</td>
                <td className="px-4 py-2">
                  {formatMoney(row.annual_premium)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

function AgentPanel() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["reports", "agent"],
    queryFn: async () => {
      const res = await api.get<Envelope<AgentDashboard>>(
        "/reports/dashboard/agent",
      );
      return res.data.data!;
    },
  });

  if (isLoading) return <p className="text-sm text-slate-500">Loading KPIs…</p>;
  if (isError || !data) {
    return <p className="text-sm text-red-600">Could not load agent KPIs.</p>;
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Kpi
          label="My customers"
          value={data.customers_total}
          hint={`New this month: ${data.customers_new_this_month}`}
        />
        <Kpi label="Active policies" value={data.policies_active} />
        <Kpi label="Expiring in 30 days" value={data.policies_expiring_30d} />
        <Kpi label="Pending quote approvals" value={data.pending_quote_approvals} />
      </div>
      <Card className="p-0">
        <div className="border-b border-slate-200 px-4 py-3 text-sm font-medium text-slate-700">
          Recent activity
        </div>
        <ul className="divide-y divide-slate-100">
          {data.recent_activity.length === 0 && (
            <li className="px-4 py-4 text-sm text-slate-500">No recent activity.</li>
          )}
          {data.recent_activity.map((item) => (
            <li key={item.id} className="flex justify-between gap-4 px-4 py-3 text-sm">
              <div>
                <p className="font-mono text-xs text-indigo-700">{item.action}</p>
                <p className="text-slate-500">
                  {item.summary || `${item.entity_type} ${item.entity_id.slice(0, 8)}…`}
                </p>
              </div>
              <span className="whitespace-nowrap text-xs text-slate-400">
                {new Date(item.created_at).toLocaleString()}
              </span>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

function AdjusterPanel() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["reports", "adjuster"],
    queryFn: async () => {
      const res = await api.get<Envelope<AdjusterDashboard>>(
        "/reports/dashboard/adjuster",
      );
      return res.data.data!;
    },
  });

  if (isLoading) return <p className="text-sm text-slate-500">Loading queue…</p>;
  if (isError || !data) {
    return <p className="text-sm text-red-600">Could not load adjuster KPIs.</p>;
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Kpi label="Assigned open claims" value={data.assigned_queue.length} />
        <Kpi label="Awaiting info" value={data.awaiting_info.length} />
        <Kpi
          label="Closed this month"
          value={data.claims_closed_this_month}
          hint={
            data.avg_days_to_resolution_personal != null
              ? `Your avg: ${data.avg_days_to_resolution_personal}d · Team: ${data.avg_days_to_resolution_team ?? "—"}d`
              : `Team avg: ${data.avg_days_to_resolution_team ?? "—"}d`
          }
        />
      </div>
      <Card className="p-0">
        <div className="border-b border-slate-200 px-4 py-3 text-sm font-medium text-slate-700">
          Priority queue
        </div>
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-2">Claim</th>
              <th className="px-4 py-2">Status</th>
              <th className="px-4 py-2">Age</th>
              <th className="px-4 py-2">Estimate</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {data.assigned_queue.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-4 text-slate-500">
                  Queue is clear.
                </td>
              </tr>
            )}
            {data.assigned_queue.slice(0, 10).map((item) => (
              <tr key={item.id}>
                <td className="px-4 py-2">
                  <Link
                    to={`/claims/${item.id}`}
                    className="font-medium text-indigo-600 hover:underline"
                  >
                    {item.claim_number}
                  </Link>
                  {item.fraud_flag && (
                    <span className="ml-2 rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700">
                      Fraud
                    </span>
                  )}
                </td>
                <td className="px-4 py-2 capitalize">
                  {item.status.replace(/_/g, " ")}
                  {item.days_info_remaining != null && (
                    <span className="ml-1 text-xs text-amber-600">
                      ({item.days_info_remaining}d left)
                    </span>
                  )}
                </td>
                <td className="px-4 py-2">{item.age_days}d</td>
                <td className="px-4 py-2">
                  {item.estimated_damage
                    ? formatMoney(item.estimated_damage)
                    : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

function CustomerPanel() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["reports", "customer"],
    queryFn: async () => {
      const res = await api.get<Envelope<CustomerDashboard>>(
        "/reports/dashboard/customer",
      );
      return res.data.data!;
    },
  });

  if (isLoading) return <p className="text-sm text-slate-500">Loading…</p>;
  if (isError || !data) {
    return <p className="text-sm text-red-600">Could not load your dashboard.</p>;
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Kpi label="Active policies" value={data.active_policies.length} />
        <Kpi label="Open claims" value={data.open_claims.length} />
        <Kpi label="Unread notifications" value={data.unread_notifications} />
        <Kpi label="Recent payments" value={data.recent_payments.length} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-0">
          <div className="border-b border-slate-200 px-4 py-3 text-sm font-medium text-slate-700">
            Your policies
          </div>
          <ul className="divide-y divide-slate-100">
            {data.active_policies.length === 0 && (
              <li className="px-4 py-4 text-sm text-slate-500">No active policies.</li>
            )}
            {data.active_policies.map((p) => (
              <li key={p.id} className="px-4 py-3 text-sm">
                <Link
                  to={`/policies/${p.id}`}
                  className="font-medium text-indigo-600 hover:underline"
                >
                  {p.policy_number}
                </Link>
                <p className="text-xs capitalize text-slate-500">
                  {p.policy_type}
                  {p.next_payment_date
                    ? ` · Next payment ${p.next_payment_date}${
                        p.next_payment_amount
                          ? ` (${formatMoney(p.next_payment_amount)})`
                          : ""
                      }`
                    : ""}
                </p>
              </li>
            ))}
          </ul>
        </Card>

        <Card className="p-0">
          <div className="border-b border-slate-200 px-4 py-3 text-sm font-medium text-slate-700">
            Open claims
          </div>
          <ul className="divide-y divide-slate-100">
            {data.open_claims.length === 0 && (
              <li className="px-4 py-4 text-sm text-slate-500">No open claims.</li>
            )}
            {data.open_claims.map((c) => (
              <li key={c.id} className="px-4 py-3 text-sm">
                <Link
                  to={`/claims/${c.id}`}
                  className="font-medium text-indigo-600 hover:underline"
                >
                  {c.claim_number}
                </Link>
                <p className="text-xs capitalize text-slate-500">
                  {c.status.replace(/_/g, " ")} · Incident {c.incident_date}
                </p>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}
