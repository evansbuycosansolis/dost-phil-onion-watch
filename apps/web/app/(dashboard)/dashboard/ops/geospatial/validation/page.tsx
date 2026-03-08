"use client";

import { apiFetch } from "@phil-onion-watch/api-client";
import type {
  GeospatialValidationResult,
  GeospatialValidationResultStatus,
  GeospatialValidationRun,
  GeospatialValidationTestcase,
} from "@phil-onion-watch/types";
import { DataTable, ErrorState, LoadingState, PageHeader, SectionShell } from "@phil-onion-watch/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { GeospatialOpsNav } from "../../../../../../components/geospatial-ops-nav";
import { validationEvidenceTemplate } from "../../../../../../lib/geospatial-playbooks";
import { useAuth } from "../../../../../providers";

type ResultDraft = {
  status: GeospatialValidationResultStatus;
  notes: string;
  evidenceLink: string;
};

const resultStatuses: GeospatialValidationResultStatus[] = ["pass", "fail", "skip"];

export default function GeospatialValidationPage() {
  const { token } = useAuth();
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [scope, setScope] = useState("Provincial geospatial monthly validation");
  const [modelVersion, setModelVersion] = useState("v1.0");
  const [thresholdVersion, setThresholdVersion] = useState("thresholds-v1");
  const [evidenceLinks, setEvidenceLinks] = useState("");
  const [signoff, setSignoff] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, ResultDraft>>({});

  const runsQuery = useQuery({
    queryKey: ["geospatial-validation-runs", token],
    queryFn: () => apiFetch<GeospatialValidationRun[]>("/api/v1/geospatial/validation/runs?limit=150", { token }),
    enabled: !!token,
  });

  useEffect(() => {
    if (!selectedId && runsQuery.data && runsQuery.data.length > 0) {
      setSelectedId(runsQuery.data[0].id);
    }
  }, [selectedId, runsQuery.data]);

  const testcasesQuery = useQuery({
    queryKey: ["geospatial-validation-testcases", token],
    queryFn: () => apiFetch<GeospatialValidationTestcase[]>("/api/v1/geospatial/validation/testcases", { token }),
    enabled: !!token,
  });

  const detailQuery = useQuery({
    queryKey: ["geospatial-validation-run", token, selectedId],
    queryFn: () => apiFetch<GeospatialValidationRun>(`/api/v1/geospatial/validation/runs/${selectedId}`, { token }),
    enabled: !!token && selectedId != null,
  });

  const resultsQuery = useQuery({
    queryKey: ["geospatial-validation-results", token, selectedId],
    queryFn: () => apiFetch<GeospatialValidationResult[]>(`/api/v1/geospatial/validation/runs/${selectedId}/results`, { token }),
    enabled: !!token && selectedId != null,
  });

  useEffect(() => {
    if (!detailQuery.data) return;
    setScope(detailQuery.data.scope);
    setModelVersion(detailQuery.data.model_version ?? "");
    setThresholdVersion(detailQuery.data.threshold_set_version ?? "");
    setEvidenceLinks((detailQuery.data.evidence_links ?? []).join("\n"));
    setSignoff(Boolean(detailQuery.data.signoff_at));
  }, [detailQuery.data]);

  useEffect(() => {
    const byCode = new Map((resultsQuery.data ?? []).map((row) => [row.testcase_code, row]));
    const next: Record<string, ResultDraft> = {};
    for (const testcase of testcasesQuery.data ?? []) {
      const existing = byCode.get(testcase.code);
      const links = (existing?.evidence?.links as string[] | undefined) ?? [];
      next[testcase.code] = {
        status: existing?.status ?? "skip",
        notes: existing?.notes ?? "",
        evidenceLink: links[0] ?? "",
      };
    }
    setDrafts(next);
  }, [resultsQuery.data, testcasesQuery.data, selectedId]);

  const summary = useMemo(() => {
    const values = Object.values(drafts);
    return {
      pass: values.filter((row) => row.status === "pass").length,
      fail: values.filter((row) => row.status === "fail").length,
      skip: values.filter((row) => row.status === "skip").length,
    };
  }, [drafts]);

  const createRunMutation = useMutation({
    mutationFn: async () =>
      apiFetch<GeospatialValidationRun>("/api/v1/geospatial/validation/runs", {
        token,
        method: "POST",
        body: {
          scope,
          model_version: modelVersion || null,
          threshold_set_version: thresholdVersion || null,
          evidence_links: evidenceLinks
            .split("\n")
            .map((value) => value.trim())
            .filter(Boolean),
        },
      }),
    onSuccess: async (created) => {
      setErrorMessage(null);
      setSelectedId(created.id);
      await queryClient.invalidateQueries({ queryKey: ["geospatial-validation-runs"] });
      await queryClient.invalidateQueries({ queryKey: ["geospatial-validation-run"] });
      await queryClient.invalidateQueries({ queryKey: ["geospatial-validation-results"] });
    },
    onError: (error) => {
      setErrorMessage(error instanceof Error ? error.message : "Failed to create validation run");
    },
  });

  const submitResultsMutation = useMutation({
    mutationFn: async () => {
      if (!selectedId) return null;
      const results = Object.entries(drafts).map(([testcaseCode, draft]) => ({
        testcase_code: testcaseCode,
        status: draft.status,
        notes: draft.notes || null,
        evidence: {
          links: draft.evidenceLink ? [draft.evidenceLink] : [],
        },
      }));
      return apiFetch<GeospatialValidationResult[]>(`/api/v1/geospatial/validation/runs/${selectedId}/results`, {
        token,
        method: "POST",
        body: {
          reviewed_by_user_id: null,
          signoff,
          results,
        },
      });
    },
    onSuccess: async () => {
      setErrorMessage(null);
      await queryClient.invalidateQueries({ queryKey: ["geospatial-validation-runs"] });
      await queryClient.invalidateQueries({ queryKey: ["geospatial-validation-run"] });
      await queryClient.invalidateQueries({ queryKey: ["geospatial-validation-results"] });
    },
    onError: (error) => {
      setErrorMessage(error instanceof Error ? error.message : "Failed to submit validation results");
    },
  });

  return (
    <div className="space-y-6">
      <PageHeader title="Geospatial Validation & Assurance" subtitle="Execute VA-T01..VA-T10 test matrix with evidence and signoff traceability." />
      <GeospatialOpsNav />
      {errorMessage ? <ErrorState message={errorMessage} /> : null}
      {runsQuery.isLoading ? <LoadingState label="Loading validation runs..." /> : null}
      {runsQuery.error ? <ErrorState message="Failed to load validation runs." /> : null}

      <SectionShell title="Validation Runs">
        <DataTable
          columns={[
            { key: "run_key", label: "Run Key" },
            {
              key: "scope",
              label: "Scope",
              render: (row) => (
                <button type="button" className="text-left text-sky-700 hover:underline" onClick={() => setSelectedId((row as GeospatialValidationRun).id)}>
                  {(row as GeospatialValidationRun).scope}
                </button>
              ),
            },
            { key: "status", label: "Status" },
            { key: "model_version", label: "Model" },
            { key: "threshold_set_version", label: "Thresholds" },
            { key: "started_at", label: "Started" },
          ]}
          rows={runsQuery.data ?? []}
        />
      </SectionShell>

      <SectionShell title={selectedId ? `Validation Run Detail #${selectedId}` : "Create Validation Run"}>
        {detailQuery.isFetching && selectedId ? <LoadingState label="Loading validation run detail..." /> : null}
        <div className="grid gap-4 md:grid-cols-2">
          <label className="text-sm text-slate-600">
            Scope
            <input className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5" value={scope} onChange={(event) => setScope(event.target.value)} />
          </label>
          <label className="text-sm text-slate-600">
            Model Version
            <input className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5" value={modelVersion} onChange={(event) => setModelVersion(event.target.value)} />
          </label>
          <label className="text-sm text-slate-600">
            Threshold Set Version
            <input className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5" value={thresholdVersion} onChange={(event) => setThresholdVersion(event.target.value)} />
          </label>
          <label className="text-sm text-slate-600 md:col-span-2">
            Evidence Links (one per line)
            <textarea className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5 font-mono text-xs" rows={5} value={evidenceLinks} onChange={(event) => setEvidenceLinks(event.target.value)} />
          </label>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
            onClick={() => {
              setScope("Geospatial assurance report execution");
              setModelVersion("v1.0");
              setThresholdVersion("thresholds-v1");
              setEvidenceLinks((validationEvidenceTemplate.links as string[]).join("\n"));
            }}
          >
            Create from template
          </button>
          <button className="rounded bg-slate-900 px-3 py-1.5 text-sm font-semibold text-white hover:bg-slate-700" type="button" onClick={() => createRunMutation.mutate()}>
            Create validation run
          </button>
        </div>
      </SectionShell>

      <SectionShell title="VA Test Matrix Results">
        {testcasesQuery.isLoading || resultsQuery.isLoading ? <LoadingState label="Loading test matrix..." /> : null}
        {testcasesQuery.error || resultsQuery.error ? <ErrorState message="Failed to load validation matrix." /> : null}
        <div className="mb-3 grid gap-2 md:grid-cols-3">
          <div className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">Pass: {summary.pass}</div>
          <div className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">Fail: {summary.fail}</div>
          <div className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">Skip: {summary.skip}</div>
        </div>
        <div className="space-y-3">
          {(testcasesQuery.data ?? []).map((testcase) => {
            const draft = drafts[testcase.code] ?? { status: "skip", notes: "", evidenceLink: "" };
            return (
              <div key={testcase.code} className="rounded border border-slate-200 p-3">
                <p className="text-sm font-semibold text-slate-800">
                  {testcase.code} - {testcase.name}
                </p>
                <p className="mt-1 text-xs text-slate-500">{testcase.expected}</p>
                <div className="mt-2 grid gap-2 md:grid-cols-3">
                  <label className="text-xs text-slate-600">
                    Status
                    <select
                      className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
                      value={draft.status}
                      onChange={(event) =>
                        setDrafts((prev) => ({
                          ...prev,
                          [testcase.code]: { ...draft, status: event.target.value as GeospatialValidationResultStatus },
                        }))
                      }
                    >
                      {resultStatuses.map((value) => (
                        <option key={value} value={value}>
                          {value}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="text-xs text-slate-600 md:col-span-2">
                    Evidence Link
                    <input
                      className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
                      placeholder="https://..."
                      value={draft.evidenceLink}
                      onChange={(event) =>
                        setDrafts((prev) => ({
                          ...prev,
                          [testcase.code]: { ...draft, evidenceLink: event.target.value },
                        }))
                      }
                    />
                  </label>
                  <label className="text-xs text-slate-600 md:col-span-3">
                    Notes
                    <textarea
                      className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
                      rows={2}
                      value={draft.notes}
                      onChange={(event) =>
                        setDrafts((prev) => ({
                          ...prev,
                          [testcase.code]: { ...draft, notes: event.target.value },
                        }))
                      }
                    />
                  </label>
                </div>
              </div>
            );
          })}
        </div>
        <label className="mt-4 flex items-center gap-2 text-sm text-slate-700">
          <input type="checkbox" checked={signoff} onChange={(event) => setSignoff(event.target.checked)} />
          Mark run as signed off
        </label>
        <div className="mt-3">
          <button className="rounded bg-emerald-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-emerald-500" type="button" onClick={() => submitResultsMutation.mutate()} disabled={!selectedId}>
            Save validation results
          </button>
        </div>
      </SectionShell>
    </div>
  );
}
