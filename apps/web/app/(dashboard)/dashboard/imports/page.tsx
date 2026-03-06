"use client";

import { useImports, useImportsOverview } from "@phil-onion-watch/api-client";
import { DataTable, ErrorState, LoadingState, PageHeader, SectionShell } from "@phil-onion-watch/ui";

import { useAuth } from "../../../providers";

export default function ImportsDashboardPage() {
  const { token } = useAuth();
  const imports = useImports(token);
  const overview = useImportsOverview(token);

  if (imports.isLoading || overview.isLoading) return <LoadingState label="Loading import data..." />;
  if (imports.error || overview.error) return <ErrorState message="Failed to load import overview" />;

  const overviewData = overview.data ?? {};

  return (
    <div>
      <PageHeader title="Imports Dashboard" subtitle="Import volumes, timing overlap, and risk assessment" />
      <SectionShell title="Import Records">
        <DataTable
          columns={[
            { key: "import_reference", label: "Reference" },
            { key: "arrival_date", label: "Arrival Date" },
            { key: "volume_tons", label: "Volume (tons)" },
            { key: "origin_country", label: "Origin" },
            { key: "status", label: "Status" },
          ]}
          rows={imports.data ?? []}
        />
      </SectionShell>

      <SectionShell title="Harvest Overlap and Timing Risk">
        <DataTable
          columns={[
            { key: "import_reference", label: "Reference" },
            { key: "arrival_date", label: "Arrival" },
            { key: "volume_tons", label: "Volume" },
            { key: "overlap_with_harvest_window", label: "Overlap" },
            { key: "timing_risk", label: "Timing Risk" },
          ]}
          rows={(overviewData.imports as Record<string, unknown>[]) ?? []}
        />
      </SectionShell>

      <SectionShell title="Risk Assessment">
        <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">
          {((overviewData.risk_assessment as string[]) ?? []).map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </SectionShell>
    </div>
  );
}
