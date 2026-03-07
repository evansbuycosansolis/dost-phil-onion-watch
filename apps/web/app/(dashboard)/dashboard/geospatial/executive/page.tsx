"use client";

import { apiFetch } from "@phil-onion-watch/api-client";
import { DataTable, EmptyState, ErrorState, LoadingState, PageHeader, SectionShell, StatCard } from "@phil-onion-watch/ui";
import { useQuery } from "@tanstack/react-query";

import { useAuth } from "../../../../providers";

type ExecutiveDashboard = {
  as_of: string;
  totals: {
    total_aois: number;
    active_aois: number;
    watchlist_aois: number;
    runs_30d: number;
    run_success_rate_30d: number;
    avg_run_duration_seconds_30d: number;
    avg_observation_confidence_90d: number;
    stale_aois: number;
    high_risk_aois: number;
  };
  monthly_run_trend: Array<{
    month: string;
    run_count: number;
    completed_count: number;
    success_rate: number;
  }>;
  top_anomaly_aois: Array<{
    aoi_id: number;
    aoi_code: string | null;
    aoi_name: string | null;
    municipality_id: number | null;
    anomaly_score: number;
    sample_count: number;
  }>;
  source_reliability: Array<{
    source: string;
    scene_count: number;
    feature_count: number;
    avg_cloud_score: number;
    avg_confidence_score: number;
    reliability_score: number;
  }>;
};

function percent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

export default function GeospatialExecutiveDashboardPage() {
  const { token } = useAuth();

  const executive = useQuery({
    queryKey: ["geospatial-executive-dashboard", token],
    queryFn: () => apiFetch<ExecutiveDashboard>("/api/v1/geospatial/dashboard/executive", { token }),
    enabled: !!token,
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Geospatial KPI Executive Dashboard"
        subtitle="Executive summary for run performance, AOI surveillance health, anomaly concentration, and source reliability."
        actions={
          <div className="flex items-center gap-2 text-sm">
            <a href="/dashboard/geospatial" className="rounded border border-slate-300 px-3 py-1 font-medium text-slate-700 hover:bg-slate-50">
              Operator KPIs
            </a>
            <a href="/dashboard/geospatial/aois" className="rounded border border-slate-300 px-3 py-1 font-medium text-slate-700 hover:bg-slate-50">
              AOI Workbench
            </a>
          </div>
        }
      />

      {executive.isLoading ? <LoadingState label="Loading executive geospatial KPIs..." /> : null}
      {executive.error ? <ErrorState message="Failed to load geospatial executive dashboard" /> : null}

      {executive.data ? (
        <>
          <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-5">
            <StatCard label="AOIs" value={executive.data.totals.total_aois} hint={`${executive.data.totals.active_aois} active`} />
            <StatCard label="Watchlist AOIs" value={executive.data.totals.watchlist_aois} hint={`${executive.data.totals.stale_aois} stale`} />
            <StatCard label="Runs (30d)" value={executive.data.totals.runs_30d} hint={`Success ${percent(executive.data.totals.run_success_rate_30d)}`} />
            <StatCard label="Avg Run Duration" value={`${executive.data.totals.avg_run_duration_seconds_30d}s`} hint="30-day average" />
            <StatCard label="High-Risk AOIs" value={executive.data.totals.high_risk_aois} hint={`Confidence ${percent(executive.data.totals.avg_observation_confidence_90d)}`} />
          </div>

          <SectionShell title="Monthly Run Performance">
            {executive.data.monthly_run_trend.length === 0 ? (
              <EmptyState title="No run trend data" description="No recent run data is available for the selected executive window." />
            ) : (
              <DataTable
                columns={[
                  { key: "month", label: "Month" },
                  { key: "run_count", label: "Runs" },
                  { key: "completed_count", label: "Completed" },
                  { key: "success_rate", label: "Success Rate", render: (row) => percent(Number((row as { success_rate: number }).success_rate ?? 0)) },
                ]}
                rows={executive.data.monthly_run_trend as unknown as Record<string, unknown>[]}
              />
            )}
          </SectionShell>

          <div className="grid gap-4 xl:grid-cols-2">
            <SectionShell title="Top Anomaly AOIs">
              {executive.data.top_anomaly_aois.length === 0 ? (
                <EmptyState title="No anomaly hotspots" description="No anomaly concentration rows are available in the current window." />
              ) : (
                <DataTable
                  columns={[
                    { key: "aoi_code", label: "AOI" },
                    { key: "aoi_name", label: "Name" },
                    { key: "municipality_id", label: "Municipality" },
                    { key: "anomaly_score", label: "Anomaly Score" },
                    { key: "sample_count", label: "Samples" },
                  ]}
                  rows={executive.data.top_anomaly_aois as unknown as Record<string, unknown>[]}
                />
              )}
            </SectionShell>

            <SectionShell title="Source Reliability Scorecard">
              {executive.data.source_reliability.length === 0 ? (
                <EmptyState title="No source reliability data" description="No scenes/features are available to score source reliability." />
              ) : (
                <DataTable
                  columns={[
                    { key: "source", label: "Source" },
                    { key: "scene_count", label: "Scenes" },
                    { key: "feature_count", label: "Features" },
                    { key: "avg_cloud_score", label: "Avg Cloud" },
                    { key: "avg_confidence_score", label: "Avg Confidence" },
                    { key: "reliability_score", label: "Reliability" },
                  ]}
                  rows={executive.data.source_reliability as unknown as Record<string, unknown>[]}
                />
              )}
            </SectionShell>
          </div>
        </>
      ) : null}
    </div>
  );
}

