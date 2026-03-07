"use client";

import { apiFetch } from "@phil-onion-watch/api-client";
import { DataTable, EmptyState, ErrorState, LoadingState, PageHeader, SectionShell, StatCard } from "@phil-onion-watch/ui";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";

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
  executive_municipality_summary_board: Array<{
    municipality_id: number;
    aoi_count: number;
    avg_anomaly_score: number;
    sample_count: number;
  }>;
  executive_top_risk_aoi_digest: Array<{
    aoi_id: number;
    aoi_code: string | null;
    risk_level: string;
    anomaly_score: number;
    sample_count: number;
  }>;
  executive_supply_impact_estimator: {
    score: number;
    high_risk_aoi_count: number;
    warehouse_stock_tons_30d: number;
    import_volume_tons_30d: number;
  };
  executive_intervention_planning_board: Array<{
    priority: number;
    municipality_id: number;
    recommended_intervention: string;
    risk_score: number;
  }>;
};

type ExecutiveAnomalyBrief = {
  id: number | null;
  title: string | null;
  generated_at: string | null;
  summary: string | null;
  highlights: string[];
  top_risk_aois: Array<{
    aoi_id: number;
    aoi_code: string | null;
    aoi_name: string | null;
    anomaly_score: number;
    sample_count: number;
  }>;
};

function percent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

export default function GeospatialExecutiveDashboardPage() {
  const { token } = useAuth();
  const [message, setMessage] = useState("");

  const executive = useQuery({
    queryKey: ["geospatial-executive-dashboard", token],
    queryFn: () => apiFetch<ExecutiveDashboard>("/api/v1/geospatial/dashboard/executive", { token }),
    enabled: !!token,
  });
  const latestBrief = useQuery({
    queryKey: ["geospatial-executive-anomaly-brief-latest", token],
    queryFn: () => apiFetch<ExecutiveAnomalyBrief>("/api/v1/geospatial/dashboard/executive/anomaly-brief/latest", { token }),
    enabled: !!token,
  });
  const generateBrief = useMutation({
    mutationFn: () => apiFetch<ExecutiveAnomalyBrief>("/api/v1/geospatial/dashboard/executive/anomaly-brief/generate", { token, method: "POST" }),
    onSuccess: async () => {
      setMessage("Executive anomaly brief generated");
      await latestBrief.refetch();
    },
    onError: () => setMessage("Executive anomaly brief generation failed"),
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

      {message ? <div className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">{message}</div> : null}
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

          <div className="grid gap-4 xl:grid-cols-2">
            <SectionShell title="Executive Municipality Summary Board">
              <DataTable
                columns={[
                  { key: "municipality_id", label: "Municipality" },
                  { key: "aoi_count", label: "AOIs" },
                  { key: "avg_anomaly_score", label: "Avg Anomaly" },
                  { key: "sample_count", label: "Samples" },
                ]}
                rows={executive.data.executive_municipality_summary_board as unknown as Record<string, unknown>[]}
              />
            </SectionShell>
            <SectionShell title="Executive Top-risk AOI Digest">
              <DataTable
                columns={[
                  { key: "aoi_code", label: "AOI" },
                  { key: "risk_level", label: "Risk" },
                  { key: "anomaly_score", label: "Anomaly" },
                  { key: "sample_count", label: "Samples" },
                ]}
                rows={executive.data.executive_top_risk_aoi_digest as unknown as Record<string, unknown>[]}
              />
            </SectionShell>
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <SectionShell title="Executive Supply Impact Estimator">
              <div className="grid gap-3 md:grid-cols-2">
                <StatCard label="Impact Score" value={executive.data.executive_supply_impact_estimator.score} hint="0-1 risk-weighted" />
                <StatCard label="High-risk AOIs" value={executive.data.executive_supply_impact_estimator.high_risk_aoi_count} hint="Current window" />
                <StatCard label="Warehouse Stock (30d)" value={executive.data.executive_supply_impact_estimator.warehouse_stock_tons_30d} hint="tons" />
                <StatCard label="Import Volume (30d)" value={executive.data.executive_supply_impact_estimator.import_volume_tons_30d} hint="tons" />
              </div>
            </SectionShell>
            <SectionShell title="Executive Intervention Planning Board">
              <DataTable
                columns={[
                  { key: "priority", label: "Priority" },
                  { key: "municipality_id", label: "Municipality" },
                  { key: "recommended_intervention", label: "Intervention" },
                  { key: "risk_score", label: "Risk Score" },
                ]}
                rows={executive.data.executive_intervention_planning_board as unknown as Record<string, unknown>[]}
              />
            </SectionShell>
          </div>

          <SectionShell title="Executive Anomaly Brief Generator">
            {latestBrief.isLoading ? <LoadingState label="Loading latest anomaly brief..." /> : null}
            {latestBrief.error ? <ErrorState message="Failed to load executive anomaly brief" /> : null}
            <div className="flex flex-wrap items-center gap-2">
              <button type="button" onClick={() => generateBrief.mutate()} className="rounded border border-slate-300 px-3 py-1 text-sm font-medium text-slate-700 hover:bg-slate-50">
                Generate anomaly brief
              </button>
            </div>
            {latestBrief.data && latestBrief.data.id ? (
              <div className="mt-3 space-y-3 text-sm text-slate-700">
                <div className="rounded border border-slate-200 bg-slate-50 px-3 py-2">
                  <div className="font-medium text-slate-900">{latestBrief.data.title}</div>
                  <div className="text-xs text-slate-500">Generated at {latestBrief.data.generated_at ?? "n/a"}</div>
                  <p className="mt-2">{latestBrief.data.summary}</p>
                </div>
                <DataTable
                  columns={[
                    { key: "aoi_code", label: "AOI" },
                    { key: "aoi_name", label: "Name" },
                    { key: "anomaly_score", label: "Anomaly Score" },
                    { key: "sample_count", label: "Samples" },
                  ]}
                  rows={latestBrief.data.top_risk_aois as unknown as Record<string, unknown>[]}
                />
              </div>
            ) : (
              <EmptyState title="No anomaly brief yet" description="Generate the first executive anomaly brief for this environment." />
            )}
          </SectionShell>
        </>
      ) : null}
    </div>
  );
}
