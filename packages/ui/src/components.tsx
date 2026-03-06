import type { ReactNode } from "react";

export function Card({ title, children, className = "" }: { title?: string; children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-lg border border-slate-200 bg-white p-4 shadow-sm ${className}`}>
      {title ? <h3 className="mb-3 text-sm font-semibold text-slate-700">{title}</h3> : null}
      {children}
    </section>
  );
}

export function StatCard({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <Card>
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-2 text-2xl font-bold text-slate-900">{value}</p>
      {hint ? <p className="mt-1 text-xs text-slate-500">{hint}</p> : null}
    </Card>
  );
}

export function SeverityPill({ severity }: { severity: string }) {
  const colors: Record<string, string> = {
    low: "bg-emerald-100 text-emerald-700",
    medium: "bg-amber-100 text-amber-700",
    high: "bg-orange-100 text-orange-700",
    critical: "bg-rose-100 text-rose-700",
  };
  return <span className={`rounded-full px-2 py-1 text-xs font-medium ${colors[severity] ?? "bg-slate-100 text-slate-700"}`}>{severity}</span>;
}

export function AlertBadge({ status }: { status: string }) {
  const statusClass: Record<string, string> = {
    open: "bg-rose-100 text-rose-700",
    acknowledged: "bg-amber-100 text-amber-700",
    resolved: "bg-emerald-100 text-emerald-700",
  };
  return <span className={`rounded px-2 py-1 text-xs font-semibold ${statusClass[status] ?? "bg-slate-100 text-slate-700"}`}>{status}</span>;
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <header className="mb-6 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">{title}</h1>
        {subtitle ? <p className="mt-1 text-sm text-slate-600">{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </header>
  );
}

export function SectionShell({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mb-6">
      <h2 className="mb-3 text-lg font-semibold text-slate-800">{title}</h2>
      {children}
    </section>
  );
}

export function ChartShell({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Card title={title}>
      <div className="h-64">{children}</div>
    </Card>
  );
}

export function DashboardGrid({ children }: { children: ReactNode }) {
  return <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">{children}</div>;
}

export function EmptyState({ title, description }: { title: string; description?: string }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 p-8 text-center">
      <h3 className="text-sm font-semibold text-slate-700">{title}</h3>
      {description ? <p className="mt-2 text-sm text-slate-500">{description}</p> : null}
    </div>
  );
}

export function LoadingState({ label = "Loading..." }: { label?: string }) {
  return <p className="animate-pulse text-sm text-slate-500">{label}</p>;
}

export function ErrorState({ message }: { message: string }) {
  return <p className="rounded bg-rose-50 p-3 text-sm text-rose-700">{message}</p>;
}

export function DataTable<T extends object>({
  columns,
  rows,
}: {
  columns: { key: keyof T; label: string; render?: (row: T) => ReactNode }[];
  rows: T[];
}) {
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50">
          <tr>
            {columns.map((col) => (
              <th key={String(col.key)} className="px-3 py-2 text-left font-semibold text-slate-600">
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 bg-white">
          {rows.map((row, idx) => (
            <tr key={idx}>
              {columns.map((col) => (
                <td key={String(col.key)} className="px-3 py-2 text-slate-700">
                  {col.render ? col.render(row) : ((row as Record<string, unknown>)[String(col.key)] as ReactNode)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export type SidebarItem = { href: string; label: string };

export function SidebarNav({ items, activePath }: { items: SidebarItem[]; activePath: string }) {
  return (
    <nav className="space-y-1">
      {items.map((item) => {
        const active = activePath === item.href;
        return (
          <a
            key={item.href}
            href={item.href}
            className={`block rounded-md px-3 py-2 text-sm font-medium ${
              active ? "bg-slate-900 text-white" : "text-slate-700 hover:bg-slate-100"
            }`}
          >
            {item.label}
          </a>
        );
      })}
    </nav>
  );
}
