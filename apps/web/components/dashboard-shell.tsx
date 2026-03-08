"use client";

import { routes } from "@phil-onion-watch/config";
import { SidebarNav } from "@phil-onion-watch/ui";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useMemo } from "react";

import { useAuth } from "../app/providers";

const adminRoles = new Set(["super_admin", "provincial_admin", "auditor"]);

export function DashboardShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { token, user, logout } = useAuth();

  useEffect(() => {
    if (!token) {
      router.replace(routes.login);
    }
  }, [token, router]);

  const items = useMemo(() => {
    const base: Array<{ href: string; label: string }> = [
      { href: routes.dashboardProvincial, label: "Provincial" },
      { href: routes.dashboardMunicipal, label: "Municipal" },
      { href: routes.dashboardWarehouses, label: "Warehouses" },
      { href: routes.dashboardPrices, label: "Prices" },
      { href: routes.dashboardImports, label: "Imports" },
      { href: routes.dashboardAlerts, label: "Alerts" },
      { href: routes.dashboardKnowledge, label: "Knowledge" },
      { href: routes.dashboardReports, label: "Reports" },
    ];
    const hasAdminRole = (user?.roles ?? []).some((role) => adminRoles.has(role));
    if (hasAdminRole) {
      base.push({ href: routes.dashboardGeospatialAOIs, label: "Geospatial" });
      base.push({ href: routes.dashboardGeospatialOpsRollout, label: "Geo Ops" });
      base.push({ href: routes.dashboardGeospatialExecutive, label: "Geo Executive" });
      base.push({ href: routes.dashboardGeospatialIntelligence, label: "Geo Intel" });
      base.push({ href: routes.dashboardAdmin, label: "Admin" });
    }
    return base;
  }, [user]);

  return (
    <div className="mx-auto flex min-h-screen max-w-[1400px] gap-4 p-4">
      <aside className="w-60 shrink-0 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <p className="text-xs uppercase tracking-wide text-slate-500">DOST Phil Onion Watch</p>
        <p className="mt-1 text-sm font-semibold text-slate-800">{user?.fullName ?? "Session"}</p>
        <p className="text-xs text-slate-500">{(user?.roles ?? []).join(", ") || "No role"}</p>
        <div className="mt-4">
          <SidebarNav items={items} activePath={pathname} />
        </div>
        <button
          type="button"
          onClick={() => {
            logout();
            router.push(routes.login);
          }}
          className="mt-6 w-full rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          Sign out
        </button>
      </aside>
      <section className="min-w-0 flex-1 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">{children}</section>
    </div>
  );
}
