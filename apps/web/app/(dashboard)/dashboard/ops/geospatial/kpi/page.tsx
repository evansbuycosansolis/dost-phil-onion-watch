"use client";

import { apiFetch } from "@phil-onion-watch/api-client";
import type { GeospatialKpiScorecard, GeospatialOpsTask } from "@phil-onion-watch/types";
import { DataTable, ErrorState, LoadingState, PageHeader, SectionShell, StatCard } from "@phil-onion-watch/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { GeospatialOpsNav } from "../../../../../../components/geospatial-ops-nav";
import { kpiTemplateMetrics, parseJsonInput, toPrettyJson } from "../../../../../../lib/geospatial-playbooks";
import { useAuth } from "../../../../../providers";

function statusClass(status: string) {
  if (status === "green") return "bg-emerald-100 text-emerald-700";
  if (status === "yellow") return "bg-amber-100 text-amber-700";
  if (status === "red") return "bg-rose-100 text-rose-700";
  return "bg-slate-100 text-slate-700";
}

function toRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }
  return value as Record<string, unknown>;
}

function toStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((row): row is string => typeof row === "string" && row.length > 0);
}

export default function GeospatialKpiPage() {
  const { token } = useAuth();
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [periodMonth, setPeriodMonth] = useState(new Date().toISOString().slice(0, 10));
  const [regionScope, setRegionScope] = useState("Occidental Mindoro");
  const [metricsJson, setMetricsJson] = useState(toPrettyJson(kpiTemplateMetrics));
  const [thresholdsJson, setThresholdsJson] = useState("{}");
  const [sourcesJson, setSourcesJson] = useState(toPrettyJson({ from: ["dashboard", "jobs", "audit"] }));

  const listQuery = useQuery({
    queryKey: ["geospatial-kpi-scorecards", token],
    queryFn: () => apiFetch<GeospatialKpiScorecard[]>("/api/v1/geospatial/kpi/scorecards?limit=200", { token }),
    enabled: !!token,
  });

  useEffect(() => {
    if (!selectedId && listQuery.data && listQuery.data.length > 0) {
      setSelectedId(listQuery.data[0].id);
    }
  }, [selectedId, listQuery.data]);

  const detailQuery = useQuery({
    queryKey: ["geospatial-kpi-scorecard", token, selectedId],
    queryFn: () => apiFetch<GeospatialKpiScorecard>(`/api/v1/geospatial/kpi/scorecards/${selectedId}`, { token }),
    enabled: !!token && selectedId != null,
  });

  const taskQuery = useQuery({
    queryKey: ["geospatial-ops-kpi-tasks", token],
    queryFn: () => apiFetch<GeospatialOpsTask[]>("/api/v1/geospatial/ops/tasks?task_type=kpi_scorecard_review&limit=50", { token }),
    enabled: !!token,
  });

  useEffect(() => {
    if (!detailQuery.data) return;
    setPeriodMonth(detailQuery.data.period_month);
    setRegionScope(detailQuery.data.region_scope);
    setMetricsJson(toPrettyJson(detailQuery.data.metrics));
    setThresholdsJson(toPrettyJson(detailQuery.data.thresholds));
    setSourcesJson(toPrettyJson(detailQuery.data.source_pointers));
  }, [detailQuery.data]);

  const latestSummary = useMemo(() => {
    const metricStatuses = (detailQuery.data?.source_pointers?.metric_statuses as Record<string, string> | undefined) ?? {};
    const values = Object.values(metricStatuses);
    return {
      green: values.filter((value) => value === "green").length,
      yellow: values.filter((value) => value === "yellow").length,
      red: values.filter((value) => value === "red").length,
    };
  }, [detailQuery.data?.source_pointers]);

  const traceability = useMemo(() => {
    const sourcePointers = toRecord(detailQuery.data?.source_pointers);
    const traceabilityPayload = toRecord(sourcePointers.traceability);
    const sourceCounts = Object.entries(toRecord(traceabilityPayload.source_counts))
      .filter(([, value]) => typeof value === "number")
      .map(([metric, count]) => ({ metric, count: Number(count) }))
      .sort((left, right) => right.count - left.count);
    const supportingLinksPayload = toRecord(traceabilityPayload.supporting_links);
    const supportingLinks = {
      incidents: toStringArray(supportingLinksPayload.incidents),
      workflows: toStringArray(supportingLinksPayload.workflows),
      deliveries: toStringArray(supportingLinksPayload.deliveries),
      reports: toStringArray(supportingLinksPayload.reports),
      audit: toStringArray(supportingLinksPayload.audit),
    };
    const artifacts = toRecord(sourcePointers.artifacts);
    return { sourceCounts, supportingLinks, artifacts };
  }, [detailQuery.data?.source_pointers]);

  const createMutation = useMutation({
    mutationFn: async () =>
      apiFetch<GeospatialKpiScorecard>("/api/v1/geospatial/kpi/scorecards", {
        token,
        method: "POST",
        body: {
          period_month: periodMonth,
          region_scope: regionScope,
          metrics: parseJsonInput(metricsJson, {}),
          thresholds: parseJsonInput(thresholdsJson, {}),
          source_pointers: parseJsonInput(sourcesJson, {}),
        },
      }),
    onSuccess: async (created) => {
      setErrorMessage(null);
      setSelectedId(created.id);
      await queryClient.invalidateQueries({ queryKey: ["geospatial-kpi-scorecards"] });
      await queryClient.invalidateQueries({ queryKey: ["geospatial-kpi-scorecard"] });
      await queryClient.invalidateQueries({ queryKey: ["geospatial-ops-kpi-tasks"] });
    },
    onError: (error) => {
      setErrorMessage(error instanceof Error ? error.message : "Failed to create scorecard");
    },
  });

  const computeMutation = useMutation({
    mutationFn: async () => {
      if (!selectedId) return null;
      return apiFetch<GeospatialKpiScorecard>(`/api/v1/geospatial/kpi/scorecards/${selectedId}/compute`, {
        token,
        method: "POST",
        body: { thresholds: parseJsonInput(thresholdsJson, {}) },
      });
    },
    onSuccess: async () => {
      setErrorMessage(null);
      await queryClient.invalidateQueries({ queryKey: ["geospatial-kpi-scorecards"] });
      await queryClient.invalidateQueries({ queryKey: ["geospatial-kpi-scorecard"] });
    },
    onError: (error) => {
      setErrorMessage(error instanceof Error ? error.message : "Failed to compute scorecard");
    },
  });

  const monthlyAutomationMutation = useMutation({
    mutationFn: async () => apiFetch<GeospatialKpiScorecard>(`/api/v1/geospatial/automation/monthly-kpi?reporting_month=${periodMonth}`, { token, method: "POST" }),
    onSuccess: async (row) => {
      setErrorMessage(null);
      setSelectedId(row.id);
      await queryClient.invalidateQueries({ queryKey: ["geospatial-kpi-scorecards"] });
      await queryClient.invalidateQueries({ queryKey: ["geospatial-kpi-scorecard"] });
      await queryClient.invalidateQueries({ queryKey: ["geospatial-ops-kpi-tasks"] });
    },
    onError: (error) => {
      setErrorMessage(error instanceof Error ? error.message : "Failed to run monthly KPI automation");
    },
  });

  return (
    <div className="space-y-6">
      <PageHeader title="Geospatial KPI Scorecards" subtitle="Monthly KPI rollups with computed threshold traffic lights and review tasks." />
      <GeospatialOpsNav />

      {errorMessage ? <ErrorState message={errorMessage} /> : null}
      {listQuery.isLoading ? <LoadingState label="Loading KPI scorecards..." /> : null}
      {listQuery.error ? <ErrorState message="Failed to load KPI scorecards." /> : null}

      {detailQuery.data ? (
        <div className="grid gap-3 md:grid-cols-4">
          <StatCard label="Overall Status" value={detailQuery.data.computed_status.toUpperCase()} hint={detailQuery.data.period_month} />
          <StatCard label="Green Metrics" value={latestSummary.green} />
          <StatCard label="Yellow Metrics" value={latestSummary.yellow} />
          <StatCard label="Red Metrics" value={latestSummary.red} />
        </div>
      ) : null}

      <SectionShell title="Scorecards">
        <DataTable
          columns={[
            { key: "id", label: "ID" },
            {
              key: "period_month",
              label: "Month",
              render: (row) => (
                <button className="font-medium text-sky-700 hover:underline" type="button" onClick={() => setSelectedId((row as GeospatialKpiScorecard).id)}>
                  {(row as GeospatialKpiScorecard).period_month}
                </button>
              ),
            },
            { key: "region_scope", label: "Scope" },
            {
              key: "computed_status",
              label: "Status",
              render: (row) => (
                <span className={`rounded-full px-2 py-1 text-xs font-semibold ${statusClass((row as GeospatialKpiScorecard).computed_status)}`}>
                  {(row as GeospatialKpiScorecard).computed_status}
                </span>
              ),
            },
            { key: "updated_at", label: "Updated" },
          ]}
          rows={listQuery.data ?? []}
        />
      </SectionShell>

      <SectionShell title={selectedId ? `Scorecard Detail #${selectedId}` : "Create KPI Scorecard"}>
        {detailQuery.isFetching && selectedId ? <LoadingState label="Loading scorecard detail..." /> : null}
        <div className="grid gap-4 md:grid-cols-2">
          <label className="text-sm text-slate-600">
            Period Month
            <input className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5" type="date" value={periodMonth} onChange={(event) => setPeriodMonth(event.target.value)} />
          </label>
          <label className="text-sm text-slate-600">
            Region Scope
            <input className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5" value={regionScope} onChange={(event) => setRegionScope(event.target.value)} />
          </label>
          <label className="text-sm text-slate-600 md:col-span-2">
            Metrics JSON
            <textarea className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5 font-mono text-xs" rows={9} value={metricsJson} onChange={(event) => setMetricsJson(event.target.value)} />
          </label>
          <label className="text-sm text-slate-600 md:col-span-2">
            Thresholds JSON
            <textarea className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5 font-mono text-xs" rows={9} value={thresholdsJson} onChange={(event) => setThresholdsJson(event.target.value)} />
          </label>
          <label className="text-sm text-slate-600 md:col-span-2">
            Source Pointers JSON
            <textarea className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5 font-mono text-xs" rows={7} value={sourcesJson} onChange={(event) => setSourcesJson(event.target.value)} />
          </label>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <button className="rounded border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50" type="button" onClick={() => setMetricsJson(toPrettyJson(kpiTemplateMetrics))}>
            Create from template
          </button>
          <button className="rounded bg-slate-900 px-3 py-1.5 text-sm font-semibold text-white hover:bg-slate-700" type="button" onClick={() => createMutation.mutate()} disabled={createMutation.isPending}>
            Create scorecard
          </button>
          {selectedId ? (
            <button className="rounded bg-amber-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-amber-500" type="button" onClick={() => computeMutation.mutate()} disabled={computeMutation.isPending}>
              Compute traffic light
            </button>
          ) : null}
          <button className="rounded bg-emerald-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-emerald-500" type="button" onClick={() => monthlyAutomationMutation.mutate()} disabled={monthlyAutomationMutation.isPending}>
            Run monthly automation
          </button>
        </div>
      </SectionShell>

      <SectionShell title="KPI Traceability">
        {traceability.sourceCounts.length === 0 ? (
          <p className="text-sm text-slate-500">No traceability source counts were generated yet for this scorecard.</p>
        ) : (
          <DataTable
            columns={[
              { key: "metric", label: "Source Metric" },
              { key: "count", label: "Count" },
            ]}
            rows={traceability.sourceCounts}
          />
        )}

        <div className="mt-4 grid gap-3 md:grid-cols-2">
          {Object.entries(traceability.supportingLinks).map(([group, links]) => (
            <div key={group} className="rounded border border-slate-200 p-3">
              <h3 className="text-sm font-semibold capitalize text-slate-700">{group} evidence</h3>
              {links.length === 0 ? (
                <p className="mt-1 text-xs text-slate-500">No supporting links for this group.</p>
              ) : (
                <ul className="mt-2 space-y-1">
                  {links.slice(0, 8).map((link) => (
                    <li key={link}>
                      <a className="text-xs text-sky-700 hover:underline" href={link} target="_blank" rel="noreferrer">
                        {link}
                      </a>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>

        <div className="mt-4 rounded border border-slate-200 p-3">
          <h3 className="text-sm font-semibold text-slate-700">Generated monthly artifacts</h3>
          {Object.keys(traceability.artifacts).length === 0 ? (
            <p className="mt-1 text-xs text-slate-500">No automation artifacts are linked for this scorecard.</p>
          ) : (
            <div className="mt-2 space-y-1 text-xs text-slate-600">
              {Object.entries(traceability.artifacts).map(([key, value]) => (
                <div key={key}>
                  <span className="font-medium">{key}: </span>
                  <span>{String(value)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </SectionShell>

      <SectionShell title="KPI Review Tasks">
        {taskQuery.isLoading ? <LoadingState label="Loading KPI review tasks..." /> : null}
        {taskQuery.error ? <ErrorState message="Failed to load KPI review tasks." /> : null}
        <DataTable
          columns={[
            { key: "id", label: "Task ID" },
            { key: "title", label: "Title" },
            { key: "status", label: "Status" },
            { key: "priority", label: "Priority" },
            { key: "due_at", label: "Due" },
          ]}
          rows={taskQuery.data ?? []}
        />
      </SectionShell>
    </div>
  );
}
