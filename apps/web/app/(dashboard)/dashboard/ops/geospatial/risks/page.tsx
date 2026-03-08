"use client";

import { apiFetch } from "@phil-onion-watch/api-client";
import type { GeospatialOpsTask, GeospatialRiskItem, GeospatialRiskStatus } from "@phil-onion-watch/types";
import { DataTable, ErrorState, LoadingState, PageHeader, SectionShell } from "@phil-onion-watch/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { GeospatialOpsNav } from "../../../../../../components/geospatial-ops-nav";
import { parseJsonInput, riskTemplate, toPrettyJson } from "../../../../../../lib/geospatial-playbooks";
import { useAuth } from "../../../../../providers";

const statuses: GeospatialRiskStatus[] = ["open", "mitigating", "accepted", "closed"];

function riskClass(rating: number) {
  if (rating >= 16) return "bg-rose-100 text-rose-700";
  if (rating >= 9) return "bg-amber-100 text-amber-700";
  return "bg-emerald-100 text-emerald-700";
}

export default function GeospatialRiskRegisterPage() {
  const { token } = useAuth();
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [riskKey, setRiskKey] = useState(`RISK-${new Date().toISOString().slice(0, 10).replace(/-/g, "")}-001`);
  const [title, setTitle] = useState(riskTemplate.title);
  const [description, setDescription] = useState(riskTemplate.description);
  const [likelihood, setLikelihood] = useState("3");
  const [impact, setImpact] = useState("3");
  const [trigger, setTrigger] = useState(riskTemplate.trigger);
  const [mitigation, setMitigation] = useState(riskTemplate.mitigation);
  const [statusValue, setStatusValue] = useState<GeospatialRiskStatus>("open");
  const [ownerUserId, setOwnerUserId] = useState("");
  const [nextReviewDate, setNextReviewDate] = useState("");
  const [targetCloseDate, setTargetCloseDate] = useState("");
  const [escalationLevel, setEscalationLevel] = useState("0");
  const [boardNotes, setBoardNotes] = useState(riskTemplate.board_notes);
  const [metadataJson, setMetadataJson] = useState(toPrettyJson(riskTemplate.metadata));
  const [closeResolution, setCloseResolution] = useState("");

  const listQuery = useQuery({
    queryKey: ["geospatial-risk-items", token],
    queryFn: () => apiFetch<GeospatialRiskItem[]>("/api/v1/geospatial/risks?limit=200", { token }),
    enabled: !!token,
  });

  useEffect(() => {
    if (!selectedId && listQuery.data && listQuery.data.length > 0) {
      setSelectedId(listQuery.data[0].id);
    }
  }, [selectedId, listQuery.data]);

  const detailQuery = useQuery({
    queryKey: ["geospatial-risk-item", token, selectedId],
    queryFn: () => apiFetch<GeospatialRiskItem>(`/api/v1/geospatial/risks/${selectedId}`, { token }),
    enabled: !!token && selectedId != null,
  });

  const taskQuery = useQuery({
    queryKey: ["geospatial-risk-tasks", token],
    queryFn: () => apiFetch<GeospatialOpsTask[]>("/api/v1/geospatial/ops/tasks?task_type=risk_escalation&limit=60", { token }),
    enabled: !!token,
  });

  useEffect(() => {
    if (!detailQuery.data) return;
    setRiskKey(detailQuery.data.risk_key);
    setTitle(detailQuery.data.title);
    setDescription(detailQuery.data.description);
    setLikelihood(String(detailQuery.data.likelihood));
    setImpact(String(detailQuery.data.impact));
    setTrigger(detailQuery.data.trigger ?? "");
    setMitigation(detailQuery.data.mitigation ?? "");
    setStatusValue(detailQuery.data.status);
    setOwnerUserId(detailQuery.data.owner_user_id ? String(detailQuery.data.owner_user_id) : "");
    setNextReviewDate(detailQuery.data.next_review_date ?? "");
    setTargetCloseDate(detailQuery.data.target_close_date ?? "");
    setEscalationLevel(String(detailQuery.data.escalation_level));
    setBoardNotes(detailQuery.data.board_notes ?? "");
    setMetadataJson(toPrettyJson(detailQuery.data.metadata));
  }, [detailQuery.data]);

  const createMutation = useMutation({
    mutationFn: async () =>
      apiFetch<GeospatialRiskItem>("/api/v1/geospatial/risks", {
        token,
        method: "POST",
        body: {
          risk_key: riskKey,
          title,
          description,
          likelihood: Number(likelihood),
          impact: Number(impact),
          trigger: trigger || null,
          mitigation: mitigation || null,
          owner_user_id: ownerUserId ? Number(ownerUserId) : null,
          status: statusValue,
          next_review_date: nextReviewDate || null,
          target_close_date: targetCloseDate || null,
          escalation_level: Number(escalationLevel),
          board_notes: boardNotes || null,
          metadata: parseJsonInput(metadataJson, {}),
        },
      }),
    onSuccess: async (created) => {
      setErrorMessage(null);
      setSelectedId(created.id);
      await queryClient.invalidateQueries({ queryKey: ["geospatial-risk-items"] });
      await queryClient.invalidateQueries({ queryKey: ["geospatial-risk-item"] });
      await queryClient.invalidateQueries({ queryKey: ["geospatial-risk-tasks"] });
    },
    onError: (error) => {
      setErrorMessage(error instanceof Error ? error.message : "Failed to create risk item");
    },
  });

  const updateMutation = useMutation({
    mutationFn: async () => {
      if (!selectedId) return null;
      return apiFetch<GeospatialRiskItem>(`/api/v1/geospatial/risks/${selectedId}`, {
        token,
        method: "PATCH",
        body: {
          title,
          description,
          likelihood: Number(likelihood),
          impact: Number(impact),
          trigger: trigger || null,
          mitigation: mitigation || null,
          owner_user_id: ownerUserId ? Number(ownerUserId) : null,
          status: statusValue,
          next_review_date: nextReviewDate || null,
          target_close_date: targetCloseDate || null,
          escalation_level: Number(escalationLevel),
          board_notes: boardNotes || null,
          metadata: parseJsonInput(metadataJson, {}),
        },
      });
    },
    onSuccess: async () => {
      setErrorMessage(null);
      await queryClient.invalidateQueries({ queryKey: ["geospatial-risk-items"] });
      await queryClient.invalidateQueries({ queryKey: ["geospatial-risk-item"] });
    },
    onError: (error) => {
      setErrorMessage(error instanceof Error ? error.message : "Failed to update risk item");
    },
  });

  const escalateMutation = useMutation({
    mutationFn: async () => {
      if (!selectedId) return null;
      return apiFetch<GeospatialRiskItem>(`/api/v1/geospatial/risks/${selectedId}/escalate`, {
        token,
        method: "POST",
        body: {
          escalation_level: Number(escalationLevel),
          board_notes: boardNotes || null,
        },
      });
    },
    onSuccess: async () => {
      setErrorMessage(null);
      await queryClient.invalidateQueries({ queryKey: ["geospatial-risk-items"] });
      await queryClient.invalidateQueries({ queryKey: ["geospatial-risk-item"] });
      await queryClient.invalidateQueries({ queryKey: ["geospatial-risk-tasks"] });
    },
    onError: (error) => {
      setErrorMessage(error instanceof Error ? error.message : "Failed to escalate risk item");
    },
  });

  const closeMutation = useMutation({
    mutationFn: async () => {
      if (!selectedId) return null;
      return apiFetch<GeospatialRiskItem>(`/api/v1/geospatial/risks/${selectedId}/close`, {
        token,
        method: "POST",
        body: {
          board_notes: boardNotes || null,
          resolution: closeResolution || null,
        },
      });
    },
    onSuccess: async () => {
      setErrorMessage(null);
      await queryClient.invalidateQueries({ queryKey: ["geospatial-risk-items"] });
      await queryClient.invalidateQueries({ queryKey: ["geospatial-risk-item"] });
    },
    onError: (error) => {
      setErrorMessage(error instanceof Error ? error.message : "Failed to close risk item");
    },
  });

  const runRiskReminderMutation = useMutation({
    mutationFn: async () => apiFetch<GeospatialOpsTask[]>("/api/v1/geospatial/automation/risk-review-reminders", { token, method: "POST" }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["geospatial-risk-tasks"] });
    },
  });

  return (
    <div className="space-y-6">
      <PageHeader title="Geospatial Risk Register" subtitle="Track risk scoring, escalation workflow, next review cadence, and closure evidence." />
      <GeospatialOpsNav />
      {errorMessage ? <ErrorState message={errorMessage} /> : null}
      {listQuery.isLoading ? <LoadingState label="Loading risk register..." /> : null}
      {listQuery.error ? <ErrorState message="Failed to load risk register." /> : null}

      <SectionShell title="Risk Items">
        <DataTable
          columns={[
            { key: "risk_key", label: "Risk Key" },
            {
              key: "title",
              label: "Title",
              render: (row) => (
                <button className="text-left text-sky-700 hover:underline" type="button" onClick={() => setSelectedId((row as GeospatialRiskItem).id)}>
                  {(row as GeospatialRiskItem).title}
                </button>
              ),
            },
            { key: "status", label: "Status" },
            {
              key: "rating",
              label: "Rating",
              render: (row) => (
                <span className={`rounded-full px-2 py-1 text-xs font-semibold ${riskClass((row as GeospatialRiskItem).rating)}`}>
                  {(row as GeospatialRiskItem).rating}
                </span>
              ),
            },
            { key: "escalation_level", label: "Escalation" },
            { key: "next_review_date", label: "Next Review" },
          ]}
          rows={listQuery.data ?? []}
        />
      </SectionShell>

      <SectionShell title={selectedId ? `Risk Detail #${selectedId}` : "Create Risk Item"}>
        {detailQuery.isFetching && selectedId ? <LoadingState label="Loading risk detail..." /> : null}
        <div className="grid gap-4 md:grid-cols-2">
          <label className="text-sm text-slate-600">
            Risk Key
            <input className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5" value={riskKey} onChange={(event) => setRiskKey(event.target.value)} />
          </label>
          <label className="text-sm text-slate-600">
            Status
            <select className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5" value={statusValue} onChange={(event) => setStatusValue(event.target.value as GeospatialRiskStatus)}>
              {statuses.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm text-slate-600 md:col-span-2">
            Title
            <input className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5" value={title} onChange={(event) => setTitle(event.target.value)} />
          </label>
          <label className="text-sm text-slate-600 md:col-span-2">
            Description
            <textarea className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5" rows={3} value={description} onChange={(event) => setDescription(event.target.value)} />
          </label>
          <label className="text-sm text-slate-600">
            Likelihood (1-5)
            <input className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5" type="number" min={1} max={5} value={likelihood} onChange={(event) => setLikelihood(event.target.value)} />
          </label>
          <label className="text-sm text-slate-600">
            Impact (1-5)
            <input className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5" type="number" min={1} max={5} value={impact} onChange={(event) => setImpact(event.target.value)} />
          </label>
          <label className="text-sm text-slate-600 md:col-span-2">
            Trigger
            <input className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5" value={trigger} onChange={(event) => setTrigger(event.target.value)} />
          </label>
          <label className="text-sm text-slate-600 md:col-span-2">
            Mitigation
            <textarea className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5" rows={2} value={mitigation} onChange={(event) => setMitigation(event.target.value)} />
          </label>
          <label className="text-sm text-slate-600">
            Owner User ID
            <input className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5" value={ownerUserId} onChange={(event) => setOwnerUserId(event.target.value)} />
          </label>
          <label className="text-sm text-slate-600">
            Escalation Level
            <input className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5" type="number" min={0} max={5} value={escalationLevel} onChange={(event) => setEscalationLevel(event.target.value)} />
          </label>
          <label className="text-sm text-slate-600">
            Next Review Date
            <input className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5" type="date" value={nextReviewDate} onChange={(event) => setNextReviewDate(event.target.value)} />
          </label>
          <label className="text-sm text-slate-600">
            Target Close Date
            <input className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5" type="date" value={targetCloseDate} onChange={(event) => setTargetCloseDate(event.target.value)} />
          </label>
          <label className="text-sm text-slate-600 md:col-span-2">
            Board Notes
            <textarea className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5" rows={2} value={boardNotes} onChange={(event) => setBoardNotes(event.target.value)} />
          </label>
          <label className="text-sm text-slate-600 md:col-span-2">
            Metadata JSON
            <textarea className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5 font-mono text-xs" rows={6} value={metadataJson} onChange={(event) => setMetadataJson(event.target.value)} />
          </label>
          <label className="text-sm text-slate-600 md:col-span-2">
            Close Resolution
            <textarea className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5" rows={2} value={closeResolution} onChange={(event) => setCloseResolution(event.target.value)} />
          </label>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
            onClick={() => {
              setTitle(riskTemplate.title);
              setDescription(riskTemplate.description);
              setTrigger(riskTemplate.trigger);
              setMitigation(riskTemplate.mitigation);
              setBoardNotes(riskTemplate.board_notes);
              setMetadataJson(toPrettyJson(riskTemplate.metadata));
            }}
          >
            Create from template
          </button>
          <button className="rounded bg-slate-900 px-3 py-1.5 text-sm font-semibold text-white hover:bg-slate-700" type="button" onClick={() => (selectedId ? updateMutation.mutate() : createMutation.mutate())}>
            {selectedId ? "Save risk" : "Create risk"}
          </button>
          {selectedId ? (
            <>
              <button className="rounded bg-amber-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-amber-500" type="button" onClick={() => escalateMutation.mutate()}>
                Escalate
              </button>
              <button className="rounded bg-emerald-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-emerald-500" type="button" onClick={() => closeMutation.mutate()}>
                Close risk
              </button>
            </>
          ) : null}
          <button className="rounded border border-emerald-300 px-3 py-1.5 text-sm font-medium text-emerald-700 hover:bg-emerald-50" type="button" onClick={() => runRiskReminderMutation.mutate()}>
            Run review reminders
          </button>
        </div>
      </SectionShell>

      <SectionShell title="Escalation Tasks">
        {taskQuery.isLoading ? <LoadingState label="Loading escalation tasks..." /> : null}
        {taskQuery.error ? <ErrorState message="Failed to load escalation tasks." /> : null}
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
