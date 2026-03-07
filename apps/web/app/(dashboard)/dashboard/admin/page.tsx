"use client";

import { routes } from "@phil-onion-watch/config";
import {
  apiFetch,
  downloadAuditSlice,
  updateAnomalyThreshold,
  useAdminOverview,
  useAuditEventDiff,
  useAuditEvents,
  useAnomalyThresholdVersions,
  useAnomalyThresholds,
  useForecastDiagnostics,
} from "@phil-onion-watch/api-client";
import { DataTable, ErrorState, LoadingState, PageHeader, SectionShell, StatCard } from "@phil-onion-watch/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { useAuth } from "../../../providers";

export default function AdminConsolePage() {
  const { token } = useAuth();
  const queryClient = useQueryClient();
  const overview = useAdminOverview(token);
  const diagnostics = useForecastDiagnostics(token);
  const thresholds = useAnomalyThresholds(token);

  const users = useQuery({
    queryKey: ["users", token],
    queryFn: () => apiFetch<Record<string, unknown>[]>("/api/v1/users", { token }),
    enabled: !!token,
  });
  const observability = useQuery({
    queryKey: ["admin-observability-overview", token],
    queryFn: () => apiFetch<Record<string, unknown>>("/api/v1/admin/observability/overview?window_minutes=60", { token }),
    enabled: !!token,
  });
  const geospatialOverview = useQuery({
    queryKey: ["admin-geospatial-overview", token],
    queryFn: () => apiFetch<{ total_aois: number; total_features: number; latest_observation_date: string | null }>("/api/v1/geospatial/dashboard/provincial", { token }),
    enabled: !!token,
  });
  const [auditEntityTypeFilter, setAuditEntityTypeFilter] = useState("");
  const [auditEntityIdFilter, setAuditEntityIdFilter] = useState("");
  const [auditActionTypeFilter, setAuditActionTypeFilter] = useState("");
  const [selectedAuditEventId, setSelectedAuditEventId] = useState<number | undefined>(undefined);
  const [auditExportFormat, setAuditExportFormat] = useState<"csv" | "json">("csv");

  const auditEvents = useAuditEvents(token, {
    limit: 300,
    entityType: auditEntityTypeFilter || undefined,
    entityId: auditEntityIdFilter || undefined,
    actionType: auditActionTypeFilter || undefined,
  });
  const auditDiff = useAuditEventDiff(token, selectedAuditEventId);

  const [selectedAnomalyType, setSelectedAnomalyType] = useState("");
  const [patchText, setPatchText] = useState("{}");
  const [changeReason, setChangeReason] = useState("Analyst threshold adjustment");
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedAnomalyType && thresholds.data && thresholds.data.length > 0) {
      setSelectedAnomalyType(thresholds.data[0].anomaly_type);
    }
  }, [selectedAnomalyType, thresholds.data]);

  useEffect(() => {
    if (!selectedAuditEventId && auditEvents.data && auditEvents.data.length > 0) {
      setSelectedAuditEventId(auditEvents.data[0].id);
    }
  }, [selectedAuditEventId, auditEvents.data]);

  useEffect(() => {
    if (!auditEvents.data || auditEvents.data.length === 0) {
      return;
    }
    if (!selectedAuditEventId) {
      return;
    }
    const exists = auditEvents.data.some((row) => row.id === selectedAuditEventId);
    if (!exists) {
      setSelectedAuditEventId(auditEvents.data[0].id);
    }
  }, [auditEvents.data, selectedAuditEventId]);

  const thresholdVersions = useAnomalyThresholdVersions(token, selectedAnomalyType || undefined);

  const updateThresholdMutation = useMutation({
    mutationFn: async () => {
      const parsed = JSON.parse(patchText) as Record<string, number | boolean>;
      if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
        throw new Error("Threshold patch must be a JSON object.");
      }
      return updateAnomalyThreshold(token, selectedAnomalyType, parsed, changeReason);
    },
    onSuccess: async () => {
      setFormError(null);
      setPatchText("{}");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["anomaly-thresholds", token] }),
        queryClient.invalidateQueries({ queryKey: ["anomaly-threshold-versions", token, selectedAnomalyType] }),
      ]);
    },
    onError: (error: unknown) => {
      setFormError(error instanceof Error ? error.message : "Failed to update thresholds.");
    },
  });

  const exportAuditMutation = useMutation({
    mutationFn: async () => {
      const blob = await downloadAuditSlice(token, {
        format: auditExportFormat,
        limit: 1000,
        entityType: auditEntityTypeFilter || undefined,
        entityId: auditEntityIdFilter || undefined,
        actionType: auditActionTypeFilter || undefined,
      });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      const stamp = new Date().toISOString().replace(/[:]/g, "-");
      link.download = `audit_slice_${stamp}.${auditExportFormat}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    },
  });

  if (
    overview.isLoading ||
    users.isLoading ||
    diagnostics.isLoading ||
    thresholds.isLoading ||
    thresholdVersions.isLoading ||
    observability.isLoading ||
    geospatialOverview.isLoading ||
    auditEvents.isLoading
  ) {
    return <LoadingState label="Loading admin console..." />;
  }
  if (
    overview.error ||
    users.error ||
    diagnostics.error ||
    thresholds.error ||
    thresholdVersions.error ||
    observability.error ||
    geospatialOverview.error ||
    auditEvents.error
  ) {
    return <ErrorState message="Failed to load admin console" />;
  }

  const data = overview.data;
  const diagnosticsSummary = data?.forecast_model_diagnostics;
  const distributionStatus = data?.report_distribution_status ?? {};
  const selectedCounts = diagnosticsSummary?.selected_model_counts ?? {};
  const avgScores = diagnosticsSummary?.model_avg_score ?? {};
  const avgMae = diagnosticsSummary?.model_avg_holdout_mae ?? {};

  const modelRows = Object.keys(selectedCounts).map((modelName) => ({
    model_name: modelName,
    selected_count: selectedCounts[modelName],
    avg_score: Number(avgScores[modelName] ?? 0).toFixed(4),
    avg_holdout_mae: Number(avgMae[modelName] ?? 0).toFixed(4),
  }));

  const municipalityRows = (diagnostics.data?.municipality_diagnostics ?? []).map((row) => ({
    municipality_name: row.municipality_name,
    selected_model: row.selected_model ?? "n/a",
    selected_score: row.selected_score == null ? "n/a" : Number(row.selected_score).toFixed(4),
    fallback_order: (row.fallback_order ?? []).join(" > "),
  }));

  const thresholdRows = (thresholds.data ?? []).map((row) => ({
    anomaly_type: row.anomaly_type,
    version: row.version,
    updated_at: row.updated_at,
    thresholds: JSON.stringify(row.thresholds),
  }));

  const thresholdVersionRows = (thresholdVersions.data ?? []).map((row) => ({
    version: row.version,
    changed_at: row.changed_at,
    changed_by: row.changed_by ?? "system",
    change_reason: row.change_reason ?? "",
    thresholds: JSON.stringify(row.thresholds),
  }));
  const auditEntityTypeOptions = Array.from(new Set((auditEvents.data ?? []).map((row) => String(row.entity_type)))).sort();
  const auditActionTypeOptions = Array.from(new Set((auditEvents.data ?? []).map((row) => String(row.action_type)))).sort();
  const auditRows = (auditEvents.data ?? []).map((row) => ({
    id: row.id,
    timestamp: row.timestamp,
    actor_user_id: row.actor_user_id ?? "system",
    action_type: row.action_type,
    entity_type: row.entity_type,
    entity_id: row.entity_id,
    correlation_id: row.correlation_id ?? "",
    change_count: auditDiff.data && auditDiff.data.event.id === row.id ? auditDiff.data.summary.total_changes : "inspect",
  }));
  const apiObservability = (observability.data?.api as Record<string, unknown>) ?? {};
  const jobObservability = (observability.data?.jobs as Record<string, unknown>) ?? {};
  const degradedEndpoints = (apiObservability.degraded_endpoints as Record<string, unknown>[]) ?? [];
  const failingJobs = (jobObservability.failing_jobs as Record<string, unknown>[]) ?? [];
  const activeObservabilityAlerts = (observability.data?.active_alerts as Record<string, unknown>[]) ?? [];
  const diffRows = (auditDiff.data?.changes ?? []).map((change) => ({
    path: change.path,
    change_type: change.change_type,
    before_value: change.before_value == null ? "" : JSON.stringify(change.before_value),
    after_value: change.after_value == null ? "" : JSON.stringify(change.after_value),
  }));

  return (
    <div>
      <PageHeader
        title="Admin Console"
        subtitle="Users, roles, ingestion status, jobs, and system controls"
        actions={
          <a
            href={routes.dashboardGeospatialAOIs}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Open Geospatial AOIs
          </a>
        }
      />

      <div className="mb-6 grid gap-4 md:grid-cols-5">
        <StatCard label="Users" value={String(data?.users_count ?? 0)} />
        <StatCard label="Document Index Status" value={String(data?.document_ingestion_status.latest_status ?? "unknown")} />
        <StatCard label="Pipeline Runs" value={String(data?.pipeline_runs.length ?? 0)} />
        <StatCard label="Queued Deliveries" value={String(distributionStatus.queued ?? 0)} />
        <StatCard label="Model Coverage" value={String(diagnosticsSummary?.municipalities_covered ?? 0)} hint="Municipalities with model diagnostics" />
      </div>

      <div className="mb-6 grid gap-4 md:grid-cols-3">
        <StatCard label="Geospatial AOIs" value={String(geospatialOverview.data?.total_aois ?? 0)} />
        <StatCard label="Geospatial Features" value={String(geospatialOverview.data?.total_features ?? 0)} />
        <StatCard label="Latest Geospatial Observation" value={geospatialOverview.data?.latest_observation_date ?? "n/a"} />
      </div>

      <SectionShell title="Users and Roles">
        <DataTable
          columns={[
            { key: "full_name", label: "Name" },
            { key: "email", label: "Email" },
            { key: "roles", label: "Roles", render: (row) => (row.roles as string[]).join(", ") },
            { key: "is_active", label: "Active" },
          ]}
          rows={users.data ?? []}
        />
      </SectionShell>

      <SectionShell title="Audit Diff Viewer">
        <div className="mb-3 grid gap-3 md:grid-cols-5">
          <label className="text-sm text-slate-700">
            Entity Type
            <select
              value={auditEntityTypeFilter}
              onChange={(event) => setAuditEntityTypeFilter(event.target.value)}
              className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
            >
              <option value="">All entities</option>
              {auditEntityTypeOptions.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm text-slate-700">
            Action Type
            <select
              value={auditActionTypeFilter}
              onChange={(event) => setAuditActionTypeFilter(event.target.value)}
              className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
            >
              <option value="">All actions</option>
              {auditActionTypeOptions.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm text-slate-700">
            Entity ID
            <input
              value={auditEntityIdFilter}
              onChange={(event) => setAuditEntityIdFilter(event.target.value)}
              placeholder="Exact entity id"
              className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
            />
          </label>
          <label className="text-sm text-slate-700">
            Export Format
            <select
              value={auditExportFormat}
              onChange={(event) => setAuditExportFormat(event.target.value as "csv" | "json")}
              className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
            >
              <option value="csv">CSV</option>
              <option value="json">JSON</option>
            </select>
          </label>
          <div className="flex items-end gap-2">
            <button
              onClick={() => {
                setSelectedAuditEventId(undefined);
                queryClient.invalidateQueries({ queryKey: ["audit-events", token] });
              }}
              className="rounded border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700"
            >
              Refresh
            </button>
            <button
              onClick={() => exportAuditMutation.mutate()}
              className="rounded border border-brand-300 bg-brand-50 px-3 py-2 text-sm font-medium text-brand-700"
            >
              Export Slice
            </button>
          </div>
        </div>
        {exportAuditMutation.error ? <p className="mb-3 text-xs text-rose-700">Failed to export audit slice.</p> : null}
        <DataTable
          columns={[
            { key: "timestamp", label: "Timestamp" },
            { key: "actor_user_id", label: "Actor" },
            { key: "action_type", label: "Action" },
            { key: "entity_type", label: "Entity" },
            { key: "entity_id", label: "Entity ID" },
            { key: "correlation_id", label: "Correlation" },
            { key: "change_count", label: "Changes" },
            {
              key: "id",
              label: "Inspect",
              render: (row) => (
                <button
                  onClick={() => setSelectedAuditEventId(Number(row.id))}
                  className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-700"
                >
                  {selectedAuditEventId === Number(row.id) ? "Inspecting" : "Inspect"}
                </button>
              ),
            },
          ]}
          rows={auditRows}
        />

        {auditDiff.isLoading ? <LoadingState label="Loading structured diff..." /> : null}
        {auditDiff.error ? <ErrorState message="Failed to load selected audit diff." /> : null}
        {auditDiff.data ? (
          <div className="mt-4 rounded-lg border border-slate-200 p-4">
            <div className="mb-3 grid gap-3 md:grid-cols-4">
              <StatCard label="Total Changes" value={auditDiff.data.summary.total_changes} />
              <StatCard label="Added" value={auditDiff.data.summary.added} />
              <StatCard label="Removed" value={auditDiff.data.summary.removed} />
              <StatCard label="Modified" value={auditDiff.data.summary.modified} />
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <h3 className="mb-2 text-sm font-semibold text-slate-700">Before Payload</h3>
                <pre className="max-h-72 overflow-auto rounded border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700">
                  {JSON.stringify(auditDiff.data.event.before_payload ?? {}, null, 2)}
                </pre>
              </div>
              <div>
                <h3 className="mb-2 text-sm font-semibold text-slate-700">After Payload</h3>
                <pre className="max-h-72 overflow-auto rounded border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700">
                  {JSON.stringify(auditDiff.data.event.after_payload ?? {}, null, 2)}
                </pre>
              </div>
            </div>
            <div className="mt-4">
              <DataTable
                columns={[
                  { key: "path", label: "Path" },
                  { key: "change_type", label: "Type" },
                  { key: "before_value", label: "Before" },
                  { key: "after_value", label: "After" },
                ]}
                rows={diffRows}
              />
            </div>
          </div>
        ) : null}
      </SectionShell>

      <SectionShell title="Anomaly Threshold Controls">
        <DataTable
          columns={[
            { key: "anomaly_type", label: "Anomaly Type" },
            { key: "version", label: "Version" },
            { key: "updated_at", label: "Updated At" },
            { key: "thresholds", label: "Thresholds" },
          ]}
          rows={thresholdRows}
        />
        <div className="mt-4 rounded-lg border border-slate-200 p-4">
          <div className="grid gap-3 md:grid-cols-2">
            <label className="text-sm text-slate-700">
              Anomaly Type
              <select
                value={selectedAnomalyType}
                onChange={(event) => setSelectedAnomalyType(event.target.value)}
                className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
              >
                {(thresholds.data ?? []).map((row) => (
                  <option key={row.anomaly_type} value={row.anomaly_type}>
                    {row.anomaly_type}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-sm text-slate-700">
              Change Reason
              <input
                value={changeReason}
                onChange={(event) => setChangeReason(event.target.value)}
                className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
              />
            </label>
          </div>
          <label className="mt-3 block text-sm text-slate-700">
            Threshold Patch JSON
            <textarea
              value={patchText}
              onChange={(event) => setPatchText(event.target.value)}
              rows={5}
              className="mt-1 w-full rounded border border-slate-300 px-2 py-1 font-mono text-xs"
            />
          </label>
          {formError ? <p className="mt-2 text-xs text-rose-700">{formError}</p> : null}
          <button
            onClick={() => updateThresholdMutation.mutate()}
            className="mt-3 rounded border border-slate-300 px-3 py-2 text-sm font-medium text-slate-800"
          >
            Apply Threshold Update
          </button>
        </div>
      </SectionShell>

      <SectionShell title="Threshold Version History">
        <DataTable
          columns={[
            { key: "version", label: "Version" },
            { key: "changed_at", label: "Changed At" },
            { key: "changed_by", label: "Changed By" },
            { key: "change_reason", label: "Reason" },
            { key: "thresholds", label: "Thresholds" },
          ]}
          rows={thresholdVersionRows}
        />
      </SectionShell>

      <SectionShell title="Forecast Model Performance Registry">
        <DataTable
          columns={[
            { key: "model_name", label: "Model" },
            { key: "selected_count", label: "Selections" },
            { key: "avg_score", label: "Avg Score" },
            { key: "avg_holdout_mae", label: "Avg Holdout MAE" },
          ]}
          rows={modelRows}
        />
      </SectionShell>

      <SectionShell title="Municipality Model Selection">
        <DataTable
          columns={[
            { key: "municipality_name", label: "Municipality" },
            { key: "selected_model", label: "Selected Model" },
            { key: "selected_score", label: "Selected Score" },
            { key: "fallback_order", label: "Fallback Order" },
          ]}
          rows={municipalityRows}
        />
      </SectionShell>

      <SectionShell title="Job Status">
        <DataTable
          columns={[
            { key: "job_name", label: "Job" },
            { key: "status", label: "Status" },
            { key: "correlation_id", label: "Correlation" },
            { key: "started_at", label: "Started" },
            { key: "finished_at", label: "Finished" },
          ]}
          rows={data?.job_status ?? []}
        />
      </SectionShell>

      <SectionShell title="Report Distribution Status">
        <DataTable
          columns={[{ key: "status", label: "Status" }, { key: "count", label: "Count" }]}
          rows={Object.entries(distributionStatus).map(([status, count]) => ({ status, count }))}
        />
      </SectionShell>

      <SectionShell title="Observability Status">
        <div className="mb-3 grid gap-4 md:grid-cols-4">
          <StatCard label="API Requests (1h)" value={String(apiObservability.requests_total ?? 0)} />
          <StatCard label="API Error Rate (1h)" value={String(apiObservability.server_error_rate ?? 0)} />
          <StatCard label="Job Runs (1h)" value={String(jobObservability.runs_total ?? 0)} />
          <StatCard label="Job Failure Rate (1h)" value={String(jobObservability.failure_rate ?? 0)} />
        </div>
        <DataTable
          columns={[
            { key: "method", label: "Method" },
            { key: "path", label: "Path" },
            { key: "request_count", label: "Requests" },
            { key: "server_error_rate", label: "Error Rate" },
            { key: "p95_latency_ms", label: "P95 Latency (ms)" },
          ]}
          rows={degradedEndpoints}
        />
      </SectionShell>

      <SectionShell title="Observability Alerts">
        <DataTable
          columns={[
            { key: "alert_type", label: "Type" },
            { key: "severity", label: "Severity" },
            { key: "summary", label: "Summary" },
            { key: "updated_at", label: "Updated" },
          ]}
          rows={activeObservabilityAlerts}
        />
      </SectionShell>

      <SectionShell title="Failing Jobs">
        <DataTable
          columns={[
            { key: "job_name", label: "Job" },
            { key: "run_count", label: "Runs" },
            { key: "failed_count", label: "Failed" },
            { key: "failure_rate", label: "Failure Rate" },
            { key: "p95_duration_ms", label: "P95 Duration (ms)" },
          ]}
          rows={failingJobs}
        />
      </SectionShell>

      <SectionShell title="Pipeline Runs">
        <DataTable
          columns={[{ key: "id", label: "Run" }, { key: "status", label: "Status" }, { key: "details", label: "Details" }]}
          rows={data?.pipeline_runs ?? []}
        />
      </SectionShell>
    </div>
  );
}
