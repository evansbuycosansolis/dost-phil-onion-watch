"use client";

import { apiFetch } from "@phil-onion-watch/api-client";
import { DataTable, EmptyState, ErrorState, LoadingState, PageHeader, SectionShell, StatCard } from "@phil-onion-watch/ui";
import { useQuery } from "@tanstack/react-query";

import { useAuth } from "../../../providers";

type OperatorOverview = {
  totals: {
    total_aois: number;
    active_aois: number;
    watchlist_aois: number;
    pipeline_runs: number;
    avg_queue_priority: number;
  };
  run_status_counts: Record<string, number>;
  stale_warning_runs: number;
  sla_breach_runs: number;
  latest_runs: Array<{
    id: number;
    run_type: string;
    status: string;
    queue_priority: number;
    started_at: string | null;
    retry_strategy: string;
  }>;
};

export default function GeospatialOperatorPage() {
  const { token } = useAuth();

  const overview = useQuery({
    queryKey: ["geospatial-operator-overview", token],
    queryFn: () => apiFetch<OperatorOverview>("/api/v1/geospatial/dashboard/operator", { token }),
    enabled: !!token,
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Geospatial Operations"
        subtitle="Operator-level KPI dashboard for AOI surveillance runs, queue health, and diagnostics coverage."
        actions={
          <div className="flex items-center gap-2 text-sm">
            <a href="/dashboard/geospatial/executive" className="rounded border border-slate-300 px-3 py-1 font-medium text-slate-700 hover:bg-slate-50">
              Executive KPIs
            </a>
            <a href="/dashboard/geospatial/intelligence" className="rounded border border-slate-300 px-3 py-1 font-medium text-slate-700 hover:bg-slate-50">
              Intelligence Console
            </a>
            <a href="/dashboard/geospatial/aois" className="rounded border border-slate-300 px-3 py-1 font-medium text-slate-700 hover:bg-slate-50">
              AOI Workbench
            </a>
          </div>
        }
      />

      {overview.isLoading ? <LoadingState label="Loading geospatial KPIs..." /> : null}
      {overview.error ? <ErrorState message="Failed to load geospatial operator overview" /> : null}

      {overview.data ? (
        <>
          <div className="grid gap-4 md:grid-cols-5">
            <StatCard label="AOIs" value={overview.data.totals.total_aois} hint={`${overview.data.totals.active_aois} active`} />
            <StatCard label="Watchlist" value={overview.data.totals.watchlist_aois} hint="Flagged AOIs" />
            <StatCard label="Pipeline Runs" value={overview.data.totals.pipeline_runs} hint="Recent run sample" />
            <StatCard label="Avg Queue Priority" value={overview.data.totals.avg_queue_priority} hint="Lower = higher urgency" />
            <StatCard label="SLA Breaches" value={overview.data.sla_breach_runs} hint={`${overview.data.stale_warning_runs} stale warnings`} />
          </div>

          <SectionShell title="Run Status Mix">
            {Object.keys(overview.data.run_status_counts).length === 0 ? (
              <EmptyState title="No run statuses" description="No geospatial runs are currently available." />
            ) : (
              <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
                {Object.entries(overview.data.run_status_counts).map(([status, count]) => (
                  <div key={status} className="rounded border border-slate-200 bg-slate-50 px-3 py-2">
                    <div className="text-xs uppercase tracking-wide text-slate-500">{status}</div>
                    <div className="mt-1 text-lg font-semibold text-slate-900">{count}</div>
                  </div>
                ))}
              </div>
            )}
          </SectionShell>

          <SectionShell title="Recent Runs">
            {overview.data.latest_runs.length === 0 ? (
              <EmptyState title="No runs found" description="Trigger an ingest or feature refresh run to populate this table." />
            ) : (
              <DataTable
                columns={[
                  { key: "id", label: "Run ID", render: (row) => <a href={`/dashboard/geospatial/runs/${String((row as { id: number }).id)}`} className="font-medium text-sky-700 hover:underline">#{String((row as { id: number }).id)}</a> },
                  { key: "run_type", label: "Type" },
                  { key: "status", label: "Status" },
                  { key: "queue_priority", label: "Priority" },
                  { key: "retry_strategy", label: "Retry" },
                  { key: "started_at", label: "Started" },
                ]}
                rows={overview.data.latest_runs as unknown as Record<string, unknown>[]}
              />
            )}
          </SectionShell>
        </>
      ) : null}
    </div>
  );
}
