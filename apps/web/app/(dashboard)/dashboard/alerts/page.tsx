"use client";

import { apiFetch, useAlerts } from "@phil-onion-watch/api-client";
import { AlertBadge, DataTable, ErrorState, LoadingState, PageHeader, SectionShell, SeverityPill } from "@phil-onion-watch/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "../../../providers";

export default function AlertsDashboardPage() {
  const { token } = useAuth();
  const queryClient = useQueryClient();
  const alerts = useAlerts(token);

  const acknowledge = useMutation({
    mutationFn: (id: number) => apiFetch(`/api/v1/alerts/${id}/acknowledge`, { token, method: "POST", body: { notes: "Acknowledged from dashboard" } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alerts", token] }),
  });

  const resolve = useMutation({
    mutationFn: (id: number) => apiFetch(`/api/v1/alerts/${id}/resolve`, { token, method: "POST", body: { notes: "Resolved from dashboard" } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alerts", token] }),
  });

  if (alerts.isLoading) return <LoadingState label="Loading alerts..." />;
  if (alerts.error) return <ErrorState message="Failed to load alerts" />;

  return (
    <div>
      <PageHeader title="Alerts Center" subtitle="Active risk alerts, severity, status, and recommended actions" />
      <SectionShell title="Active Alerts">
        <DataTable
          columns={[
            { key: "title", label: "Title" },
            { key: "severity", label: "Severity", render: (row) => <SeverityPill severity={String(row.severity)} /> },
            { key: "alert_type", label: "Type" },
            { key: "status", label: "Status", render: (row) => <AlertBadge status={String(row.status)} /> },
            { key: "summary", label: "Summary" },
            { key: "recommended_action", label: "Recommended Action" },
            {
              key: "id",
              label: "Actions",
              render: (row) => (
                <div className="flex gap-2">
                  <button
                    onClick={() => acknowledge.mutate(Number(row.id))}
                    className="rounded border border-amber-300 bg-amber-50 px-2 py-1 text-xs text-amber-700"
                  >
                    Ack
                  </button>
                  <button
                    onClick={() => resolve.mutate(Number(row.id))}
                    className="rounded border border-emerald-300 bg-emerald-50 px-2 py-1 text-xs text-emerald-700"
                  >
                    Resolve
                  </button>
                </div>
              ),
            },
          ]}
          rows={alerts.data ?? []}
        />
      </SectionShell>
    </div>
  );
}
