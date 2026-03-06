"use client";

import { apiFetch } from "@phil-onion-watch/api-client";
import { DataTable, ErrorState, LoadingState, PageHeader, SectionShell, StatCard } from "@phil-onion-watch/ui";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { useAuth } from "../../../providers";

type Municipality = { id: number; name: string; code: string };

export default function MunicipalDashboardPage() {
  const { token } = useAuth();
  const [selectedMunicipalityId, setSelectedMunicipalityId] = useState<number | undefined>(undefined);

  const municipalities = useQuery({
    queryKey: ["municipalities", token],
    queryFn: () => apiFetch<Municipality[]>("/api/v1/municipalities", { token }),
    enabled: !!token,
  });

  const overview = useQuery({
    queryKey: ["municipal-overview", token, selectedMunicipalityId],
    queryFn: () => apiFetch<Record<string, unknown>>(`/api/v1/dashboard/municipal/${selectedMunicipalityId}/overview`, { token }),
    enabled: !!token && !!selectedMunicipalityId,
  });

  useEffect(() => {
    if (!selectedMunicipalityId && municipalities.data?.[0]?.id) {
      setSelectedMunicipalityId(municipalities.data[0].id);
    }
  }, [municipalities.data, selectedMunicipalityId]);

  if (municipalities.isLoading) return <LoadingState label="Loading municipalities..." />;
  if (municipalities.error) return <ErrorState message="Failed to load municipalities" />;

  const data = overview.data;

  return (
    <div>
      <PageHeader title="Municipal Dashboard" subtitle="Production, stocks, prices, and compliance by municipality" />

      <div className="mb-4">
        <label className="mb-1 block text-sm font-medium text-slate-700">Municipality</label>
        <select
          value={selectedMunicipalityId ?? ""}
          onChange={(e) => setSelectedMunicipalityId(Number(e.target.value))}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm"
        >
          {municipalities.data?.map((municipality) => (
            <option key={municipality.id} value={municipality.id}>
              {municipality.name}
            </option>
          ))}
        </select>
      </div>

      {overview.isLoading ? <LoadingState label="Loading municipality overview..." /> : null}
      {overview.error ? <ErrorState message="Unable to load municipality overview" /> : null}

      {data ? (
        <>
          <div className="mb-6 grid gap-4 md:grid-cols-4">
            <StatCard label="Production (tons)" value={String(data.production_tons ?? 0)} />
            <StatCard label="Stock (tons)" value={String(data.stock_tons ?? 0)} />
            <StatCard label="Recent Submissions" value={String(data.recent_submissions ?? 0)} />
            <StatCard label="Compliance (%)" value={String(data.reporting_compliance_pct ?? 0)} />
          </div>

          <SectionShell title="Recent Price Reports">
            <DataTable
              columns={[
                { key: "report_date", label: "Date" },
                { key: "price_per_kg", label: "Price / Kg" },
              ]}
              rows={(data.recent_price_reports as Record<string, unknown>[]) ?? []}
            />
          </SectionShell>

          <SectionShell title="Local Alerts">
            <DataTable
              columns={[
                { key: "title", label: "Title" },
                { key: "severity", label: "Severity" },
                { key: "status", label: "Status" },
              ]}
              rows={(data.local_alerts as Record<string, unknown>[]) ?? []}
            />
          </SectionShell>
        </>
      ) : null}
    </div>
  );
}
