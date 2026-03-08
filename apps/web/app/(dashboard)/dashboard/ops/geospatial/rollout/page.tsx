"use client";

import { apiFetch } from "@phil-onion-watch/api-client";
import type { GeospatialRolloutWave } from "@phil-onion-watch/types";
import { DataTable, ErrorState, LoadingState, PageHeader, SectionShell } from "@phil-onion-watch/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { GeospatialOpsNav } from "../../../../../../components/geospatial-ops-nav";
import { rolloutTemplateCriteria, parseJsonInput, toPrettyJson } from "../../../../../../lib/geospatial-playbooks";
import { useAuth } from "../../../../../providers";

function gateClass(status: string) {
  if (status === "passed") return "bg-emerald-100 text-emerald-700";
  if (status === "failed") return "bg-rose-100 text-rose-700";
  if (status === "ready") return "bg-amber-100 text-amber-700";
  return "bg-slate-100 text-slate-700";
}

export default function GeospatialRolloutPage() {
  const { token } = useAuth();
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [name, setName] = useState("Wave 1 Pilot");
  const [waveNumber, setWaveNumber] = useState("1");
  const [regionScope, setRegionScope] = useState("Occidental Mindoro");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [reviewerIds, setReviewerIds] = useState("");
  const [gateNotes, setGateNotes] = useState("");
  const [criteriaJson, setCriteriaJson] = useState(toPrettyJson(rolloutTemplateCriteria));

  const listQuery = useQuery({
    queryKey: ["geospatial-rollout-waves", token],
    queryFn: () => apiFetch<GeospatialRolloutWave[]>("/api/v1/geospatial/waves?limit=200", { token }),
    enabled: !!token,
  });

  useEffect(() => {
    if (!selectedId && listQuery.data && listQuery.data.length > 0) {
      setSelectedId(listQuery.data[0].id);
    }
  }, [selectedId, listQuery.data]);

  const detailQuery = useQuery({
    queryKey: ["geospatial-rollout-wave", token, selectedId],
    queryFn: () => apiFetch<GeospatialRolloutWave>(`/api/v1/geospatial/waves/${selectedId}`, { token }),
    enabled: !!token && selectedId != null,
  });

  useEffect(() => {
    if (!detailQuery.data) return;
    setName(detailQuery.data.name);
    setWaveNumber(String(detailQuery.data.wave_number));
    setRegionScope(detailQuery.data.region_scope);
    setStartDate(detailQuery.data.start_date ?? "");
    setEndDate(detailQuery.data.end_date ?? "");
    setReviewerIds(detailQuery.data.reviewer_ids.join(", "));
    setGateNotes(detailQuery.data.gate_notes ?? "");
    setCriteriaJson(toPrettyJson(detailQuery.data.pass_fail_criteria ?? {}));
  }, [detailQuery.data]);

  const createMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        name,
        wave_number: Number(waveNumber),
        region_scope: regionScope,
        start_date: startDate || null,
        end_date: endDate || null,
        reviewer_ids: reviewerIds
          .split(",")
          .map((value) => Number(value.trim()))
          .filter((value) => Number.isFinite(value) && value > 0),
        gate_notes: gateNotes || null,
        pass_fail_criteria: parseJsonInput(criteriaJson, {}),
      };
      return apiFetch<GeospatialRolloutWave>("/api/v1/geospatial/waves", {
        token,
        method: "POST",
        body: payload,
      });
    },
    onSuccess: async (created) => {
      setErrorMessage(null);
      setSelectedId(created.id);
      await queryClient.invalidateQueries({ queryKey: ["geospatial-rollout-waves"] });
      await queryClient.invalidateQueries({ queryKey: ["geospatial-rollout-wave"] });
    },
    onError: (error) => {
      setErrorMessage(error instanceof Error ? error.message : "Failed to create rollout wave");
    },
  });

  const updateMutation = useMutation({
    mutationFn: async () => {
      if (!selectedId) return null;
      return apiFetch<GeospatialRolloutWave>(`/api/v1/geospatial/waves/${selectedId}`, {
        token,
        method: "PATCH",
        body: {
          name,
          wave_number: Number(waveNumber),
          region_scope: regionScope,
          start_date: startDate || null,
          end_date: endDate || null,
          reviewer_ids: reviewerIds
            .split(",")
            .map((value) => Number(value.trim()))
            .filter((value) => Number.isFinite(value) && value > 0),
          gate_notes: gateNotes || null,
          pass_fail_criteria: parseJsonInput(criteriaJson, {}),
        },
      });
    },
    onSuccess: async () => {
      setErrorMessage(null);
      await queryClient.invalidateQueries({ queryKey: ["geospatial-rollout-waves"] });
      await queryClient.invalidateQueries({ queryKey: ["geospatial-rollout-wave"] });
    },
    onError: (error) => {
      setErrorMessage(error instanceof Error ? error.message : "Failed to update rollout wave");
    },
  });

  const gateMutation = useMutation({
    mutationFn: async () => {
      if (!selectedId) return null;
      return apiFetch<GeospatialRolloutWave>(`/api/v1/geospatial/waves/${selectedId}/gate-evaluate`, {
        token,
        method: "POST",
        body: {
          gate_notes: gateNotes || null,
          pass_fail_criteria: parseJsonInput(criteriaJson, {}),
        },
      });
    },
    onSuccess: async () => {
      setErrorMessage(null);
      await queryClient.invalidateQueries({ queryKey: ["geospatial-rollout-waves"] });
      await queryClient.invalidateQueries({ queryKey: ["geospatial-rollout-wave"] });
    },
    onError: (error) => {
      setErrorMessage(error instanceof Error ? error.message : "Failed to evaluate gate");
    },
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Geospatial Rollout Waves"
        subtitle="Operationalize rollout waves with pass/fail gates, owners, reviewers, and auditable criteria."
      />
      <GeospatialOpsNav />

      {errorMessage ? <ErrorState message={errorMessage} /> : null}
      {listQuery.isLoading ? <LoadingState label="Loading rollout waves..." /> : null}
      {listQuery.error ? <ErrorState message="Failed to load rollout waves." /> : null}

      <SectionShell title="Waves">
        <DataTable
          columns={[
            { key: "id", label: "ID" },
            {
              key: "name",
              label: "Name",
              render: (row) => (
                <button
                  type="button"
                  className="font-medium text-sky-700 hover:underline"
                  onClick={() => setSelectedId((row as GeospatialRolloutWave).id)}
                >
                  {(row as GeospatialRolloutWave).name}
                </button>
              ),
            },
            { key: "wave_number", label: "Wave" },
            { key: "region_scope", label: "Region" },
            {
              key: "gate_status",
              label: "Gate",
              render: (row) => (
                <span className={`rounded-full px-2 py-1 text-xs font-semibold ${gateClass((row as GeospatialRolloutWave).gate_status)}`}>
                  {(row as GeospatialRolloutWave).gate_status}
                </span>
              ),
            },
            { key: "start_date", label: "Start" },
            { key: "end_date", label: "End" },
          ]}
          rows={listQuery.data ?? []}
        />
      </SectionShell>

      <SectionShell title={selectedId ? `Wave Detail #${selectedId}` : "Create Rollout Wave"}>
        {detailQuery.isFetching && selectedId ? <LoadingState label="Loading wave detail..." /> : null}
        <div className="grid gap-4 md:grid-cols-2">
          <label className="text-sm text-slate-600">
            Name
            <input className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5" value={name} onChange={(event) => setName(event.target.value)} />
          </label>
          <label className="text-sm text-slate-600">
            Wave Number
            <input
              className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5"
              type="number"
              min={0}
              value={waveNumber}
              onChange={(event) => setWaveNumber(event.target.value)}
            />
          </label>
          <label className="text-sm text-slate-600">
            Region Scope
            <input
              className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5"
              value={regionScope}
              onChange={(event) => setRegionScope(event.target.value)}
            />
          </label>
          <label className="text-sm text-slate-600">
            Reviewer IDs (comma-separated)
            <input
              className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5"
              value={reviewerIds}
              onChange={(event) => setReviewerIds(event.target.value)}
            />
          </label>
          <label className="text-sm text-slate-600">
            Start Date
            <input className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5" type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
          </label>
          <label className="text-sm text-slate-600">
            End Date
            <input className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5" type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
          </label>
          <label className="text-sm text-slate-600 md:col-span-2">
            Gate Notes
            <textarea className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5" rows={3} value={gateNotes} onChange={(event) => setGateNotes(event.target.value)} />
          </label>
          <label className="text-sm text-slate-600 md:col-span-2">
            Pass/Fail Criteria JSON
            <textarea className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5 font-mono text-xs" rows={10} value={criteriaJson} onChange={(event) => setCriteriaJson(event.target.value)} />
          </label>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
            onClick={() => setCriteriaJson(toPrettyJson(rolloutTemplateCriteria))}
          >
            Create from template
          </button>
          <button
            type="button"
            className="rounded bg-slate-900 px-3 py-1.5 text-sm font-semibold text-white hover:bg-slate-700"
            onClick={() => (selectedId ? updateMutation.mutate() : createMutation.mutate())}
            disabled={createMutation.isPending || updateMutation.isPending}
          >
            {selectedId ? "Save wave" : "Create wave"}
          </button>
          {selectedId ? (
            <button
              type="button"
              className="rounded bg-amber-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-amber-500"
              onClick={() => gateMutation.mutate()}
              disabled={gateMutation.isPending}
            >
              Evaluate gate
            </button>
          ) : null}
        </div>
      </SectionShell>
    </div>
  );
}
