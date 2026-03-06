"use client";

import { useWarehousesOverview } from "@phil-onion-watch/api-client";
import { DataTable, ErrorState, LoadingState, PageHeader, SectionShell, SeverityPill } from "@phil-onion-watch/ui";

import { useAuth } from "../../../providers";

export default function WarehousesDashboardPage() {
  const { token } = useAuth();
  const warehouses = useWarehousesOverview(token);

  if (warehouses.isLoading) return <LoadingState label="Loading warehouse overview..." />;
  if (warehouses.error) return <ErrorState message="Unable to load warehouse data" />;

  return (
    <div>
      <PageHeader title="Warehouses Dashboard" subtitle="Storage capacity, utilization, and release behavior" />
      <SectionShell title="Warehouse Utilization">
        <DataTable
          columns={[
            { key: "warehouse_name", label: "Warehouse" },
            { key: "municipality_name", label: "Municipality" },
            { key: "location", label: "Location" },
            { key: "capacity_tons", label: "Capacity" },
            { key: "current_stock_tons", label: "Current Stock" },
            { key: "utilization_pct", label: "Utilization %" },
            { key: "last_update", label: "Last Update" },
            { key: "release_trend_tons", label: "Release Trend" },
            {
              key: "anomaly_flag",
              label: "Anomaly",
              render: (row) => (row.anomaly_flag ? <SeverityPill severity="high" /> : <SeverityPill severity="low" />),
            },
          ]}
          rows={warehouses.data ?? []}
        />
      </SectionShell>
    </div>
  );
}
