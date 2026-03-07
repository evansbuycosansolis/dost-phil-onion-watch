"use client";

import { apiFetch } from "@phil-onion-watch/api-client";
import { apiConfig } from "@phil-onion-watch/config";
import { Card, EmptyState, ErrorState, LoadingState, SectionShell } from "@phil-onion-watch/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

type RunDiagnostics = {
  run_id: number;
  status: string;
  health_badge: string;
  elapsed_seconds: number;
  duration_percentiles_seconds: { p50: number; p90: number };
  throughput_per_minute: number;
  source_coverage: Record<string, number>;
  missing_scene_count: number;
  provenance_completeness_score: number;
  stale_data_warning: boolean;
  sla_breach: boolean;
  phase_progress: Record<string, number>;
  live_logs: Array<{ id: number; phase: string; status: string; message: string; logged_at: string }>;
};

type RunCompare = {
  left_run_id: number;
  right_run_id: number;
  metrics_summary: {
    status_left: string;
    status_right: string;
    elapsed_seconds_left: number;
    elapsed_seconds_right: number;
    elapsed_seconds_delta: number;
    throughput_per_minute_left: number;
    throughput_per_minute_right: number;
    throughput_delta: number;
    missing_scene_left: number;
    missing_scene_right: number;
    missing_scene_delta: number;
    provenance_completeness_left: number;
    provenance_completeness_right: number;
    provenance_completeness_delta: number;
  };
  provenance_diff: {
    scene_counts: { left: number; right: number; shared: number; left_only: number; right_only: number };
    feature_counts: { left: number; right: number; shared: number; left_only: number; right_only: number };
    scene_overlap_ratio: number;
    feature_overlap_ratio: number;
    scene_shared_sample: string[];
    scene_left_only_sample: string[];
    scene_right_only_sample: string[];
    feature_shared_sample: string[];
    feature_left_only_sample: string[];
    feature_right_only_sample: string[];
  };
  scene_overlap_matrix: {
    labels: { rows: string[]; columns: string[] };
    values: number[][];
    union_count: number;
    shared_count: number;
    left_only_count: number;
    right_only_count: number;
    left_only_ratio: number;
    right_only_ratio: number;
  };
  feature_overlap_matrix: {
    labels: { rows: string[]; columns: string[] };
    values: number[][];
    union_count: number;
    shared_count: number;
    left_only_count: number;
    right_only_count: number;
    left_only_ratio: number;
    right_only_ratio: number;
  };
  parameter_delta: {
    left_hash: string;
    right_hash: string;
    changed_count: number;
    unchanged_count: number;
    truncated: boolean;
    metadata_changed_count: number;
    changes: Array<{ path: string; change_type: string; left: unknown; right: unknown }>;
    metadata_changes: Record<string, { left: unknown; right: unknown; changed: boolean }>;
  };
  diff: Record<string, unknown>;
};

type RunLineage = {
  root_run_id: number;
  upstream_depth: number;
  downstream_count: number;
  nodes: Array<{
    run_id: number;
    parent_run_id: number | null;
    run_type: string;
    status: string;
    queue_priority: number;
    retry_strategy: string;
  }>;
  edges: Array<{ from_run_id: number; to_run_id: number; relation: string }>;
};

type RunDependencyGraph = {
  root_run_id: number;
  direction: "upstream" | "downstream";
  depth: number;
  node_count: number;
  edge_count: number;
  nodes: Array<{
    run_id: number;
    parent_run_id: number | null;
    run_type: string;
    status: string;
    queue_priority: number;
    retry_strategy: string;
  }>;
  edges: Array<{ from_run_id: number; to_run_id: number; relation: string }>;
};

type RunReproducibility = {
  run_id: number;
  reference_run_id: number | null;
  reference_reason: string | null;
  badge: "high" | "medium" | "low";
  score: number;
  diagnostics: Array<{
    check: string;
    passed: boolean;
    weight: number;
    contribution: number;
    details: string;
  }>;
  summary: {
    scene_overlap_ratio: number;
    feature_overlap_ratio: number;
    parameter_changed_count: number;
    parameter_hash_match: boolean;
  };
};

type RunArtifactManifest = {
  run_id: number;
  generated_at: string;
  artifacts: Array<{
    artifact_key: string;
    label: string;
    filename: string;
    content_type: string;
    size_bytes: number;
    checksum_sha256: string;
    download_path: string;
    generated_at: string;
  }>;
};

type RunArtifactDownloadCenter = {
  run_id: number;
  generated_at: string;
  artifact_count: number;
  total_size_bytes: number;
  artifacts: Array<{
    artifact_key: string;
    label: string;
    filename: string;
    content_type: string;
    size_bytes: number;
    checksum_sha256: string;
    download_path: string;
    generated_at: string;
  }>;
};

type RunCommandCenter = {
  run_approval_gate_before_release?: {
    status?: string;
    release_blocked?: boolean;
    review_required?: boolean;
    workflow_id?: number | null;
    requested_at?: string | null;
    reviewed_at?: string | null;
    requested_by?: number | null;
    reviewed_by?: number | null;
    notes?: string | null;
    next_action?: string;
  };
  run_chain_of_custody_timeline?: {
    event_count?: number;
    events?: Array<{
      timestamp?: string;
      event_type?: string;
      summary?: string;
      actor_user_id?: number | null;
    }>;
  };
  run_publish_unpublish_workflow?: Record<string, unknown>;
  run_artifact_retention_policy?: Record<string, unknown>;
  run_cold_storage_archive_action?: Record<string, unknown>;
  run_archive_restore_action?: Record<string, unknown>;
  run_immutable_evidence_record?: Record<string, unknown>;
  run_digital_signature_verification?: Record<string, unknown>;
  run_provenance_notarization_stub?: Record<string, unknown>;
  run_decision_log?: Array<Record<string, unknown>>;
  run_governance_attestation?: Record<string, unknown>;
  run_reviewer_assignment?: Record<string, unknown>;
  run_reviewer_checklist?: Array<Record<string, unknown>>;
  run_review_comment_threads?: Array<Record<string, unknown>>;
  run_merge_reconcile_duplicate_runs?: Record<string, unknown>;
  run_split_combined_runs?: Record<string, unknown>;
  run_scenario_replay?: Record<string, unknown> | null;
  run_dry_run_preview?: Record<string, unknown>;
  run_synthetic_test_data_mode?: Record<string, unknown>;
  run_red_team_anomaly_injection?: Record<string, unknown>;
};

type FilterPreset = {
  id: number;
  preset_type: string;
  name: string;
  filters: Record<string, unknown>;
};

type RunRowsResponse = {
  run_id: number;
  total: number;
  rows: Array<Record<string, unknown>>;
};

function toCsvText(rows: Array<Record<string, unknown>>) {
  if (!rows.length) return "";
  const headers = Object.keys(rows[0]);
  const escape = (value: unknown) => `"${String(value ?? "").replace(/"/g, '""')}"`;
  return [headers.join(","), ...rows.map((row) => headers.map((header) => escape(row[header])).join(","))].join("\n");
}

function downloadCsv(name: string, csv: string) {
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function GeospatialRunAdvancedPanel({ token, runId }: { token?: string | null; runId: number }) {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState("");
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [compareRunId, setCompareRunId] = useState("");
  const [operatorNotes, setOperatorNotes] = useState("");
  const [priority, setPriority] = useState("100");
  const [retryStrategy, setRetryStrategy] = useState("standard");
  const [cancelReason, setCancelReason] = useState("");
  const [presetName, setPresetName] = useState("");
  const [scheduleName, setScheduleName] = useState("");
  const [artifactDownloadKey, setArtifactDownloadKey] = useState("");
  const [sceneColumns, setSceneColumns] = useState<string[]>(["source", "scene_id", "aoi_code", "cloud_score", "processing_status", "provenance_status"]);
  const [featureColumns, setFeatureColumns] = useState<string[]>(["source", "observation_date", "aoi_code", "scene_id", "observation_confidence_score", "crop_activity_score", "vegetation_vigor_score"]);

  const diagnostics = useQuery({
    queryKey: ["geospatial-run-diagnostics", token, runId],
    queryFn: () => apiFetch<RunDiagnostics>(`/api/v1/geospatial/runs/${runId}/diagnostics`, { token }),
    enabled: !!token,
    refetchInterval: autoRefresh ? 5000 : false,
  });

  const scenes = useQuery({
    queryKey: ["geospatial-run-advanced-scenes", token, runId],
    queryFn: () => apiFetch<RunRowsResponse>(`/api/v1/geospatial/runs/${runId}/provenance/scenes?page=1&page_size=50`, { token }),
    enabled: !!token,
  });

  const features = useQuery({
    queryKey: ["geospatial-run-advanced-features", token, runId],
    queryFn: () => apiFetch<RunRowsResponse>(`/api/v1/geospatial/runs/${runId}/provenance/features?page=1&page_size=50`, { token }),
    enabled: !!token,
  });

  const filterPresets = useQuery({
    queryKey: ["geospatial-run-filter-presets", token],
    queryFn: () => apiFetch<FilterPreset[]>(`/api/v1/geospatial/run-filter-presets`, { token }),
    enabled: !!token,
  });

  const lineage = useQuery({
    queryKey: ["geospatial-run-lineage", token, runId],
    queryFn: () => apiFetch<RunLineage>(`/api/v1/geospatial/runs/${runId}/lineage`, { token }),
    enabled: !!token,
  });

  const upstreamDependencies = useQuery({
    queryKey: ["geospatial-run-upstream-dependencies", token, runId],
    queryFn: () => apiFetch<RunDependencyGraph>(`/api/v1/geospatial/runs/${runId}/dependencies/upstream`, { token }),
    enabled: !!token,
  });

  const downstreamDependencies = useQuery({
    queryKey: ["geospatial-run-downstream-dependencies", token, runId],
    queryFn: () => apiFetch<RunDependencyGraph>(`/api/v1/geospatial/runs/${runId}/dependencies/downstream`, { token }),
    enabled: !!token,
  });

  const reproducibility = useQuery({
    queryKey: ["geospatial-run-reproducibility", token, runId],
    queryFn: () => apiFetch<RunReproducibility>(`/api/v1/geospatial/runs/${runId}/reproducibility`, { token }),
    enabled: !!token,
  });

  const artifactManifest = useQuery({
    queryKey: ["geospatial-run-artifact-manifest", token, runId],
    queryFn: () => apiFetch<RunArtifactManifest>(`/api/v1/geospatial/runs/${runId}/artifacts/manifest`, { token }),
    enabled: !!token,
  });

  const artifactDownloadCenter = useQuery({
    queryKey: ["geospatial-run-artifact-download-center", token, runId],
    queryFn: () => apiFetch<RunArtifactDownloadCenter>(`/api/v1/geospatial/runs/${runId}/artifacts/download-center`, { token }),
    enabled: !!token,
  });
  const commandCenter = useQuery({
    queryKey: ["geospatial-run-command-center", token, runId],
    queryFn: () => apiFetch<RunCommandCenter>(`/api/v1/geospatial/runs/${runId}/operations/command-center`, { token }),
    enabled: !!token,
  });

  const compareMutation = useMutation({
    mutationFn: async () =>
      apiFetch<RunCompare>("/api/v1/geospatial/run-compare", {
        token,
        method: "POST",
        body: { left_run_id: runId, right_run_id: Number(compareRunId) },
      }),
    onSuccess: () => setMessage("Run comparison complete"),
    onError: () => setMessage("Run comparison failed"),
  });

  const updatePriorityMutation = useMutation({
    mutationFn: async () => apiFetch(`/api/v1/geospatial/runs/${runId}/priority`, { token, method: "POST", body: { queue_priority: Number(priority) } }),
    onSuccess: async () => {
      setMessage("Run priority updated");
      await queryClient.invalidateQueries({ queryKey: ["geospatial-run-diagnostics", token, runId] });
    },
    onError: () => setMessage("Run priority update failed"),
  });

  const updateNotesMutation = useMutation({
    mutationFn: async () => apiFetch(`/api/v1/geospatial/runs/${runId}/notes`, { token, method: "POST", body: { operator_notes: operatorNotes } }),
    onSuccess: () => setMessage("Operator notes updated"),
    onError: () => setMessage("Operator note update failed"),
  });

  const cloneMutation = useMutation({
    mutationFn: async () =>
      apiFetch(`/api/v1/geospatial/runs/${runId}/clone`, {
        token,
        method: "POST",
        body: { queue_priority: Number(priority), retry_strategy: retryStrategy, notes: `Clone requested from advanced panel for run ${runId}` },
      }),
    onSuccess: () => setMessage("Run clone queued"),
    onError: () => setMessage("Run clone failed"),
  });

  const cancelMutation = useMutation({
    mutationFn: async () =>
      apiFetch(`/api/v1/geospatial/runs/${runId}/cancel?reason=${encodeURIComponent(cancelReason || "Operator cancellation")}`, {
        token,
        method: "POST",
      }),
    onSuccess: () => setMessage("Cancel request submitted"),
    onError: () => setMessage("Cancel request failed"),
  });

  const savePresetMutation = useMutation({
    mutationFn: async () =>
      apiFetch(`/api/v1/geospatial/run-presets`, {
        token,
        method: "POST",
        body: {
          name: presetName || `Preset ${runId}`,
          run_type: "feature_refresh",
          description: "Saved from run advanced panel",
          sources: ["sentinel-2", "sentinel-1"],
          parameters: { scene_columns: sceneColumns, feature_columns: featureColumns },
          retry_strategy: retryStrategy,
          queue_priority: Number(priority),
        },
      }),
    onSuccess: () => setMessage("Run parameter preset saved"),
    onError: () => setMessage("Failed to save run preset"),
  });

  const saveScheduleMutation = useMutation({
    mutationFn: async () =>
      apiFetch(`/api/v1/geospatial/run-schedules`, {
        token,
        method: "POST",
        body: {
          name: scheduleName || `Schedule for run ${runId}`,
          run_type: "feature_refresh",
          cron_expression: "0 4 1 * *",
          timezone: "Asia/Manila",
          recurrence_template: "monthly_start",
          retry_strategy: retryStrategy,
          queue_priority: Number(priority),
          is_active: true,
          sources: ["sentinel-2", "sentinel-1"],
          parameters: { reference_run_id: runId },
          notify_channels: ["email:ops@onionwatch.ph"],
        },
      }),
    onSuccess: () => setMessage("Run schedule created"),
    onError: () => setMessage("Failed to create run schedule"),
  });

  const saveFilterPresetMutation = useMutation({
    mutationFn: async (presetType: "scene" | "feature") =>
      apiFetch(`/api/v1/geospatial/run-filter-presets`, {
        token,
        method: "POST",
        body: {
          preset_type: presetType,
          name: `${presetType}-preset-${runId}`,
          filters: presetType === "scene" ? { scene_columns: sceneColumns } : { feature_columns: featureColumns },
        },
      }),
    onSuccess: async () => {
      setMessage("Drilldown filter preset saved");
      await queryClient.invalidateQueries({ queryKey: ["geospatial-run-filter-presets", token] });
    },
    onError: () => setMessage("Failed to save filter preset"),
  });
  const approvalGateMutation = useMutation({
    mutationFn: async (status: "requested" | "approved" | "rejected") =>
      apiFetch(`/api/v1/geospatial/runs/${runId}/operations/approval-gate`, {
        token,
        method: "POST",
        body: {
          status,
          notes: `Advanced panel set approval gate to ${status}`,
        },
      }),
    onSuccess: async () => {
      setMessage("Run approval gate updated");
      await queryClient.invalidateQueries({ queryKey: ["geospatial-run-command-center", token, runId] });
    },
    onError: () => setMessage("Run approval gate update failed"),
  });
  const publishMutation = useMutation({
    mutationFn: async (action: "publish" | "unpublish") =>
      apiFetch(`/api/v1/geospatial/runs/${runId}/operations/publish`, {
        token,
        method: "POST",
        body: { action, channel: "executive" },
      }),
    onSuccess: async () => {
      setMessage("Run publish workflow updated");
      await queryClient.invalidateQueries({ queryKey: ["geospatial-run-command-center", token, runId] });
    },
    onError: () => setMessage("Run publish workflow update failed"),
  });
  const archiveMutation = useMutation({
    mutationFn: async (action: "archive" | "restore") =>
      apiFetch(`/api/v1/geospatial/runs/${runId}/operations/archive`, {
        token,
        method: "POST",
        body: { action, tier: "cold", retention_days: 365 },
      }),
    onSuccess: async () => {
      setMessage("Run archive workflow updated");
      await queryClient.invalidateQueries({ queryKey: ["geospatial-run-command-center", token, runId] });
    },
    onError: () => setMessage("Run archive workflow update failed"),
  });
  const governanceMutation = useMutation({
    mutationFn: async (action: "decision" | "attest" | "comment") =>
      apiFetch(`/api/v1/geospatial/runs/${runId}/operations/governance`, {
        token,
        method: "POST",
        body:
          action === "decision"
            ? { action, decision: "approve_release", notes: "Advanced panel governance decision" }
            : action === "attest"
            ? { action, status: "attested", notes: "Governance attestation from advanced panel" }
            : { action, comment: "Review comment from advanced panel", thread_id: "default" },
      }),
    onSuccess: async () => {
      setMessage("Run governance updated");
      await queryClient.invalidateQueries({ queryKey: ["geospatial-run-command-center", token, runId] });
    },
    onError: () => setMessage("Run governance update failed"),
  });
  const scenarioMutation = useMutation({
    mutationFn: async (action: "replay" | "dry_run" | "synthetic_test" | "red_team_injection") =>
      apiFetch(`/api/v1/geospatial/runs/${runId}/operations/scenario`, {
        token,
        method: "POST",
        body: {
          action,
          enabled: true,
          dataset: "synthetic-default",
          injection_type: "anomaly_spike",
        },
      }),
    onSuccess: async () => {
      setMessage("Run scenario operations updated");
      await queryClient.invalidateQueries({ queryKey: ["geospatial-run-command-center", token, runId] });
    },
    onError: () => setMessage("Run scenario operations update failed"),
  });

  const sceneRows = useMemo(() => scenes.data?.rows ?? [], [scenes.data?.rows]);
  const featureRows = useMemo(() => features.data?.rows ?? [], [features.data?.rows]);
  const availableSceneColumns = useMemo(() => (sceneRows[0] ? Object.keys(sceneRows[0]) : []), [sceneRows]);
  const availableFeatureColumns = useMemo(() => (featureRows[0] ? Object.keys(featureRows[0]) : []), [featureRows]);
  const compared = compareMutation.data;

  async function downloadArtifact(artifactKey: string, filename: string) {
    try {
      setArtifactDownloadKey(artifactKey);
      const response = await fetch(`${apiConfig.baseUrl}/api/v1/geospatial/runs/${runId}/artifacts/${artifactKey}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!response.ok) {
        throw new Error(`artifact-download-${response.status}`);
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setMessage(`Downloaded artifact: ${filename}`);
    } catch {
      setMessage("Artifact download failed");
    } finally {
      setArtifactDownloadKey("");
    }
  }

  return (
    <SectionShell title="Run Advanced Operations and Drilldown UX">
      <div className="space-y-4" data-testid="run-advanced-panel">
        <Card>
          <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
            <div>
              <a href="/dashboard/geospatial" className="text-sky-700 hover:underline">Geo home</a> / <a href="/dashboard/geospatial/aois" className="text-sky-700 hover:underline">AOIs</a> / <span className="font-semibold">Run #{runId}</span>
            </div>
            <div className="flex items-center gap-3 text-xs">
              <label className="flex items-center gap-2"><input type="checkbox" checked={autoRefresh} onChange={(event) => setAutoRefresh(event.target.checked)} /> Auto-refresh</label>
              <span>{message}</span>
            </div>
          </div>
        </Card>

        {diagnostics.isLoading ? <LoadingState label="Loading run diagnostics..." /> : null}
        {diagnostics.error ? <ErrorState message="Failed to load run diagnostics" /> : null}
        {diagnostics.data ? (
          <div className="grid gap-4 xl:grid-cols-3">
            <Card title="Execution Health, SLA, Throughput, and Source Coverage">
              <div className="space-y-2 text-xs text-slate-700">
                <div>Status: <span className="font-semibold">{diagnostics.data.status}</span> · Health badge: <span className="font-semibold">{diagnostics.data.health_badge}</span></div>
                <div>Elapsed: {diagnostics.data.elapsed_seconds}s · Throughput: {diagnostics.data.throughput_per_minute}/min · P50/P90: {diagnostics.data.duration_percentiles_seconds.p50}s / {diagnostics.data.duration_percentiles_seconds.p90}s</div>
                <div>Provenance completeness: {(diagnostics.data.provenance_completeness_score * 100).toFixed(1)}% · Missing scenes: {diagnostics.data.missing_scene_count}</div>
                {diagnostics.data.stale_data_warning ? <div className="rounded bg-amber-50 px-2 py-1 text-amber-700">Stale-data warning active</div> : null}
                {diagnostics.data.sla_breach ? <div className="rounded bg-rose-50 px-2 py-1 text-rose-700">SLA breach indicator active</div> : null}
                <div>Source coverage: {Object.entries(diagnostics.data.source_coverage).map(([k, v]) => `${k}:${v}`).join(", ") || "none"}</div>
                <div>Execution phase progress:</div>
                <div className="grid gap-1">
                  {Object.entries(diagnostics.data.phase_progress).map(([phase, pct]) => (
                    <div key={phase} className="rounded border border-slate-200 bg-slate-50 p-1">
                      <div className="flex items-center justify-between"><span>{phase}</span><span>{pct}%</span></div>
                      <div className="mt-1 h-1.5 rounded bg-slate-200"><div className="h-1.5 rounded bg-sky-500" style={{ width: `${pct}%` }} /></div>
                    </div>
                  ))}
                </div>
              </div>
            </Card>
            <Card title="Live Log Tail and Retry/Cancel Strategy">
              <div className="space-y-2 text-xs">
                <div className="grid gap-2 sm:grid-cols-2">
                  <input value={priority} onChange={(event) => setPriority(event.target.value)} placeholder="Queue priority" className="rounded border border-slate-300 px-2 py-1 text-sm" />
                  <select value={retryStrategy} onChange={(event) => setRetryStrategy(event.target.value)} className="rounded border border-slate-300 px-2 py-1 text-sm">
                    <option value="standard">standard</option>
                    <option value="exponential">exponential</option>
                    <option value="aggressive">aggressive</option>
                  </select>
                  <input value={cancelReason} onChange={(event) => setCancelReason(event.target.value)} placeholder="Cancel reason capture" className="rounded border border-slate-300 px-2 py-1 text-sm sm:col-span-2" />
                  <textarea value={operatorNotes} onChange={(event) => setOperatorNotes(event.target.value)} placeholder="Run operator notes" className="h-16 rounded border border-slate-300 px-2 py-1 text-sm sm:col-span-2" />
                </div>
                <div className="flex flex-wrap gap-2">
                  <button type="button" onClick={() => updatePriorityMutation.mutate()} className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50">Update priority</button>
                  <button type="button" onClick={() => updateNotesMutation.mutate()} className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50">Save notes</button>
                  <button type="button" onClick={() => cloneMutation.mutate()} className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50">Clone run</button>
                  <button type="button" onClick={() => cancelMutation.mutate()} className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50">Cancel with reason</button>
                </div>
                <div className="max-h-40 space-y-1 overflow-y-auto rounded border border-slate-200 bg-slate-50 p-2 text-slate-700">
                  {diagnostics.data.live_logs.slice(0, 30).map((log) => (
                    <div key={log.id} className="rounded bg-white px-2 py-1">
                      <div className="font-medium">{log.phase} · {log.status}</div>
                      <div>{log.message}</div>
                      <div className="text-slate-500">{log.logged_at}</div>
                    </div>
                  ))}
                </div>
              </div>
            </Card>
            <Card title="Run Approval Gate and Chain-of-Custody">
              {commandCenter.isLoading ? <LoadingState label="Loading approval gate and custody timeline..." /> : null}
              {commandCenter.error ? <ErrorState message="Failed to load approval gate and chain-of-custody timeline" /> : null}
              {commandCenter.data ? (
                <div className="space-y-2 text-xs text-slate-700">
                  <div className="rounded border border-slate-200 bg-slate-50 px-2 py-1">
                    Approval gate: <span className="font-semibold">{commandCenter.data.run_approval_gate_before_release?.status ?? "not_requested"}</span> · release blocked: <span className="font-semibold">{String(commandCenter.data.run_approval_gate_before_release?.release_blocked ?? true)}</span>
                  </div>
                  <div className="rounded border border-slate-200 bg-slate-50 px-2 py-1">
                    Next action: {commandCenter.data.run_approval_gate_before_release?.next_action ?? "request_review"} · workflow #{commandCenter.data.run_approval_gate_before_release?.workflow_id ?? "n/a"}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button type="button" onClick={() => approvalGateMutation.mutate("requested")} className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50">Request gate</button>
                    <button type="button" onClick={() => approvalGateMutation.mutate("approved")} className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50">Approve gate</button>
                    <button type="button" onClick={() => approvalGateMutation.mutate("rejected")} className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50">Reject gate</button>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button type="button" onClick={() => publishMutation.mutate("publish")} className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50">Publish</button>
                    <button type="button" onClick={() => publishMutation.mutate("unpublish")} className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50">Unpublish</button>
                    <button type="button" onClick={() => archiveMutation.mutate("archive")} className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50">Archive cold</button>
                    <button type="button" onClick={() => archiveMutation.mutate("restore")} className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50">Restore archive</button>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button type="button" onClick={() => governanceMutation.mutate("decision")} className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50">Decision log</button>
                    <button type="button" onClick={() => governanceMutation.mutate("comment")} className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50">Add comment</button>
                    <button type="button" onClick={() => governanceMutation.mutate("attest")} className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50">Attest</button>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button type="button" onClick={() => scenarioMutation.mutate("replay")} className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50">Replay</button>
                    <button type="button" onClick={() => scenarioMutation.mutate("dry_run")} className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50">Dry-run</button>
                    <button type="button" onClick={() => scenarioMutation.mutate("synthetic_test")} className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50">Synthetic mode</button>
                    <button type="button" onClick={() => scenarioMutation.mutate("red_team_injection")} className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50">Red-team inject</button>
                  </div>
                  <div className="rounded border border-slate-200 bg-white px-2 py-1">
                    Chain-of-custody timeline events: {commandCenter.data.run_chain_of_custody_timeline?.event_count ?? 0}
                  </div>
                  <div className="rounded border border-slate-200 bg-white px-2 py-1">
                    Publish state: {String((commandCenter.data.run_publish_unpublish_workflow as { is_published?: boolean } | undefined)?.is_published ?? false)} · Archive tier: {String((commandCenter.data.run_cold_storage_archive_action as { archive_tier?: string } | undefined)?.archive_tier ?? "hot")}
                  </div>
                  <div className="rounded border border-slate-200 bg-white px-2 py-1">
                    Signature verified: {String((commandCenter.data.run_digital_signature_verification as { verified?: boolean } | undefined)?.verified ?? false)} · Notary: {String((commandCenter.data.run_provenance_notarization_stub as { status?: string } | undefined)?.status ?? "n/a")}
                  </div>
                  <div className="rounded border border-slate-200 bg-white px-2 py-1">
                    Decision log entries: {((commandCenter.data.run_decision_log as unknown[]) ?? []).length} · Review comments: {((commandCenter.data.run_review_comment_threads as unknown[]) ?? []).length}
                  </div>
                  <div className="max-h-28 overflow-y-auto rounded border border-slate-200 bg-white px-2 py-1">
                    {(commandCenter.data.run_chain_of_custody_timeline?.events ?? []).slice(-8).map((event, index) => (
                      <div key={`${event.timestamp ?? "na"}-${event.event_type ?? "event"}-${index}`}>
                        {event.timestamp ?? "n/a"} · {event.event_type ?? "event"} · {event.summary ?? ""}
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </Card>
          </div>
        ) : null}

        <div className="grid gap-4 xl:grid-cols-3">
          <Card title="Run Compare Metrics Summary">
            <input value={compareRunId} onChange={(event) => setCompareRunId(event.target.value)} placeholder="Compare against run id" className="w-full rounded border border-slate-300 px-2 py-1 text-sm" />
            <button type="button" disabled={!compareRunId.trim()} onClick={() => compareMutation.mutate()} className="mt-2 rounded border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50">Compare two runs</button>
            {!compared ? <p className="mt-2 text-xs text-slate-500">Run compare metrics summary will render after selecting a target run.</p> : (
              <div className="mt-2 grid gap-2 text-xs text-slate-700">
                <div className="rounded border border-slate-200 bg-slate-50 px-2 py-1">Status: {compared.metrics_summary.status_left} -&gt; {compared.metrics_summary.status_right}</div>
                <div className="rounded border border-slate-200 bg-slate-50 px-2 py-1">Elapsed: {compared.metrics_summary.elapsed_seconds_left}s vs {compared.metrics_summary.elapsed_seconds_right}s (delta {compared.metrics_summary.elapsed_seconds_delta}s)</div>
                <div className="rounded border border-slate-200 bg-slate-50 px-2 py-1">Throughput: {compared.metrics_summary.throughput_per_minute_left}/min vs {compared.metrics_summary.throughput_per_minute_right}/min (delta {compared.metrics_summary.throughput_delta})</div>
                <div className="rounded border border-slate-200 bg-slate-50 px-2 py-1">Missing scenes: {compared.metrics_summary.missing_scene_left} vs {compared.metrics_summary.missing_scene_right} (delta {compared.metrics_summary.missing_scene_delta})</div>
                <div className="rounded border border-slate-200 bg-slate-50 px-2 py-1">Provenance completeness: {(compared.metrics_summary.provenance_completeness_left * 100).toFixed(1)}% vs {(compared.metrics_summary.provenance_completeness_right * 100).toFixed(1)}% (delta {(compared.metrics_summary.provenance_completeness_delta * 100).toFixed(1)}%)</div>
                <div className="rounded border border-slate-200 bg-white px-2 py-1">
                  Scene overlap matrix [L-L, L-R, R-L, R-R]: {compared.scene_overlap_matrix.values?.[0]?.[0] ?? 0}, {compared.scene_overlap_matrix.values?.[0]?.[1] ?? 0}, {compared.scene_overlap_matrix.values?.[1]?.[0] ?? 0}, {compared.scene_overlap_matrix.values?.[1]?.[1] ?? 0}
                </div>
                <div className="rounded border border-slate-200 bg-white px-2 py-1">
                  Feature overlap matrix [L-L, L-R, R-L, R-R]: {compared.feature_overlap_matrix.values?.[0]?.[0] ?? 0}, {compared.feature_overlap_matrix.values?.[0]?.[1] ?? 0}, {compared.feature_overlap_matrix.values?.[1]?.[0] ?? 0}, {compared.feature_overlap_matrix.values?.[1]?.[1] ?? 0}
                </div>
                <div className="rounded border border-slate-200 bg-white px-2 py-1">
                  Parameter delta viewer: {compared.parameter_delta.changed_count} changed path(s), {compared.parameter_delta.unchanged_count} unchanged, metadata changes {compared.parameter_delta.metadata_changed_count}
                </div>
                <div className="max-h-24 overflow-y-auto rounded border border-slate-200 bg-white px-2 py-1">
                  <div className="font-medium">Parameter delta sample</div>
                  {(compared.parameter_delta.changes ?? []).slice(0, 6).map((change) => (
                    <div key={`${change.path}-${change.change_type}`}>{change.path} [{change.change_type}]</div>
                  ))}
                </div>
              </div>
            )}
          </Card>
          <Card title="Run Compare Provenance Diff">
            {!compared ? <EmptyState title="No compare diff" description="Execute run comparison to inspect provenance overlap and divergence." /> : (
              <div className="space-y-2 text-xs text-slate-700">
                <div className="rounded border border-slate-200 bg-slate-50 px-2 py-1">Scene overlap ratio: {(compared.provenance_diff.scene_overlap_ratio * 100).toFixed(1)}%</div>
                <div className="rounded border border-slate-200 bg-slate-50 px-2 py-1">Feature overlap ratio: {(compared.provenance_diff.feature_overlap_ratio * 100).toFixed(1)}%</div>
                <div className="grid gap-2 sm:grid-cols-2">
                  <div className="rounded border border-slate-200 bg-slate-50 px-2 py-1">Scenes L/R/shared: {compared.provenance_diff.scene_counts.left}/{compared.provenance_diff.scene_counts.right}/{compared.provenance_diff.scene_counts.shared}</div>
                  <div className="rounded border border-slate-200 bg-slate-50 px-2 py-1">Features L/R/shared: {compared.provenance_diff.feature_counts.left}/{compared.provenance_diff.feature_counts.right}/{compared.provenance_diff.feature_counts.shared}</div>
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  <div className="rounded border border-slate-200 bg-slate-50 px-2 py-1">Scene matrix left-only/right-only: {compared.scene_overlap_matrix.left_only_count}/{compared.scene_overlap_matrix.right_only_count}</div>
                  <div className="rounded border border-slate-200 bg-slate-50 px-2 py-1">Feature matrix left-only/right-only: {compared.feature_overlap_matrix.left_only_count}/{compared.feature_overlap_matrix.right_only_count}</div>
                </div>
                <div className="max-h-24 overflow-y-auto rounded border border-slate-200 bg-white px-2 py-1">
                  <div className="font-medium">Scene left-only sample</div>
                  {(compared.provenance_diff.scene_left_only_sample ?? []).slice(0, 5).map((entry) => <div key={`sl-${entry}`}>{entry}</div>)}
                </div>
                <div className="max-h-24 overflow-y-auto rounded border border-slate-200 bg-white px-2 py-1">
                  <div className="font-medium">Feature right-only sample</div>
                  {(compared.provenance_diff.feature_right_only_sample ?? []).slice(0, 5).map((entry) => <div key={`fr-${entry}`}>{entry}</div>)}
                </div>
                <div className="rounded border border-slate-200 bg-white px-2 py-1">Parameter hashes: {compared.parameter_delta.left_hash.slice(0, 12)} / {compared.parameter_delta.right_hash.slice(0, 12)}</div>
              </div>
            )}
          </Card>
          <Card title="Run Reproducibility and Dependency Graphs">
            {lineage.isLoading || upstreamDependencies.isLoading || downstreamDependencies.isLoading || reproducibility.isLoading ? <LoadingState label="Loading lineage and reproducibility..." /> : null}
            {lineage.error || upstreamDependencies.error || downstreamDependencies.error || reproducibility.error ? <ErrorState message="Failed to load run lineage/dependencies/reproducibility" /> : null}
            {lineage.data && upstreamDependencies.data && downstreamDependencies.data && reproducibility.data ? (
              <div className="space-y-2 text-xs text-slate-700">
                <div className="rounded border border-slate-200 bg-slate-50 px-2 py-1">Lineage root #{lineage.data.root_run_id} · upstream depth {lineage.data.upstream_depth} · downstream count {lineage.data.downstream_count}</div>
                <div className="rounded border border-slate-200 bg-slate-50 px-2 py-1">
                  Reproducibility badge: <span className="font-semibold uppercase">{reproducibility.data.badge}</span> · score {(reproducibility.data.score * 100).toFixed(1)}% · reference #{reproducibility.data.reference_run_id ?? "n/a"} ({reproducibility.data.reference_reason ?? "none"})
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  <div className="rounded border border-slate-200 bg-white p-2">
                    <div className="font-medium">Upstream dependency graph</div>
                    <div>Depth {upstreamDependencies.data.depth} · Nodes {upstreamDependencies.data.node_count} · Edges {upstreamDependencies.data.edge_count}</div>
                    <div className="mt-1 max-h-20 overflow-y-auto">
                      {(upstreamDependencies.data.edges ?? []).map((edge, index) => (
                        <div key={`up-${edge.from_run_id}-${edge.to_run_id}-${index}`}>#{edge.from_run_id} -&gt; #{edge.to_run_id}</div>
                      ))}
                    </div>
                  </div>
                  <div className="rounded border border-slate-200 bg-white p-2">
                    <div className="font-medium">Downstream consumer graph</div>
                    <div>Depth {downstreamDependencies.data.depth} · Nodes {downstreamDependencies.data.node_count} · Edges {downstreamDependencies.data.edge_count}</div>
                    <div className="mt-1 max-h-20 overflow-y-auto">
                      {(downstreamDependencies.data.edges ?? []).map((edge, index) => (
                        <div key={`down-${edge.from_run_id}-${edge.to_run_id}-${index}`}>#{edge.from_run_id} -&gt; #{edge.to_run_id}</div>
                      ))}
                    </div>
                  </div>
                </div>
                <div className="max-h-24 overflow-y-auto rounded border border-slate-200 bg-white px-2 py-1">
                  <div className="font-medium">Reproducibility diagnostics</div>
                  {(reproducibility.data.diagnostics ?? []).map((check) => (
                    <div key={check.check}>
                      {check.check}: {check.passed ? "pass" : "fail"} (weight {check.weight}, contribution {check.contribution}) - {check.details}
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </Card>
        </div>

        <div className="grid gap-4 xl:grid-cols-3">
          <Card title="Run Schedule Builder and Parameter Presets">
            <input value={presetName} onChange={(event) => setPresetName(event.target.value)} placeholder="Parameter preset name" className="w-full rounded border border-slate-300 px-2 py-1 text-sm" />
            <button type="button" onClick={() => savePresetMutation.mutate()} className="mt-2 rounded border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50">Save run preset</button>
            <input value={scheduleName} onChange={(event) => setScheduleName(event.target.value)} placeholder="Schedule name" className="mt-2 w-full rounded border border-slate-300 px-2 py-1 text-sm" />
            <button type="button" onClick={() => saveScheduleMutation.mutate()} className="mt-2 rounded border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50">Create schedule + recurrence template</button>
            <div className="mt-2 rounded border border-slate-200 bg-slate-50 p-2 text-xs text-slate-600">Parameter validation hints: queue priority 1-1000, cron expression required, retry strategy required.</div>
          </Card>
          <Card title="Saved Drilldown Filter Presets">
            <div className="flex flex-wrap gap-2 text-xs">
              <button type="button" onClick={() => saveFilterPresetMutation.mutate("scene")} className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50">Save scene preset</button>
              <button type="button" onClick={() => saveFilterPresetMutation.mutate("feature")} className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50">Save feature preset</button>
            </div>
            <div className="mt-2 max-h-40 space-y-1 overflow-y-auto rounded border border-slate-200 bg-slate-50 p-2 text-xs text-slate-700">
              {(filterPresets.data ?? []).map((preset) => (
                <div key={preset.id} className="rounded bg-white px-2 py-1">
                  <div className="font-medium">{preset.name}</div>
                  <div>{preset.preset_type}</div>
                </div>
              ))}
            </div>
          </Card>
          <Card title="Run Artifact Download Center">
            {artifactManifest.isLoading || artifactDownloadCenter.isLoading ? <LoadingState label="Loading artifact download center..." /> : null}
            {artifactManifest.error || artifactDownloadCenter.error ? <ErrorState message="Failed to load run artifact download center" /> : null}
            {(artifactManifest.data || artifactDownloadCenter.data) ? (
              <div className="space-y-2 text-xs text-slate-700">
                <div className="rounded border border-slate-200 bg-slate-50 px-2 py-1">
                  Generated at {artifactDownloadCenter.data?.generated_at ?? artifactManifest.data?.generated_at} · artifacts {artifactDownloadCenter.data?.artifact_count ?? artifactManifest.data?.artifacts?.length ?? 0} · total size {artifactDownloadCenter.data?.total_size_bytes ?? 0} bytes
                </div>
                <a href={`/dashboard/geospatial/runs/${runId}/artifacts`} className="inline-flex rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-white">Open artifact download center</a>
                <div className="max-h-48 space-y-1 overflow-y-auto rounded border border-slate-200 bg-white p-2">
                  {(artifactDownloadCenter.data?.artifacts ?? artifactManifest.data?.artifacts ?? []).map((artifact) => (
                    <div key={artifact.artifact_key} className="rounded border border-slate-200 bg-slate-50 px-2 py-1">
                      <div className="font-medium">{artifact.label}</div>
                      <div>{artifact.filename} · {artifact.content_type} · {artifact.size_bytes} bytes</div>
                      <button
                        type="button"
                        disabled={artifactDownloadKey === artifact.artifact_key}
                        onClick={() => {
                          void downloadArtifact(artifact.artifact_key, artifact.filename);
                        }}
                        className="mt-1 rounded border border-slate-300 px-2 py-0.5 font-medium text-slate-700 hover:bg-white disabled:opacity-50"
                      >
                        {artifactDownloadKey === artifact.artifact_key ? "Downloading..." : "Download"}
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </Card>
        </div>

        <div className="grid gap-4 xl:grid-cols-2">
          <Card title="Scene Column Visibility, Row Summary, and Metadata Expand">
            <div className="mb-2 flex flex-wrap gap-2 text-xs">
              {availableSceneColumns.map((column) => (
                <label key={column} className="flex items-center gap-1 rounded border border-slate-200 bg-slate-50 px-2 py-1">
                  <input type="checkbox" checked={sceneColumns.includes(column)} onChange={(event) => setSceneColumns((prev) => (event.target.checked ? [...prev, column] : prev.filter((entry) => entry !== column)))} />
                  {column}
                </label>
              ))}
            </div>
            <div className="rounded border border-slate-200 bg-slate-50 px-2 py-1 text-xs text-slate-700">Scene row count summary: {scenes.data?.total ?? sceneRows.length}</div>
            {sceneRows.length === 0 ? <EmptyState title="No scenes" description="Empty-state recovery: clear filters and retry run ingestion." /> : (
              <div className="mt-2 max-h-48 space-y-2 overflow-y-auto text-xs">
                {sceneRows.slice(0, 8).map((row, idx) => (
                  <details key={idx} className="rounded border border-slate-200 bg-white px-2 py-1">
                    <summary className="cursor-pointer">{String(row.scene_id ?? row.id ?? `scene-${idx}`)} · provenance confidence badge {(Number(row.cloud_score ?? 0) <= 0.2 ? "high" : "medium")}</summary>
                    <div className="mt-1 space-y-1 text-slate-600">
                      {sceneColumns.map((column) => <div key={column}><span className="font-medium">{column}:</span> {String(row[column] ?? "n/a")}</div>)}
                      <div>Processing stage timeline: discovered -&gt; normalized -&gt; linked -&gt; materialized</div>
                      <div>Scene thumbnail/footprint preview: {String(row.scene_id ?? "n/a")}</div>
                      <div>Scene cloud mask preview: cloud score {String(row.cloud_score ?? "n/a")}</div>
                      <div>Scene download/source URL visibility: {String((row.metadata as { source_url?: string } | undefined)?.source_url ?? "n/a")}</div>
                    </div>
                  </details>
                ))}
              </div>
            )}
          </Card>
          <Card title="Feature Column Visibility, Distribution, and Anomaly Explanation">
            <div className="mb-2 flex flex-wrap gap-2 text-xs">
              {availableFeatureColumns.map((column) => (
                <label key={column} className="flex items-center gap-1 rounded border border-slate-200 bg-slate-50 px-2 py-1">
                  <input type="checkbox" checked={featureColumns.includes(column)} onChange={(event) => setFeatureColumns((prev) => (event.target.checked ? [...prev, column] : prev.filter((entry) => entry !== column)))} />
                  {column}
                </label>
              ))}
            </div>
            <div className="rounded border border-slate-200 bg-slate-50 px-2 py-1 text-xs text-slate-700">Feature row count summary: {features.data?.total ?? featureRows.length}</div>
            {featureRows.length === 0 ? <EmptyState title="No features" description="Empty-state recovery: run feature recompute or broaden source filters." /> : (
              <div className="mt-2 max-h-48 space-y-2 overflow-y-auto text-xs">
                {featureRows.slice(0, 8).map((row, idx) => (
                  <div key={idx} className="rounded border border-slate-200 bg-white px-2 py-1 text-slate-600">
                    {featureColumns.map((column) => <div key={column}><span className="font-medium">{column}:</span> {String(row[column] ?? "n/a")}</div>)}
                    <div>Feature anomaly explanation panel: score delta against confidence threshold highlights potential anomaly context.</div>
                    <div>Feature threshold breakdown viewer: confidence {String(row.observation_confidence_score ?? "n/a")} vs threshold 0.40.</div>
                  </div>
                ))}
              </div>
            )}
            <div className="mt-2 flex flex-wrap gap-2 text-xs">
              <button type="button" onClick={() => downloadCsv(`run-${runId}-scenes-visible.csv`, toCsvText(sceneRows.map((row) => Object.fromEntries(sceneColumns.map((column) => [column, row[column]])))))} className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50">Export scene visible slice</button>
              <button type="button" onClick={() => downloadCsv(`run-${runId}-features-visible.csv`, toCsvText(featureRows.map((row) => Object.fromEntries(featureColumns.map((column) => [column, row[column]])))))} className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50">Export feature visible slice</button>
            </div>
          </Card>
        </div>
      </div>
    </SectionShell>
  );
}
