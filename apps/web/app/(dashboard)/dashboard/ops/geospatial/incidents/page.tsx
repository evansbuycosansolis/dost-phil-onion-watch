"use client";

import { apiFetch } from "@phil-onion-watch/api-client";
import type { GeospatialIncident, GeospatialIncidentSeverity, GeospatialIncidentStatus, GeospatialOpsTask } from "@phil-onion-watch/types";
import { DataTable, ErrorState, LoadingState, PageHeader, SectionShell, StatCard } from "@phil-onion-watch/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { GeospatialOpsNav } from "../../../../../../components/geospatial-ops-nav";
import { incidentTemplate, parseJsonInput, toPrettyJson } from "../../../../../../lib/geospatial-playbooks";
import { useAuth } from "../../../../../providers";

const severities: GeospatialIncidentSeverity[] = ["SEV0", "SEV1", "SEV2", "SEV3"];
const statuses: GeospatialIncidentStatus[] = ["open", "mitigating", "resolved", "postmortem"];

function severityClass(value: GeospatialIncidentSeverity) {
  if (value === "SEV0" || value === "SEV1") return "bg-rose-100 text-rose-700";
  if (value === "SEV2") return "bg-amber-100 text-amber-700";
  return "bg-slate-100 text-slate-700";
}

function statusClass(value: GeospatialIncidentStatus) {
  if (value === "resolved" || value === "postmortem") return "bg-emerald-100 text-emerald-700";
  if (value === "mitigating") return "bg-amber-100 text-amber-700";
  return "bg-rose-100 text-rose-700";
}

function calcSloState(incident: GeospatialIncident) {
  const started = new Date(incident.started_at).getTime();
  const due = started + incident.slo_target_minutes * 60 * 1000;
  const now = Date.now();
  return {
    dueAt: new Date(due).toISOString(),
    overdue: incident.status === "open" || incident.status === "mitigating" ? now > due : false,
  };
}

export default function GeospatialIncidentsPage() {
  const { token } = useAuth();
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [severity, setSeverity] = useState<GeospatialIncidentSeverity>("SEV3");
  const [statusValue, setStatusValue] = useState<GeospatialIncidentStatus>("open");
  const [summary, setSummary] = useState(incidentTemplate.summary);
  const [impact, setImpact] = useState(incidentTemplate.impact);
  const [rootCause, setRootCause] = useState(incidentTemplate.root_cause);
  const [assignedToUserId, setAssignedToUserId] = useState("");
  const [sloTargetMinutes, setSloTargetMinutes] = useState("240");
  const [correctiveActionsJson, setCorrectiveActionsJson] = useState(toPrettyJson(incidentTemplate.corrective_actions));
  const [evidencePackJson, setEvidencePackJson] = useState(toPrettyJson(incidentTemplate.evidence_pack));
  const [commsLogJson, setCommsLogJson] = useState("[]");
  const [resolutionNote, setResolutionNote] = useState("");
  const [lessonsLearned, setLessonsLearned] = useState("");

  const listQuery = useQuery({
    queryKey: ["geospatial-incidents", token],
    queryFn: () => apiFetch<GeospatialIncident[]>("/api/v1/geospatial/incidents?limit=200", { token }),
    enabled: !!token,
  });

  const summaryStats = useMemo(() => {
    const rows = listQuery.data ?? [];
    return {
      total: rows.length,
      open: rows.filter((row) => row.status === "open").length,
      mitigating: rows.filter((row) => row.status === "mitigating").length,
      resolved: rows.filter((row) => row.status === "resolved" || row.status === "postmortem").length,
    };
  }, [listQuery.data]);

  useEffect(() => {
    if (!selectedId && listQuery.data && listQuery.data.length > 0) {
      setSelectedId(listQuery.data[0].id);
    }
  }, [selectedId, listQuery.data]);

  const detailQuery = useQuery({
    queryKey: ["geospatial-incident", token, selectedId],
    queryFn: () => apiFetch<GeospatialIncident>(`/api/v1/geospatial/incidents/${selectedId}`, { token }),
    enabled: !!token && selectedId != null,
  });

  const taskQuery = useQuery({
    queryKey: ["geospatial-incident-tasks", token],
    queryFn: () => apiFetch<GeospatialOpsTask[]>("/api/v1/geospatial/ops/tasks?task_type=incident_slo_breach&limit=60", { token }),
    enabled: !!token,
  });

  useEffect(() => {
    if (!detailQuery.data) return;
    setSeverity(detailQuery.data.severity);
    setStatusValue(detailQuery.data.status);
    setSummary(detailQuery.data.summary);
    setImpact(detailQuery.data.impact ?? "");
    setRootCause(detailQuery.data.root_cause ?? "");
    setAssignedToUserId(detailQuery.data.assigned_to_user_id ? String(detailQuery.data.assigned_to_user_id) : "");
    setSloTargetMinutes(String(detailQuery.data.slo_target_minutes));
    setCorrectiveActionsJson(toPrettyJson(detailQuery.data.corrective_actions));
    setEvidencePackJson(toPrettyJson(detailQuery.data.evidence_pack));
    setCommsLogJson(toPrettyJson(detailQuery.data.comms_log));
  }, [detailQuery.data]);

  const createMutation = useMutation({
    mutationFn: async () =>
      apiFetch<GeospatialIncident>("/api/v1/geospatial/incidents", {
        token,
        method: "POST",
        body: {
          severity,
          summary,
          impact: impact || null,
          root_cause: rootCause || null,
          corrective_actions: parseJsonInput(correctiveActionsJson, []),
          evidence_pack: parseJsonInput(evidencePackJson, {}),
          comms_log: parseJsonInput(commsLogJson, []),
          assigned_to_user_id: assignedToUserId ? Number(assignedToUserId) : null,
          slo_target_minutes: Number(sloTargetMinutes),
        },
      }),
    onSuccess: async (created) => {
      setErrorMessage(null);
      setSelectedId(created.id);
      await queryClient.invalidateQueries({ queryKey: ["geospatial-incidents"] });
      await queryClient.invalidateQueries({ queryKey: ["geospatial-incident"] });
    },
    onError: (error) => {
      setErrorMessage(error instanceof Error ? error.message : "Failed to create incident");
    },
  });

  const updateMutation = useMutation({
    mutationFn: async () => {
      if (!selectedId) return null;
      return apiFetch<GeospatialIncident>(`/api/v1/geospatial/incidents/${selectedId}`, {
        token,
        method: "PATCH",
        body: {
          severity,
          status: statusValue,
          summary,
          impact: impact || null,
          root_cause: rootCause || null,
          corrective_actions: parseJsonInput(correctiveActionsJson, []),
          evidence_pack: parseJsonInput(evidencePackJson, {}),
          comms_log: parseJsonInput(commsLogJson, []),
          assigned_to_user_id: assignedToUserId ? Number(assignedToUserId) : null,
          slo_target_minutes: Number(sloTargetMinutes),
        },
      });
    },
    onSuccess: async () => {
      setErrorMessage(null);
      await queryClient.invalidateQueries({ queryKey: ["geospatial-incidents"] });
      await queryClient.invalidateQueries({ queryKey: ["geospatial-incident"] });
    },
    onError: (error) => {
      setErrorMessage(error instanceof Error ? error.message : "Failed to update incident");
    },
  });

  const resolveMutation = useMutation({
    mutationFn: async () => {
      if (!selectedId) return null;
      return apiFetch<GeospatialIncident>(`/api/v1/geospatial/incidents/${selectedId}/resolve`, {
        token,
        method: "POST",
        body: {
          root_cause: rootCause || null,
          corrective_actions: parseJsonInput(correctiveActionsJson, []),
          evidence_pack: parseJsonInput(evidencePackJson, {}),
          resolution_note: resolutionNote || null,
        },
      });
    },
    onSuccess: async () => {
      setErrorMessage(null);
      await queryClient.invalidateQueries({ queryKey: ["geospatial-incidents"] });
      await queryClient.invalidateQueries({ queryKey: ["geospatial-incident"] });
    },
    onError: (error) => {
      setErrorMessage(error instanceof Error ? error.message : "Failed to resolve incident");
    },
  });

  const postmortemMutation = useMutation({
    mutationFn: async () => {
      if (!selectedId) return null;
      return apiFetch<GeospatialIncident>(`/api/v1/geospatial/incidents/${selectedId}/postmortem`, {
        token,
        method: "POST",
        body: {
          root_cause: rootCause || "Postmortem root cause required",
          corrective_actions: parseJsonInput(correctiveActionsJson, []),
          evidence_pack: parseJsonInput(evidencePackJson, {}),
          lessons_learned: lessonsLearned || null,
        },
      });
    },
    onSuccess: async () => {
      setErrorMessage(null);
      await queryClient.invalidateQueries({ queryKey: ["geospatial-incidents"] });
      await queryClient.invalidateQueries({ queryKey: ["geospatial-incident"] });
    },
    onError: (error) => {
      setErrorMessage(error instanceof Error ? error.message : "Failed to complete postmortem");
    },
  });

  const sloCheckMutation = useMutation({
    mutationFn: async () => apiFetch<GeospatialOpsTask[]>("/api/v1/geospatial/automation/incident-slo-checks", { token, method: "POST" }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["geospatial-incident-tasks"] });
      await queryClient.invalidateQueries({ queryKey: ["geospatial-incidents"] });
    },
  });

  return (
    <div className="space-y-6">
      <PageHeader title="Geospatial Incident Command" subtitle="Track severity, mitigation SLO, evidence packs, and postmortem lifecycle." />
      <GeospatialOpsNav />
      {errorMessage ? <ErrorState message={errorMessage} /> : null}

      <div className="grid gap-3 md:grid-cols-4">
        <StatCard label="Total" value={summaryStats.total} />
        <StatCard label="Open" value={summaryStats.open} />
        <StatCard label="Mitigating" value={summaryStats.mitigating} />
        <StatCard label="Resolved/Postmortem" value={summaryStats.resolved} />
      </div>

      {listQuery.isLoading ? <LoadingState label="Loading incidents..." /> : null}
      {listQuery.error ? <ErrorState message="Failed to load incidents." /> : null}

      <SectionShell title="Incidents">
        <DataTable
          columns={[
            { key: "incident_key", label: "Incident" },
            {
              key: "severity",
              label: "Severity",
              render: (row) => (
                <span className={`rounded-full px-2 py-1 text-xs font-semibold ${severityClass((row as GeospatialIncident).severity)}`}>
                  {(row as GeospatialIncident).severity}
                </span>
              ),
            },
            {
              key: "status",
              label: "Status",
              render: (row) => (
                <span className={`rounded-full px-2 py-1 text-xs font-semibold ${statusClass((row as GeospatialIncident).status)}`}>
                  {(row as GeospatialIncident).status}
                </span>
              ),
            },
            {
              key: "summary",
              label: "Summary",
              render: (row) => (
                <button className="text-left text-sky-700 hover:underline" type="button" onClick={() => setSelectedId((row as GeospatialIncident).id)}>
                  {(row as GeospatialIncident).summary}
                </button>
              ),
            },
            { key: "started_at", label: "Started" },
          ]}
          rows={listQuery.data ?? []}
        />
      </SectionShell>

      <SectionShell title={selectedId ? `Incident Detail #${selectedId}` : "Create Incident"}>
        {detailQuery.isFetching && selectedId ? <LoadingState label="Loading incident detail..." /> : null}
        {detailQuery.data ? (
          <p className={`mb-3 rounded px-3 py-2 text-sm ${calcSloState(detailQuery.data).overdue ? "bg-rose-50 text-rose-700" : "bg-slate-50 text-slate-700"}`}>
            SLO due at {calcSloState(detailQuery.data).dueAt} {calcSloState(detailQuery.data).overdue ? "(OVERDUE)" : ""}
          </p>
        ) : null}
        <div className="grid gap-4 md:grid-cols-2">
          <label className="text-sm text-slate-600">
            Severity
            <select className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5" value={severity} onChange={(event) => setSeverity(event.target.value as GeospatialIncidentSeverity)}>
              {severities.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm text-slate-600">
            Status
            <select className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5" value={statusValue} onChange={(event) => setStatusValue(event.target.value as GeospatialIncidentStatus)}>
              {statuses.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm text-slate-600 md:col-span-2">
            Summary
            <input className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5" value={summary} onChange={(event) => setSummary(event.target.value)} />
          </label>
          <label className="text-sm text-slate-600 md:col-span-2">
            Impact
            <textarea className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5" rows={2} value={impact} onChange={(event) => setImpact(event.target.value)} />
          </label>
          <label className="text-sm text-slate-600 md:col-span-2">
            Root Cause
            <textarea className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5" rows={2} value={rootCause} onChange={(event) => setRootCause(event.target.value)} />
          </label>
          <label className="text-sm text-slate-600">
            Assigned To User ID
            <input className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5" value={assignedToUserId} onChange={(event) => setAssignedToUserId(event.target.value)} />
          </label>
          <label className="text-sm text-slate-600">
            SLO Target Minutes
            <input className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5" type="number" min={1} value={sloTargetMinutes} onChange={(event) => setSloTargetMinutes(event.target.value)} />
          </label>
          <label className="text-sm text-slate-600 md:col-span-2">
            Corrective Actions JSON
            <textarea className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5 font-mono text-xs" rows={7} value={correctiveActionsJson} onChange={(event) => setCorrectiveActionsJson(event.target.value)} />
          </label>
          <label className="text-sm text-slate-600 md:col-span-2">
            Evidence Pack JSON
            <textarea className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5 font-mono text-xs" rows={7} value={evidencePackJson} onChange={(event) => setEvidencePackJson(event.target.value)} />
          </label>
          <label className="text-sm text-slate-600 md:col-span-2">
            Comms Log JSON
            <textarea className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5 font-mono text-xs" rows={7} value={commsLogJson} onChange={(event) => setCommsLogJson(event.target.value)} />
          </label>
        </div>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <label className="text-sm text-slate-600">
            Resolution Note
            <input className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5" value={resolutionNote} onChange={(event) => setResolutionNote(event.target.value)} />
          </label>
          <label className="text-sm text-slate-600">
            Lessons Learned
            <input className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5" value={lessonsLearned} onChange={(event) => setLessonsLearned(event.target.value)} />
          </label>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
            onClick={() => {
              setSummary(incidentTemplate.summary);
              setImpact(incidentTemplate.impact);
              setRootCause(incidentTemplate.root_cause);
              setCorrectiveActionsJson(toPrettyJson(incidentTemplate.corrective_actions));
              setEvidencePackJson(toPrettyJson(incidentTemplate.evidence_pack));
            }}
          >
            Create from template
          </button>
          <button className="rounded bg-slate-900 px-3 py-1.5 text-sm font-semibold text-white hover:bg-slate-700" type="button" onClick={() => (selectedId ? updateMutation.mutate() : createMutation.mutate())}>
            {selectedId ? "Save incident" : "Create incident"}
          </button>
          {selectedId ? (
            <>
              <button className="rounded bg-amber-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-amber-500" type="button" onClick={() => resolveMutation.mutate()}>
                Resolve incident
              </button>
              <button className="rounded bg-emerald-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-emerald-500" type="button" onClick={() => postmortemMutation.mutate()}>
                Complete postmortem
              </button>
            </>
          ) : null}
          <button className="rounded border border-rose-300 px-3 py-1.5 text-sm font-medium text-rose-700 hover:bg-rose-50" type="button" onClick={() => sloCheckMutation.mutate()}>
            Run SLO checks
          </button>
        </div>
      </SectionShell>

      <SectionShell title="Incident SLO Tasks">
        {taskQuery.isLoading ? <LoadingState label="Loading incident SLO tasks..." /> : null}
        {taskQuery.error ? <ErrorState message="Failed to load incident SLO tasks." /> : null}
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
