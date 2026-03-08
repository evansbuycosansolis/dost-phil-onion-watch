"use client";

import { routes } from "@phil-onion-watch/config";
import { usePathname } from "next/navigation";

const items = [
  { href: routes.dashboardGeospatialOpsRollout, label: "Rollout Waves" },
  { href: routes.dashboardGeospatialOpsKpi, label: "KPI Scorecards" },
  { href: routes.dashboardGeospatialOpsIncidents, label: "Incidents" },
  { href: routes.dashboardGeospatialOpsValidation, label: "Validation" },
  { href: routes.dashboardGeospatialOpsRisks, label: "Risk Register" },
];

export function GeospatialOpsNav() {
  const pathname = usePathname();
  return (
    <div className="mb-4 flex flex-wrap gap-2">
      {items.map((item) => {
        const active = pathname === item.href;
        return (
          <a
            key={item.href}
            href={item.href}
            className={`rounded-md border px-3 py-1.5 text-sm font-medium ${
              active ? "border-slate-900 bg-slate-900 text-white" : "border-slate-300 text-slate-700 hover:bg-slate-50"
            }`}
          >
            {item.label}
          </a>
        );
      })}
    </div>
  );
}
