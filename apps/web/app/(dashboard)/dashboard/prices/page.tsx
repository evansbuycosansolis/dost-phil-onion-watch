"use client";

import { usePricesOverview } from "@phil-onion-watch/api-client";
import { DataTable, ErrorState, LoadingState, PageHeader, SectionShell } from "@phil-onion-watch/ui";

import { useAuth } from "../../../providers";

export default function PricesDashboardPage() {
  const { token } = useAuth();
  const prices = usePricesOverview(token);

  if (prices.isLoading) return <LoadingState label="Loading price dashboard..." />;
  if (prices.error) return <ErrorState message="Failed to load price overview" />;

  const data = prices.data ?? {};

  return (
    <div>
      <PageHeader title="Prices Dashboard" subtitle="Farmgate, wholesale, retail, and spread pressure" />

      <SectionShell title="Farmgate Trend">
        <DataTable columns={[{ key: "date", label: "Date" }, { key: "price", label: "Price / Kg" }]} rows={(data.farmgate_trend as Record<string, unknown>[]) ?? []} />
      </SectionShell>

      <SectionShell title="Wholesale Trend">
        <DataTable columns={[{ key: "date", label: "Date" }, { key: "price", label: "Price / Kg" }]} rows={(data.wholesale_trend as Record<string, unknown>[]) ?? []} />
      </SectionShell>

      <SectionShell title="Retail Trend">
        <DataTable columns={[{ key: "date", label: "Date" }, { key: "price", label: "Price / Kg" }]} rows={(data.retail_trend as Record<string, unknown>[]) ?? []} />
      </SectionShell>

      <SectionShell title="Price Spread">
        <DataTable columns={[{ key: "date", label: "Date" }, { key: "spread", label: "Spread" }]} rows={(data.price_spread as Record<string, unknown>[]) ?? []} />
      </SectionShell>

      <SectionShell title="Municipality Comparison">
        <DataTable
          columns={[
            { key: "municipality", label: "Municipality" },
            { key: "avg_farmgate", label: "Avg Farmgate" },
            { key: "avg_wholesale", label: "Avg Wholesale" },
            { key: "avg_retail", label: "Avg Retail" },
          ]}
          rows={(data.municipality_comparison as Record<string, unknown>[]) ?? []}
        />
      </SectionShell>

      <SectionShell title="Price Pressure Warnings">
        <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">
          {((data.price_pressure_warnings as string[]) ?? []).map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      </SectionShell>
    </div>
  );
}
