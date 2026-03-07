"use client";

import { useAlerts, useAnomalies, useForecastLatest, useProvincialOverview } from "@phil-onion-watch/api-client";
import { AlertBadge, DashboardGrid, DataTable, ErrorState, LoadingState, PageHeader, SectionShell, SeverityPill, StatCard } from "@phil-onion-watch/ui";

import { useAuth } from "../../../providers";

export default function ProvincialDashboardPage() {
  const { token } = useAuth();
  const overview = useProvincialOverview(token);
  const forecast = useForecastLatest(token);
  const alerts = useAlerts(token);
  const anomalies = useAnomalies(token);

  if (overview.isLoading) return <LoadingState label="Loading provincial overview..." />;
  if (overview.error) return <ErrorState message="Failed to load provincial overview" />;

  const data = overview.data;

  return (
    <div>
      <PageHeader title="Provincial Command Dashboard" subtitle="Occidental Mindoro onion supply intelligence and decision support" />
      <DashboardGrid>
        <StatCard label="Total Harvest (tons)" value={data?.total_harvest_volume_tons ?? 0} />
        <StatCard label="Warehouse Stock (tons)" value={data?.current_warehouse_stock_tons ?? 0} />
        <StatCard label="Cold Utilization (%)" value={data?.cold_storage_utilization_pct ?? 0} />
        <StatCard label="Stock Releases (tons)" value={data?.stock_release_volume_tons ?? 0} />
      </DashboardGrid>

      <SectionShell title="Municipality Summary">
        <DataTable
          columns={[
            { key: "municipality_name", label: "Municipality" },
            { key: "production_tons", label: "Production (tons)" },
            { key: "stock_tons", label: "Stock (tons)" },
            { key: "avg_farmgate_price", label: "Avg Farmgate" },
          ]}
          rows={data?.municipality_cards ?? []}
        />
      </SectionShell>

      <SectionShell title="Forecast Summary">
        {forecast.isLoading ? <LoadingState /> : null}
        {forecast.error ? <ErrorState message="Unable to load forecast data" /> : null}
        {forecast.data ? (
          <DataTable
            columns={[
              { key: "municipality_id", label: "Municipality ID" },
              { key: "next_month_supply_tons", label: "Next Month Supply" },
              { key: "next_quarter_trend", label: "Quarter Trend" },
              { key: "shortage_probability", label: "Shortage Prob." },
              { key: "oversupply_probability", label: "Oversupply Prob." },
            ]}
            rows={forecast.data.outputs ?? []}
          />
        ) : null}
      </SectionShell>

      <SectionShell title="Active Alerts">
        {alerts.data ? (
          <DataTable
            columns={[
              { key: "title", label: "Title" },
              { key: "severity", label: "Severity", render: (row) => <SeverityPill severity={String(row.severity)} /> },
              { key: "status", label: "Status", render: (row) => <AlertBadge status={String(row.status)} /> },
              { key: "summary", label: "Summary" },
            ]}
            rows={alerts.data.slice(0, 8)}
          />
        ) : null}
      </SectionShell>

      <SectionShell title="Top Anomaly Hotspots">
        {anomalies.data ? (
          <DataTable
            columns={[
              { key: "anomaly_type", label: "Type" },
              { key: "severity", label: "Severity", render: (row) => <SeverityPill severity={String(row.severity)} /> },
              { key: "scope_type", label: "Scope" },
              { key: "metrics", label: "Score", render: (row) => String((row.metrics as Record<string, unknown>)?.final_score ?? "n/a") },
              { key: "metrics", label: "Why Fired", render: (row) => String((row.metrics as Record<string, unknown>)?.explanation ?? "n/a") },
              { key: "summary", label: "Summary" },
            ]}
            rows={anomalies.data.slice(0, 8)}
          />
        ) : null}
      </SectionShell>
    </div>
  );
}
