"use client";

import {
  apiFetch,
  downloadReportFile,
  processReportDistributionQueue,
  queueReportDistribution,
  useDistributionDeliveries,
  useForecastDiagnostics,
  useReportRecipientGroups,
  useReports,
} from "@phil-onion-watch/api-client";
import { DataTable, ErrorState, LoadingState, PageHeader, SectionShell } from "@phil-onion-watch/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "../../../providers";

const REPORT_CATEGORIES = [
  "provincial_exec_summary",
  "municipality_summary",
  "warehouse_utilization",
  "price_trend",
  "alert_digest",
] as const;

export default function ReportsCenterPage() {
  const { token, user } = useAuth();
  const queryClient = useQueryClient();
  const reports = useReports(token);
  const recipientGroups = useReportRecipientGroups(token);
  const deliveries = useDistributionDeliveries(token, undefined, 100);
  const forecastDiagnostics = useForecastDiagnostics(token);
  const overview = useQuery({
    queryKey: ["dashboard-reports-overview", token],
    queryFn: () => apiFetch<Record<string, unknown>>("/api/v1/dashboard/reports/overview", { token }),
    enabled: !!token,
  });

  const generate = useMutation({
    mutationFn: (category: string) =>
      apiFetch("/api/v1/reports/generate", {
        token,
        method: "POST",
        body: { category, reporting_month: new Date().toISOString().slice(0, 10) },
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["reports", token] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard-reports-overview", token] }),
        queryClient.invalidateQueries({ queryKey: ["report-distribution-deliveries", token] }),
      ]);
    },
  });

  const download = useMutation({
    mutationFn: async ({ reportId, format }: { reportId: number; format: "csv" | "pdf" }) => {
      const blob = await downloadReportFile(token, reportId, format);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `report_${reportId}.${format}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    },
  });

  const queueDelivery = useMutation({
    mutationFn: (reportId: number) => queueReportDistribution(token, reportId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["report-distribution-deliveries", token] });
    },
  });

  const processDistribution = useMutation({
    mutationFn: () => processReportDistributionQueue(token, 100),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["report-distribution-deliveries", token] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard-reports-overview", token] }),
      ]);
    },
  });

  if (reports.isLoading || overview.isLoading || forecastDiagnostics.isLoading || recipientGroups.isLoading || deliveries.isLoading) {
    return <LoadingState label="Loading reports center..." />;
  }
  if (reports.error || overview.error || forecastDiagnostics.error || recipientGroups.error || deliveries.error) {
    return <ErrorState message="Failed to load reports" />;
  }

  const canManageDistribution = (user?.roles ?? []).some((role) => ["super_admin", "provincial_admin"].includes(role));

  const modelCounts = forecastDiagnostics.data?.selected_model_counts ?? {};
  const modelScores = forecastDiagnostics.data?.model_avg_score ?? {};
  const modelMae = forecastDiagnostics.data?.model_avg_holdout_mae ?? {};
  const distributionStatus = (overview.data?.report_distribution_status as Record<string, number>) ?? {};

  const diagnosticsRows = Object.keys(modelCounts).map((modelName) => ({
    model_name: modelName,
    selected_count: modelCounts[modelName],
    avg_score: Number(modelScores[modelName] ?? 0).toFixed(4),
    avg_holdout_mae: Number(modelMae[modelName] ?? 0).toFixed(4),
  }));

  const municipalitySnapshot = (forecastDiagnostics.data?.municipality_diagnostics ?? []).slice(0, 8).map((row) => ({
    municipality: row.municipality_name,
    selected_model: row.selected_model ?? "n/a",
    selected_score: row.selected_score == null ? "n/a" : Number(row.selected_score).toFixed(4),
    fallback_order: (row.fallback_order ?? []).join(" > "),
  }));

  return (
    <div>
      <PageHeader title="Reports Center" subtitle="Monthly executive summaries and generated report artifacts" />

      <SectionShell title="Generate Report">
        <div className="flex flex-wrap gap-2">
          {REPORT_CATEGORIES.map((category) => (
            <button
              key={category}
              onClick={() => generate.mutate(category)}
              className="rounded-md border border-brand-300 bg-brand-50 px-3 py-2 text-sm font-medium text-brand-700"
            >
              Generate {category}
            </button>
          ))}
          {canManageDistribution ? (
            <button
              onClick={() => processDistribution.mutate()}
              className="rounded-md border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm font-medium text-emerald-700"
            >
              Process Distribution Queue
            </button>
          ) : null}
        </div>
      </SectionShell>

      <SectionShell title="Distribution Queue Health">
        <DataTable
          columns={[{ key: "status", label: "Status" }, { key: "count", label: "Count" }]}
          rows={Object.entries(distributionStatus).map(([status, count]) => ({ status, count }))}
        />
      </SectionShell>

      <SectionShell title="Recipient Groups">
        <DataTable
          columns={[
            { key: "name", label: "Group" },
            { key: "report_category", label: "Category" },
            { key: "role_name", label: "Role" },
            { key: "organization_id", label: "Organization" },
            { key: "delivery_channel", label: "Channel" },
            { key: "export_format", label: "Format" },
            { key: "max_attempts", label: "Max Attempts" },
          ]}
          rows={recipientGroups.data ?? []}
        />
      </SectionShell>

      <SectionShell title="Forecast Model Diagnostics for Reporting">
        <DataTable
          columns={[
            { key: "model_name", label: "Model" },
            { key: "selected_count", label: "Selections" },
            { key: "avg_score", label: "Avg Score" },
            { key: "avg_holdout_mae", label: "Avg Holdout MAE" },
          ]}
          rows={diagnosticsRows}
        />
      </SectionShell>

      <SectionShell title="Municipality Selection Snapshot">
        <DataTable
          columns={[
            { key: "municipality", label: "Municipality" },
            { key: "selected_model", label: "Selected Model" },
            { key: "selected_score", label: "Selected Score" },
            { key: "fallback_order", label: "Fallback Order" },
          ]}
          rows={municipalitySnapshot}
        />
      </SectionShell>

      <SectionShell title="Monthly Executive Summary Cards">
        <DataTable
          columns={[{ key: "reporting_month", label: "Reporting Month" }, { key: "count", label: "Generated Reports" }]}
          rows={(overview.data?.monthly_summary as Record<string, unknown>[]) ?? []}
        />
      </SectionShell>

      <SectionShell title="Generated Report History">
        <DataTable
          columns={[
            { key: "title", label: "Title" },
            { key: "category", label: "Category" },
            { key: "reporting_month", label: "Month" },
            { key: "status", label: "Status" },
            { key: "file_path", label: "Artifact" },
            {
              key: "id",
              label: "Export",
              render: (row) => (
                <div className="flex gap-2">
                  <button
                    onClick={() => download.mutate({ reportId: Number(row.id), format: "csv" })}
                    className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-700"
                  >
                    CSV
                  </button>
                  <button
                    onClick={() => download.mutate({ reportId: Number(row.id), format: "pdf" })}
                    className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-700"
                  >
                    PDF
                  </button>
                  {canManageDistribution ? (
                    <button
                      onClick={() => queueDelivery.mutate(Number(row.id))}
                      className="rounded border border-emerald-300 px-2 py-1 text-xs text-emerald-700"
                    >
                      Queue Delivery
                    </button>
                  ) : null}
                </div>
              ),
            },
          ]}
          rows={reports.data ?? []}
        />
      </SectionShell>

      <SectionShell title="Recent Delivery Logs">
        <DataTable
          columns={[
            { key: "report_id", label: "Report ID" },
            { key: "recipient_email", label: "Recipient" },
            { key: "recipient_role", label: "Role" },
            { key: "status", label: "Status" },
            { key: "attempt_count", label: "Attempts" },
            { key: "delivery_channel", label: "Channel" },
            { key: "export_format", label: "Format" },
            { key: "last_error", label: "Last Error" },
            { key: "delivered_at", label: "Delivered At" },
          ]}
          rows={deliveries.data ?? []}
        />
      </SectionShell>
    </div>
  );
}
