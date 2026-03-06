"use client";

import { searchDocuments, useDocuments } from "@phil-onion-watch/api-client";
import { DataTable, ErrorState, LoadingState, PageHeader, SectionShell } from "@phil-onion-watch/ui";
import { useMutation } from "@tanstack/react-query";
import { FormEvent, useState } from "react";

import { useAuth } from "../../../providers";

export default function KnowledgeCenterPage() {
  const { token } = useAuth();
  const documents = useDocuments(token);
  const [query, setQuery] = useState("import timing and stock release");

  const search = useMutation({
    mutationFn: (q: string) => searchDocuments(token, q, 5),
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    search.mutate(query);
  };

  if (documents.isLoading) return <LoadingState label="Loading document inventory..." />;
  if (documents.error) return <ErrorState message="Failed to load document list" />;

  return (
    <div>
      <PageHeader title="Knowledge Center" subtitle="Semantic retrieval for policies, advisories, and inspection reports" />

      <SectionShell title="Reference Documents">
        <DataTable
          columns={[
            { key: "title", label: "Title" },
            { key: "source_type", label: "Source Type" },
            { key: "status", label: "Status" },
            { key: "uploaded_at", label: "Uploaded" },
            { key: "summary", label: "Summary" },
          ]}
          rows={documents.data ?? []}
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
