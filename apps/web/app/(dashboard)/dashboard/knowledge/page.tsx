"use client";

import { processDocumentQueue, searchDocuments, useDocumentIngestionJobs, useDocuments } from "@phil-onion-watch/api-client";
import { DataTable, ErrorState, LoadingState, PageHeader, SectionShell } from "@phil-onion-watch/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";

import { useAuth } from "../../../providers";

export default function KnowledgeCenterPage() {
  const { token, user } = useAuth();
  const queryClient = useQueryClient();
  const documents = useDocuments(token);
  const ingestionJobs = useDocumentIngestionJobs(token);
  const [query, setQuery] = useState("import timing and stock release");

  const search = useMutation({
    mutationFn: (q: string) => searchDocuments(token, q, 5),
  });

  const processQueue = useMutation({
    mutationFn: () => processDocumentQueue(token, 6),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["documents", token] }),
        queryClient.invalidateQueries({ queryKey: ["document-ingestion-jobs", token] }),
      ]);
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    search.mutate(query);
  };

  const canManageQueue = (user?.roles ?? []).some((role) =>
    ["super_admin", "provincial_admin", "policy_reviewer", "market_analyst"].includes(role),
  );

  if (documents.isLoading || ingestionJobs.isLoading) return <LoadingState label="Loading document inventory..." />;
  if (documents.error || ingestionJobs.error) return <ErrorState message="Failed to load document list" />;

  return (
    <div>
      <PageHeader title="Knowledge Center" subtitle="Semantic retrieval for policies, advisories, and inspection reports" />

      <SectionShell title="Reference Documents">
        {canManageQueue ? (
          <div className="mb-3">
            <button
              onClick={() => processQueue.mutate()}
              className="rounded border border-slate-300 px-3 py-2 text-sm text-slate-700"
            >
              Process Ingestion Queue
            </button>
          </div>
        ) : null}
        <DataTable
          columns={[
            { key: "title", label: "Title" },
            { key: "source_type", label: "Source Type" },
            { key: "status", label: "Status" },
            { key: "progress_pct", label: "Progress (%)" },
            {
              key: "processed_chunks",
              label: "Chunks",
              render: (row) => `${row.processed_chunks}/${row.total_chunks} (failed: ${row.failed_chunks})`,
            },
            { key: "index_status", label: "Index" },
            { key: "failure_reason", label: "Failure Reason" },
            { key: "uploaded_at", label: "Uploaded" },
          ]}
          rows={documents.data ?? []}
        />
      </SectionShell>

      <SectionShell title="Ingestion Job Queue">
        <DataTable
          columns={[
            { key: "id", label: "Job ID" },
            { key: "document_id", label: "Document ID" },
            { key: "status", label: "Status" },
            { key: "attempt_count", label: "Attempts" },
            {
              key: "processed_chunks",
              label: "Chunk Progress",
              render: (row) => `${row.processed_chunks}/${row.total_chunks} (failed: ${row.failed_chunks})`,
            },
            { key: "last_error", label: "Last Error" },
            { key: "queued_at", label: "Queued At" },
          ]}
          rows={ingestionJobs.data ?? []}
        />
      </SectionShell>

      <SectionShell title="Semantic Search">
        <form onSubmit={submit} className="mb-4 flex gap-2">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            placeholder="Search policy and report knowledge"
          />
          <button type="submit" className="rounded-md bg-brand-700 px-4 py-2 text-sm font-semibold text-white">
            Search
          </button>
        </form>

        {search.isPending ? <LoadingState label="Searching knowledge index..." /> : null}
        {search.error ? <ErrorState message="Semantic search failed" /> : null}

        {search.data ? (
          <DataTable
            columns={[
              { key: "document_title", label: "Document" },
              { key: "score", label: "Score" },
              { key: "snippet", label: "Citation Snippet" },
            ]}
            rows={search.data.results}
          />
        ) : null}
      </SectionShell>
    </div>
  );
}
