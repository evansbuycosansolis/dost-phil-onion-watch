"use client";

import { apiFetch, downloadReportFile, useReports } from "@phil-onion-watch/api-client";
import { DataTable, ErrorState, LoadingState, PageHeader, SectionShell } from "@phil-onion-watch/ui";
import { useMutation, useQuery } from "@tanstack/react-query";

import { useAuth } from "../../../providers";

const REPORT_CATEGORIES = [
  "provincial_exec_summary",
  "municipality_summary",
  "warehouse_utilization",
  "price_trend",
  "alert_digest",
] as const;

export default function ReportsCenterPage() {
  const { token } = useAuth();
  const reports = useReports(token);
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

  if (reports.isLoading || overview.isLoading) return <LoadingState label="Loading reports center..." />;
  if (reports.error || overview.error) return <ErrorState message="Failed to load reports" />;

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
        </div>
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
                </div>
              ),
            },
          ]}
          rows={reports.data ?? []}
        />
      </SectionShell>
    </div>
  );
}
