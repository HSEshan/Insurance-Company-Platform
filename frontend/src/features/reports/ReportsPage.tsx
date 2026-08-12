import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { api, getErrorMessage } from "../../lib/api";
import { Button, Card } from "../../components/ui";
import type { Envelope, LossRatioRow } from "../../types";
import { formatMoney } from "../../types";

async function downloadReport(
  path: string,
  filename: string,
  params?: Record<string, string | undefined>,
) {
  const res = await api.get(path, {
    params,
    responseType: "blob",
  });
  const url = URL.createObjectURL(res.data as Blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function ReportsPage() {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const { data: lossRows } = useQuery({
    queryKey: ["reports", "loss-ratio"],
    queryFn: async () => {
      const res = await api.get<Envelope<LossRatioRow[]>>("/reports/loss-ratio");
      return res.data.data ?? [];
    },
  });

  async function run(key: string, fn: () => Promise<void>) {
    setError(null);
    setBusy(key);
    try {
      await fn();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  const reports = [
    {
      key: "claims",
      title: "Claims by status / date",
      description: "All claims with status, amounts, and policy context.",
      action: () =>
        downloadReport("/reports/claims-summary", "claims-summary.csv"),
    },
    {
      key: "billing",
      title: "Premium billing summary",
      description: "Installments due in the current month.",
      action: () =>
        downloadReport("/reports/billing-summary", "billing-summary.csv"),
    },
    {
      key: "loss",
      title: "Loss ratio by product line",
      description: "Rolling 12-month premium vs claim payouts.",
      action: () =>
        downloadReport("/reports/loss-ratio/export", "loss-ratio.csv"),
    },
    {
      key: "agents",
      title: "Agent production",
      description: "Policies written and annual premium by agent.",
      action: () =>
        downloadReport("/reports/agent-production", "agent-production.csv"),
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-slate-800">Reports</h2>
        <p className="mt-1 text-sm text-slate-500">
          Downloadable CSV summaries for managers and compliance review.
        </p>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="grid gap-4 md:grid-cols-2">
        {reports.map((report) => (
          <Card key={report.key}>
            <p className="text-sm font-medium text-slate-800">{report.title}</p>
            <p className="mt-1 text-xs text-slate-500">{report.description}</p>
            <Button
              className="mt-4"
              variant="secondary"
              loading={busy === report.key}
              onClick={() => run(report.key, report.action)}
            >
              <Download className="h-4 w-4" />
              Download CSV
            </Button>
          </Card>
        ))}
      </div>

      <Card className="p-0">
        <div className="border-b border-slate-200 px-4 py-3 text-sm font-medium text-slate-700">
          Loss ratio by line (12 months)
        </div>
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-2">Line</th>
              <th className="px-4 py-2">Premium collected</th>
              <th className="px-4 py-2">Claims paid</th>
              <th className="px-4 py-2">Loss ratio</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {(lossRows ?? []).map((row) => (
              <tr key={row.policy_type}>
                <td className="px-4 py-2 capitalize">{row.policy_type}</td>
                <td className="px-4 py-2">
                  {formatMoney(row.premium_collected)}
                </td>
                <td className="px-4 py-2">{formatMoney(row.claims_paid)}</td>
                <td className="px-4 py-2">
                  {row.loss_ratio != null
                    ? `${(Number(row.loss_ratio) * 100).toFixed(1)}%`
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
