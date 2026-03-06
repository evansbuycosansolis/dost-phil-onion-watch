"use client";

import { apiFetch } from "@phil-onion-watch/api-client";
import { DataTable, ErrorState, LoadingState, PageHeader, SectionShell, StatCard } from "@phil-onion-watch/ui";
import { useQuery } from "@tanstack/react-query";

import { useAuth } from "../../../providers";

export default function AdminConsolePage() {
  const { token } = useAuth();
  const overview = useQuery({
    queryKey: ["admin-overview", token],
    queryFn: () => apiFetch<Record<string, unknown>>("/api/v1/admin/overview", { token }),
    enabled: !!token,
  });

  const users = useQuery({
    queryKey: ["users", token],
    queryFn: () => apiFetch<Record<string, unknown>[]>("/api/v1/users", { token }),
    enabled: !!token,
  });

  if (overview.isLoading || users.isLoading) return <LoadingState label="Loading admin console..." />;
  if (overview.error || users.error) return <ErrorState message="Failed to load admin console" />;

  const data = overview.data ?? {};

  return (
    <div>
      <PageHeader title="Admin Console" subtitle="Users, roles, ingestion status, jobs, and system controls" />

      <div className="mb-6 grid gap-4 md:grid-cols-3">
        <StatCard label="Users" value={String(data.users_count ?? 0)} />
        <StatCard label="Document Index Status" value={String((data.document_ingestion_status as Record<string, unknown>)?.latest_status ?? "unknown")} />
        <StatCard label="Pipeline Runs" value={String((data.pipeline_runs as Record<string, unknown>[])?.length ?? 0)} />
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

      <SectionShell title="Job Status">
        <DataTable
          columns={[
            { key: "job_name", label: "Job" },
            { key: "status", label: "Status" },
            { key: "started_at", label: "Started" },
            { key: "finished_at", label: "Finished" },
          ]}
          rows={(data.job_status as Record<string, unknown>[]) ?? []}
        />
      </SectionShell>

      <SectionShell title="Pipeline Runs">
        <DataTable
          columns={[{ key: "id", label: "Run" }, { key: "status", label: "Status" }, { key: "details", label: "Details" }]}
          rows={(data.pipeline_runs as Record<string, unknown>[]) ?? []}
        />
      </SectionShell>
    </div>
  );
}
