"use client";

import { apiFetch } from "@phil-onion-watch/api-client";
import { apiConfig } from "@phil-onion-watch/config";
import { Card, DataTable, EmptyState, ErrorState, LoadingState, PageHeader, SectionShell, StatCard } from "@phil-onion-watch/ui";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { useAuth } from "../../../../providers";

type Aoi = { id: number; code: string; name: string };
type Run = { id: number; run_type: string; status: string; started_at: string | null };

function useDownload(token?: string | null) {
  return async (path: string, filename: string) => {
    const response = await fetch(`${apiConfig.baseUrl}${path}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!response.ok) throw new Error(`download-${response.status}`);
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  };
}

export default function GeospatialIntelligencePage() {
  const { token } = useAuth();
  const download = useDownload(token);
  const [message, setMessage] = useState("");
  const [selectedAoiId, setSelectedAoiId] = useState<number | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);

  const aois = useQuery({
    queryKey: ["geo-intelligence-aois", token],
    queryFn: () => apiFetch<Aoi[]>("/api/v1/geospatial/aois?is_active=true", { token }),
    enabled: !!token,
  });
  const runs = useQuery({
    queryKey: ["geo-intelligence-runs", token],
    queryFn: () => apiFetch<Run[]>("/api/v1/geospatial/runs?limit=20", { token }),
    enabled: !!token,
  });

  const activeAoiId = selectedAoiId ?? aois.data?.[0]?.id ?? null;
  const activeRunId = selectedRunId ?? runs.data?.[0]?.id ?? null;

  const surveillance = useQuery({
    queryKey: ["geo-intelligence-surveillance", token, activeAoiId],
    queryFn: () => apiFetch<Record<string, unknown>>(`/api/v1/geospatial/aois/${activeAoiId}/surveillance/overview`, { token }),
    enabled: !!token && !!activeAoiId,
  });
  const aoiOps = useQuery({
    queryKey: ["geo-intelligence-aoi-ops", token, activeAoiId],
    queryFn: () => apiFetch<Record<string, unknown>>(`/api/v1/geospatial/aois/${activeAoiId}/operations/overview`, { token }),
    enabled: !!token && !!activeAoiId,
  });
  const multiAoi = useQuery({
    queryKey: ["geo-intelligence-multi-aoi", token, aois.data?.map((row) => row.id).join(",")],
    queryFn: () =>
      apiFetch<Record<string, unknown>>("/api/v1/geospatial/dashboard/multi-aoi/overview", {
        token,
        method: "POST",
        body: { aoi_ids: (aois.data ?? []).slice(0, 12).map((row) => row.id) },
      }),
    enabled: !!token && !!aois.data?.length,
  });
  const runOps = useQuery({
    queryKey: ["geo-intelligence-run-ops", token, activeRunId],
    queryFn: () => apiFetch<Record<string, unknown>>(`/api/v1/geospatial/runs/${activeRunId}/operations/command-center`, { token }),
    enabled: !!token && !!activeRunId,
  });
  const sceneIntel = useQuery({
    queryKey: ["geo-intelligence-scene-intel", token, activeRunId],
    queryFn: () => apiFetch<Record<string, unknown>>(`/api/v1/geospatial/runs/${activeRunId}/scene-intelligence`, { token }),
    enabled: !!token && !!activeRunId,
  });
  const featureIntel = useQuery({
    queryKey: ["geo-intelligence-feature-intel", token, activeRunId],
    queryFn: () => apiFetch<Record<string, unknown>>(`/api/v1/geospatial/runs/${activeRunId}/feature-intelligence`, { token }),
    enabled: !!token && !!activeRunId,
  });
  const configHealth = useQuery({
    queryKey: ["geo-intelligence-config-health", token],
    queryFn: () => apiFetch<Record<string, unknown>>("/api/v1/geospatial/dashboard/config-health", { token }),
    enabled: !!token,
  });
  const selfTest = useQuery({
    queryKey: ["geo-intelligence-self-test", token],
    queryFn: () => apiFetch<Record<string, unknown>>("/api/v1/geospatial/dashboard/self-test", { token }),
    enabled: !!token,
  });
  const operationsCenter = useQuery({
    queryKey: ["geo-intelligence-operations-center", token],
    queryFn: () => apiFetch<Record<string, unknown>>("/api/v1/geospatial/dashboard/operations-center", { token }),
    enabled: !!token,
  });

  const reviewMutation = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/geospatial/aois/${activeAoiId}/operations/review`, {
        token,
        method: "POST",
        body: { action: "verify", status: "approved", reason: "Analyst verified", feature_id: 0 },
      }),
    onSuccess: async () => {
      setMessage("AOI review workflow updated");
      await aoiOps.refetch();
    },
  });
  const fieldVisitMutation = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/geospatial/aois/${activeAoiId}/operations/field-visit`, {
        token,
        method: "POST",
        body: { action: "request", notes: "Field visit requested from intelligence console" },
      }),
    onSuccess: async () => {
      setMessage("Field visit request captured");
      await aoiOps.refetch();
    },
  });
  const weeklyDigestMutation = useMutation({
    mutationFn: () => apiFetch("/api/v1/geospatial/dashboard/weekly-digest/generate", { token, method: "POST" }),
    onSuccess: () => setMessage("Weekly digest generated"),
  });
  const monthlyReportMutation = useMutation({
    mutationFn: () => apiFetch("/api/v1/geospatial/dashboard/monthly-performance/generate", { token, method: "POST" }),
    onSuccess: () => setMessage("Monthly performance report generated"),
  });

  const firstFeatureId = useMemo(() => {
    const rows = (featureIntel.data?.rows as Array<{ feature_id?: number }> | undefined) ?? [];
    return rows[0]?.feature_id ?? null;
  }, [featureIntel.data]);

  const annotateFeatureMutation = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/geospatial/features/${firstFeatureId}/annotation`, {
        token,
        method: "POST",
        body: { annotation: "Validated from intelligence page", label: "analyst-note" },
      }),
    onSuccess: async () => {
      setMessage("Feature annotation saved");
      await featureIntel.refetch();
    },
  });
  const reviewFeatureMutation = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/geospatial/features/${firstFeatureId}/review`, {
        token,
        method: "POST",
        body: { decision: "approved", notes: "Approved in intelligence page" },
      }),
    onSuccess: async () => {
      setMessage("Feature review updated");
      await featureIntel.refetch();
    },
  });
  const recalibrateFeatureMutation = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/geospatial/features/${firstFeatureId}/recalibrate`, {
        token,
        method: "POST",
        body: { target_confidence: 0.82 },
      }),
    onSuccess: async () => {
      setMessage("Feature confidence recalibrated");
      await featureIntel.refetch();
    },
  });

  const multiRanking = ((multiAoi.data?.multi_aoi_anomaly_ranking_table as Record<string, unknown>[] | undefined) ?? []).slice(0, 10);
  const sceneRows = ((sceneIntel.data?.rows as Record<string, unknown>[] | undefined) ?? []).slice(0, 12);
  const featureRows = ((featureIntel.data?.rows as Record<string, unknown>[] | undefined) ?? []).slice(0, 12);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Geospatial Intelligence Console"
        subtitle="AOI surveillance analytics, multi-AOI compare, run operations command center, scene/feature intelligence, and platform diagnostics."
        actions={(
          <div className="flex flex-wrap gap-2 text-sm">
            <a href="/dashboard/geospatial" className="rounded border border-slate-300 px-3 py-1 font-medium text-slate-700 hover:bg-slate-50">Geo KPIs</a>
            <a href="/dashboard/geospatial/aois" className="rounded border border-slate-300 px-3 py-1 font-medium text-slate-700 hover:bg-slate-50">AOI workbench</a>
          </div>
        )}
      />

      {message ? <div className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">{message}</div> : null}

      <Card>
        <div className="grid gap-3 md:grid-cols-2">
          <label className="text-sm text-slate-700">
            AOI
            <select className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm" value={activeAoiId ?? ""} onChange={(event) => setSelectedAoiId(Number(event.target.value))}>
              {(aois.data ?? []).map((row) => <option key={row.id} value={row.id}>{row.code} · {row.name}</option>)}
            </select>
          </label>
          <label className="text-sm text-slate-700">
            Run
            <select className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm" value={activeRunId ?? ""} onChange={(event) => setSelectedRunId(Number(event.target.value))}>
              {(runs.data ?? []).map((row) => <option key={row.id} value={row.id}>#{row.id} · {row.run_type} · {row.status}</option>)}
            </select>
          </label>
        </div>
      </Card>

      <SectionShell title="AOI Surveillance and Operations">
        {surveillance.isLoading || aoiOps.isLoading ? <LoadingState label="Loading AOI surveillance intelligence..." /> : null}
        {surveillance.error || aoiOps.error ? <ErrorState message="Failed to load AOI surveillance/operations intelligence" /> : null}
        {surveillance.data && aoiOps.data ? (
          <div className="space-y-4">
            <div className="grid gap-4 md:grid-cols-4">
              <StatCard label="Anomaly Score" value={String(surveillance.data.aoi_confidence_adjusted_anomaly_score ?? "0")} hint="Confidence-adjusted" />
              <StatCard label="Cloud-free Obs" value={String(surveillance.data.aoi_cloud_free_observation_counter ?? "0")} hint="Counter" />
              <StatCard label="Baseline Deviation" value={String(surveillance.data.aoi_baseline_deviation_score ?? "0")} hint="AOI vs municipality" />
              <StatCard label="Crop Stage" value={String((surveillance.data.aoi_crop_stage_classifier_badge as { stage?: string } | undefined)?.stage ?? "unknown")} hint="Classifier badge" />
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <Card title="Heatmaps">
                <div className="space-y-1 text-xs text-slate-700">
                  <div>Anomaly density: {JSON.stringify((surveillance.data.aoi_heatmap_by_anomaly_density as { values?: unknown } | undefined)?.values ?? [])}</div>
                  <div>Confidence score: {JSON.stringify((surveillance.data.aoi_heatmap_by_confidence_score as { values?: unknown } | undefined)?.values ?? [])}</div>
                  <div>Cloud contamination: {JSON.stringify((surveillance.data.aoi_heatmap_by_cloud_contamination as { values?: unknown } | undefined)?.values ?? [])}</div>
                </div>
              </Card>
              <Card title="AOI Operations Controls">
                <div className="space-y-2 text-xs text-slate-700">
                  <div>Verification badge: {String((aoiOps.data.aoi_analyst_verification_badge as { verified?: boolean } | undefined)?.verified ?? false)}</div>
                  <div>Field visit status: {String((aoiOps.data.aoi_field_visit_request_action as { status?: string } | undefined)?.status ?? "idle")}</div>
                  <div>SLA targets: {JSON.stringify(aoiOps.data.aoi_sla_target_settings ?? {})}</div>
                  <div className="flex flex-wrap gap-2">
                    <button type="button" onClick={() => reviewMutation.mutate()} className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50">Verify anomaly</button>
                    <button type="button" onClick={() => fieldVisitMutation.mutate()} className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50">Request field visit</button>
                    <button
                      type="button"
                      onClick={async () => {
                        if (!activeAoiId) return;
                        try {
                          await download(`/api/v1/geospatial/aois/${activeAoiId}/operations/offline-packet`, `aoi-${activeAoiId}-offline-packet.json`);
                          setMessage("Offline observation packet exported");
                        } catch {
                          setMessage("Offline observation packet export failed");
                        }
                      }}
                      className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50"
                    >
                      Export offline packet
                    </button>
                  </div>
                </div>
              </Card>
            </div>
          </div>
        ) : null}
      </SectionShell>

      <SectionShell title="Multi-AOI Compare and Leaderboards">
        {multiAoi.isLoading ? <LoadingState label="Loading multi-AOI intelligence..." /> : null}
        {multiAoi.error ? <ErrorState message="Failed to load multi-AOI intelligence" /> : null}
        {multiAoi.data ? (
          <div className="space-y-3">
            <div className="grid gap-4 md:grid-cols-3">
              <StatCard label="Selected AOIs" value={String((multiAoi.data.multi_aoi_bulk_compare_dashboard as { selected_count?: number } | undefined)?.selected_count ?? 0)} hint="Bulk compare dashboard" />
              <StatCard label="Avg Confidence" value={String((multiAoi.data.multi_aoi_bulk_compare_dashboard as { avg_confidence?: number } | undefined)?.avg_confidence ?? 0)} hint="Aggregate trend context" />
              <StatCard label="Avg Anomaly" value={String((multiAoi.data.multi_aoi_bulk_compare_dashboard as { avg_anomaly?: number } | undefined)?.avg_anomaly ?? 0)} hint="Ranking signal" />
            </div>
            {multiRanking.length === 0 ? (
              <EmptyState title="No multi-AOI ranking data" description="No AOI ranking rows are available yet." />
            ) : (
              <DataTable
                columns={[
                  { key: "aoi_code", label: "AOI" },
                  { key: "municipality_name", label: "Municipality" },
                  { key: "avg_confidence", label: "Confidence" },
                  { key: "avg_anomaly", label: "Anomaly" },
                  { key: "stale", label: "Stale" },
                ]}
                rows={multiRanking}
              />
            )}
            <button
              type="button"
              onClick={async () => {
                try {
                  await download("/api/v1/geospatial/dashboard/multi-aoi/export-workbook", "multi-aoi-workbook.csv");
                  setMessage("Multi-AOI export workbook downloaded");
                } catch {
                  setMessage("Multi-AOI export workbook failed");
                }
              }}
              className="rounded border border-slate-300 px-3 py-1 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Download multi-AOI workbook
            </button>
          </div>
        ) : null}
      </SectionShell>

      <SectionShell title="Run Command Center, Scene, and Feature Intelligence">
        {runOps.isLoading || sceneIntel.isLoading || featureIntel.isLoading ? <LoadingState label="Loading run intelligence..." /> : null}
        {runOps.error || sceneIntel.error || featureIntel.error ? <ErrorState message="Failed to load run intelligence modules" /> : null}
        {runOps.data && sceneIntel.data && featureIntel.data ? (
          <div className="space-y-3">
            <div className="grid gap-4 md:grid-cols-4">
              <StatCard label="Repro Badge" value={String(runOps.data.run_reproducibility_badge ?? "n/a")} hint="Diagnostics-backed" />
              <StatCard label="Queue Saturation" value={String((runOps.data.run_queue_saturation_alert as { is_saturated?: boolean } | undefined)?.is_saturated ?? false)} hint="Alert state" />
              <StatCard label="Stuck Detector" value={String((runOps.data.run_stuck_state_detector as { is_stuck?: boolean } | undefined)?.is_stuck ?? false)} hint="Run state" />
              <StatCard label="Cost Estimate" value={String((runOps.data.run_infrastructure_cost_estimate as { estimated_cost_usd?: number } | undefined)?.estimated_cost_usd ?? 0)} hint="USD proxy" />
            </div>
            <div className="grid gap-4 md:grid-cols-3">
              <StatCard label="Approval Gate" value={String((runOps.data.run_approval_gate_before_release as { status?: string } | undefined)?.status ?? "not_requested")} hint="Before release" />
              <StatCard label="Release Blocked" value={String((runOps.data.run_approval_gate_before_release as { release_blocked?: boolean } | undefined)?.release_blocked ?? true)} hint="Fail-closed" />
              <StatCard label="Custody Events" value={String((runOps.data.run_chain_of_custody_timeline as { event_count?: number } | undefined)?.event_count ?? 0)} hint="Timeline depth" />
            </div>
            <div className="flex flex-wrap gap-2 text-sm">
              <button
                type="button"
                onClick={async () => {
                  if (!activeRunId) return;
                  try {
                    await download(`/api/v1/geospatial/runs/${activeRunId}/artifacts/signed-package`, `run-${activeRunId}-signed-package.json`);
                    setMessage("Signed export package downloaded");
                  } catch {
                    setMessage("Signed export package failed");
                  }
                }}
                className="rounded border border-slate-300 px-3 py-1 font-medium text-slate-700 hover:bg-slate-50"
              >
                Download signed package
              </button>
              <button
                type="button"
                onClick={async () => {
                  if (!activeRunId) return;
                  try {
                    await download(`/api/v1/geospatial/runs/${activeRunId}/artifacts/evidence-bundle`, `run-${activeRunId}-evidence-bundle.json`);
                    setMessage("Evidence bundle downloaded");
                  } catch {
                    setMessage("Evidence bundle failed");
                  }
                }}
                className="rounded border border-slate-300 px-3 py-1 font-medium text-slate-700 hover:bg-slate-50"
              >
                Download evidence bundle
              </button>
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <Card title="Scene Intelligence Rows">
                {sceneRows.length === 0 ? <EmptyState title="No scene rows" description="No scene intelligence rows for selected run." /> : (
                  <DataTable
                    columns={[
                      { key: "source", label: "Source" },
                      { key: "scene_id", label: "Scene" },
                      { key: "scene_overlap_with_aoi_percentage", label: "Overlap %" },
                      { key: "scene_quality_composite_score", label: "Quality" },
                      { key: "scene_usable_pixel_percentage", label: "Usable %" },
                      { key: "scene_georegistration_quality_score", label: "Georeg Quality" },
                      { key: "scene_aoi_boundary_mismatch_detector", label: "Boundary Mismatch", render: (row) => String(((row as { scene_aoi_boundary_mismatch_detector?: { mismatch?: boolean } }).scene_aoi_boundary_mismatch_detector?.mismatch) ?? false) },
                      { key: "scene_radiometric_anomaly_detector", label: "Radiometric Flag", render: (row) => String(((row as { scene_radiometric_anomaly_detector?: { flagged?: boolean } }).scene_radiometric_anomaly_detector?.flagged) ?? false) },
                    ]}
                    rows={sceneRows}
                  />
                )}
              </Card>
              <Card title="Feature Intelligence Rows">
                {featureRows.length === 0 ? <EmptyState title="No feature rows" description="No feature intelligence rows for selected run." /> : (
                  <DataTable
                    columns={[
                      { key: "feature_id", label: "Feature ID" },
                      { key: "source", label: "Source" },
                      { key: "feature_temporal_cluster_key", label: "Temporal Cluster" },
                      { key: "feature_cross_source_consensus_score", label: "Cross-source Consensus" },
                      { key: "feature_human_review_priority_score", label: "Review Priority" },
                      { key: "feature_review_sla_timer", label: "SLA Timer", render: (row) => String(((row as { feature_review_sla_timer?: { elapsed_hours?: number } }).feature_review_sla_timer?.elapsed_hours) ?? "n/a") },
                      { key: "anomaly_score", label: "Anomaly" },
                      { key: "feature_review_status", label: "Review" },
                    ]}
                    rows={featureRows}
                  />
                )}
                <div className="mt-2 flex flex-wrap gap-2">
                  <button type="button" disabled={!firstFeatureId} onClick={() => annotateFeatureMutation.mutate()} className="rounded border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50">Annotate first feature</button>
                  <button type="button" disabled={!firstFeatureId} onClick={() => reviewFeatureMutation.mutate()} className="rounded border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50">Approve first feature</button>
                  <button type="button" disabled={!firstFeatureId} onClick={() => recalibrateFeatureMutation.mutate()} className="rounded border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50">Recalibrate first feature</button>
                </div>
              </Card>
            </div>
          </div>
        ) : null}
      </SectionShell>

      <SectionShell title="Platform Diagnostics and Reporting">
        {configHealth.isLoading || selfTest.isLoading ? <LoadingState label="Loading platform diagnostics..." /> : null}
        {configHealth.error || selfTest.error ? <ErrorState message="Failed to load platform diagnostics" /> : null}
        {configHealth.data && selfTest.data ? (
          <div className="space-y-3">
            <div className="grid gap-4 md:grid-cols-3">
              <StatCard label="Config Health" value={String(configHealth.data.health_status ?? "unknown")} hint={`PostGIS ${String(configHealth.data.postgis_enabled ?? false)}`} />
              <StatCard label="Active Schedules" value={String(configHealth.data.active_run_schedules ?? 0)} hint="Cron-capable runs" />
              <StatCard label="Self-test Passed" value={String(selfTest.data.passed ?? false)} hint="Diagnostics suite" />
            </div>
            <div className="flex flex-wrap gap-2">
              <button type="button" onClick={() => weeklyDigestMutation.mutate()} className="rounded border border-slate-300 px-3 py-1 text-sm font-medium text-slate-700 hover:bg-slate-50">Generate weekly digest</button>
              <button type="button" onClick={() => monthlyReportMutation.mutate()} className="rounded border border-slate-300 px-3 py-1 text-sm font-medium text-slate-700 hover:bg-slate-50">Generate monthly performance report</button>
            </div>
          </div>
        ) : null}
      </SectionShell>

      <SectionShell title="Geospatial Operations Center">
        {operationsCenter.isLoading ? <LoadingState label="Loading operations center..." /> : null}
        {operationsCenter.error ? <ErrorState message="Failed to load geospatial operations center" /> : null}
        {operationsCenter.data ? (
          <div className="space-y-3">
            <div className="grid gap-4 md:grid-cols-4">
              <StatCard
                label="Notification Center"
                value={String(((operationsCenter.data.geospatial_notification_center as { total_open?: number } | undefined)?.total_open) ?? 0)}
                hint="Open notifications"
              />
              <StatCard
                label="Unresolved Queue"
                value={String((((operationsCenter.data.geospatial_unresolved_anomaly_queue as unknown[]) ?? []).length))}
                hint="Anomaly queue size"
              />
              <StatCard
                label="Readiness Score"
                value={String((((operationsCenter.data.geospatial_readiness_checklist as { score?: number } | undefined)?.score) ?? 0))}
                hint="Operational readiness"
              />
              <StatCard
                label="Config Drift"
                value={String((((operationsCenter.data.geospatial_configuration_drift_alert as { active?: boolean } | undefined)?.active) ?? false))}
                hint="Deployment guardrail"
              />
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <Card title="Inbox Triage Queue">
                <DataTable
                  columns={[
                    { key: "alert_id", label: "Alert" },
                    { key: "severity", label: "Severity" },
                    { key: "scope_type", label: "Scope" },
                    { key: "title", label: "Title" },
                  ]}
                  rows={(((operationsCenter.data.geospatial_inbox_triage_queue as Record<string, unknown>[] | undefined) ?? []).slice(0, 10))}
                />
              </Card>
              <Card title="Analyst Workload Board">
                <DataTable
                  columns={[
                    { key: "analyst_group", label: "Group" },
                    { key: "assigned_items", label: "Assigned" },
                    { key: "capacity", label: "Capacity" },
                    { key: "utilization", label: "Utilization" },
                  ]}
                  rows={(((operationsCenter.data.geospatial_analyst_workload_board as Record<string, unknown>[] | undefined) ?? []).slice(0, 10))}
                />
              </Card>
            </div>
          </div>
        ) : null}
      </SectionShell>
    </div>
  );
}
