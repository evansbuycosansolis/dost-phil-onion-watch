"use client";

import { apiFetch } from "@phil-onion-watch/api-client";
import { Card, EmptyState, ErrorState, LoadingState, SectionShell, SeverityPill } from "@phil-onion-watch/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

type AoiRow = {
  id: number;
  code: string;
  name: string;
  is_active: boolean;
};

type AoiMetadata = {
  owner_user_id: number | null;
  tags: string[];
  labels: string[];
  watchlist_flag: boolean;
  public_share_token: string | null;
};

type AoiVersion = {
  id: number;
  version: number;
  change_type: string;
  changed_at: string;
};

type AoiAnalytics = {
  risk_score: number;
  cloud_coverage_trend: Array<{ value: number | null }>;
  vegetation_vigor_trend: Array<{ value: number | null }>;
  crop_activity_trend: Array<{ value: number | null }>;
  confidence_trend: Array<{ value: number | null }>;
};

type ActivityPayload = {
  events: Array<{ timestamp: string; type: string; summary: string }>;
};

type NotePayload = {
  id: number;
  note_type: string;
  body: string;
  created_at: string;
};

function series(values: Array<number | null | undefined>) {
  const points = values.filter((item): item is number => typeof item === "number").map((item) => Math.max(0, Math.min(1, item))).slice(-20);
  if (points.length === 0) return "n/a";
  const blocks = ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"];
  return points.map((item) => blocks[Math.min(7, Math.floor(item * 7))]).join("");
}

function riskSeverity(value: number) {
  if (value >= 0.8) return "critical";
  if (value >= 0.6) return "high";
  if (value >= 0.35) return "medium";
  return "low";
}

function downloadBlob(name: string, text: string, mime: string) {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function GeospatialAoiAdvancedPanel({
  token,
  selectedAoi,
  selectedRunId,
  aoiRows,
  canManageAOIs,
}: {
  token?: string | null;
  selectedAoi: AoiRow | null;
  selectedRunId: number | null;
  aoiRows: AoiRow[];
  canManageAOIs: boolean;
}) {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState("");
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [metadataInput, setMetadataInput] = useState({ owner: "", tags: "", labels: "" });
  const [noteBody, setNoteBody] = useState("");
  const [diffInput, setDiffInput] = useState({ from: "", to: "" });
  const [importPayload, setImportPayload] = useState("{\"type\":\"FeatureCollection\",\"features\":[]}");

  const metadata = useQuery({
    queryKey: ["geospatial-advanced-aoi-metadata", token, selectedAoi?.id],
    queryFn: () => apiFetch<AoiMetadata>(`/api/v1/geospatial/aois/${selectedAoi?.id}/metadata`, { token }),
    enabled: !!token && !!selectedAoi,
  });
  const versions = useQuery({
    queryKey: ["geospatial-advanced-aoi-versions", token, selectedAoi?.id],
    queryFn: () => apiFetch<AoiVersion[]>(`/api/v1/geospatial/aois/${selectedAoi?.id}/versions?limit=40`, { token }),
    enabled: !!token && !!selectedAoi,
  });
  const analytics = useQuery({
    queryKey: ["geospatial-advanced-aoi-analytics", token, selectedAoi?.id],
    queryFn: () => apiFetch<AoiAnalytics>(`/api/v1/geospatial/aois/${selectedAoi?.id}/analytics?months=12`, { token }),
    enabled: !!token && !!selectedAoi,
  });
  const activity = useQuery({
    queryKey: ["geospatial-advanced-aoi-activity", token, selectedAoi?.id],
    queryFn: () => apiFetch<ActivityPayload>(`/api/v1/geospatial/aois/${selectedAoi?.id}/activity?limit=60`, { token }),
    enabled: !!token && !!selectedAoi,
  });
  const notes = useQuery({
    queryKey: ["geospatial-advanced-aoi-notes", token, selectedAoi?.id],
    queryFn: () => apiFetch<NotePayload[]>(`/api/v1/geospatial/aois/${selectedAoi?.id}/notes`, { token }),
    enabled: !!token && !!selectedAoi,
  });
  const diff = useQuery({
    queryKey: ["geospatial-advanced-aoi-diff", token, selectedAoi?.id, diffInput.from, diffInput.to],
    queryFn: () =>
      apiFetch<{ changes: Array<{ path: string; change_type: string }> }>(
        `/api/v1/geospatial/aois/${selectedAoi?.id}/versions/diff?from_version=${diffInput.from}&to_version=${diffInput.to}`,
        { token },
      ),
    enabled: !!token && !!selectedAoi && !!diffInput.from && !!diffInput.to,
  });

  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds]);

  const invalidateAll = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["geospatial-aois"] }),
      queryClient.invalidateQueries({ queryKey: ["geospatial-advanced-aoi-metadata", token, selectedAoi?.id] }),
      queryClient.invalidateQueries({ queryKey: ["geospatial-advanced-aoi-activity", token, selectedAoi?.id] }),
      queryClient.invalidateQueries({ queryKey: ["geospatial-advanced-aoi-notes", token, selectedAoi?.id] }),
      queryClient.invalidateQueries({ queryKey: ["geospatial-advanced-aoi-versions", token, selectedAoi?.id] }),
    ]);
  };

  const bulkStatus = useMutation({
    mutationFn: (isActive: boolean) =>
      apiFetch("/api/v1/geospatial/aois/bulk/status", {
        token,
        method: "POST",
        body: { aoi_ids: selectedIds, is_active: isActive, change_reason: "Dashboard bulk status update" },
      }),
    onSuccess: async () => {
      setMessage("Bulk status updated");
      await invalidateAll();
    },
    onError: () => setMessage("Bulk status update failed"),
  });

  if (!selectedAoi) {
    return (
      <SectionShell title="AOI Advanced Operations">
        <EmptyState title="Select an AOI" description="Choose an AOI from the table to manage advanced workflow features." />
      </SectionShell>
    );
  }

  return (
    <SectionShell title="AOI Advanced Operations">
      <div className="space-y-4" data-testid="aoi-advanced-panel">
        <Card>
          <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
            <div>
              <a href="/dashboard/geospatial" className="text-sky-700 hover:underline">Geo home</a> / <a href="/dashboard/geospatial/aois" className="text-sky-700 hover:underline">AOIs</a> / <span className="font-semibold">{selectedAoi.code}</span>{selectedRunId ? <span> / Run #{selectedRunId}</span> : null}
            </div>
            <div className="flex items-center gap-2">
              <button type="button" onClick={async () => {
                const link = `${window.location.origin}/dashboard/geospatial/aois?aoiId=${selectedAoi.id}`;
                await navigator.clipboard.writeText(link);
                setMessage("AOI deep-link copied");
              }} className="rounded border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50">Copy AOI deep-link</button>
              <button type="button" onClick={() => window.print()} className="rounded border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50">Printable summary</button>
            </div>
          </div>
          {message ? <p className="mt-2 rounded bg-emerald-50 px-2 py-1 text-xs text-emerald-700">{message}</p> : null}
        </Card>

        <div className="grid gap-4 xl:grid-cols-2">
          <Card title="Risk, Seasonality, and Trend Diagnostics">
            {analytics.isLoading ? <LoadingState label="Loading AOI analytics..." /> : null}
            {analytics.error ? <ErrorState message="Failed to load AOI analytics" /> : null}
            {analytics.data ? (
              <div className="space-y-2 text-sm">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-slate-900">Risk {analytics.data.risk_score.toFixed(3)}</span>
                  <SeverityPill severity={riskSeverity(analytics.data.risk_score)} />
                </div>
                <div className="rounded border border-slate-200 bg-slate-50 px-2 py-1 text-xs">Cloud trend: <span className="font-mono">{series(analytics.data.cloud_coverage_trend.map((item) => item.value))}</span></div>
                <div className="rounded border border-slate-200 bg-slate-50 px-2 py-1 text-xs">Vigor trend: <span className="font-mono">{series(analytics.data.vegetation_vigor_trend.map((item) => item.value))}</span></div>
                <div className="rounded border border-slate-200 bg-slate-50 px-2 py-1 text-xs">Crop trend: <span className="font-mono">{series(analytics.data.crop_activity_trend.map((item) => item.value))}</span></div>
                <div className="rounded border border-slate-200 bg-slate-50 px-2 py-1 text-xs">Confidence trend: <span className="font-mono">{series(analytics.data.confidence_trend.map((item) => item.value))}</span></div>
              </div>
            ) : null}
          </Card>

          <Card title="Metadata, Favorites, Watchlist, and Public Share">
            {metadata.isLoading ? <LoadingState label="Loading metadata..." /> : null}
            {metadata.error ? <ErrorState message="Failed to load metadata" /> : null}
            {metadata.data ? (
              <div className="space-y-2 text-xs">
                <div className="grid gap-2 sm:grid-cols-3">
                  <input value={metadataInput.owner} onChange={(event) => setMetadataInput((prev) => ({ ...prev, owner: event.target.value }))} placeholder={metadata.data.owner_user_id == null ? "owner user id" : String(metadata.data.owner_user_id)} className="rounded border border-slate-300 px-2 py-1 text-sm" />
                  <input value={metadataInput.tags} onChange={(event) => setMetadataInput((prev) => ({ ...prev, tags: event.target.value }))} placeholder={(metadata.data.tags ?? []).join(", ")} className="rounded border border-slate-300 px-2 py-1 text-sm" />
                  <input value={metadataInput.labels} onChange={(event) => setMetadataInput((prev) => ({ ...prev, labels: event.target.value }))} placeholder={(metadata.data.labels ?? []).join(", ")} className="rounded border border-slate-300 px-2 py-1 text-sm" />
                </div>
                <div className="flex flex-wrap gap-2">
                  <button type="button" disabled={!canManageAOIs} onClick={async () => {
                    await apiFetch(`/api/v1/geospatial/aois/${selectedAoi.id}/metadata`, {
                      token,
                      method: "POST",
                      body: {
                        owner_user_id: metadataInput.owner.trim() ? Number(metadataInput.owner) : metadata.data.owner_user_id,
                        tags: metadataInput.tags.trim() ? metadataInput.tags.split(",").map((item) => item.trim()).filter(Boolean) : metadata.data.tags,
                        labels: metadataInput.labels.trim() ? metadataInput.labels.split(",").map((item) => item.trim()).filter(Boolean) : metadata.data.labels,
                        watchlist_flag: metadata.data.watchlist_flag,
                      },
                    });
                    setMessage("AOI metadata updated");
                    await invalidateAll();
                  }} className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50">Save metadata</button>
                  <button type="button" onClick={async () => {
                    await apiFetch(`/api/v1/geospatial/aois/${selectedAoi.id}/favorite`, { token, method: "POST", body: { is_pinned: true } });
                    setMessage("AOI pinned as favorite");
                  }} className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50">Pin favorite</button>
                  <button type="button" onClick={async () => {
                    await apiFetch(`/api/v1/geospatial/aois/${selectedAoi.id}/metadata`, {
                      token,
                      method: "POST",
                      body: {
                        owner_user_id: metadata.data.owner_user_id,
                        tags: metadata.data.tags,
                        labels: metadata.data.labels,
                        watchlist_flag: !metadata.data.watchlist_flag,
                      },
                    });
                    setMessage("Watchlist flag toggled");
                    await invalidateAll();
                  }} className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50">Toggle watchlist</button>
                  <button type="button" onClick={async () => {
                    if (!metadata.data.public_share_token) return;
                    const payload = await apiFetch(`/api/v1/geospatial/aois/${selectedAoi.id}/summary/public?token=${metadata.data.public_share_token}`, { token });
                    downloadBlob(`aoi-${selectedAoi.code}-public-summary.json`, JSON.stringify(payload, null, 2), "application/json");
                    setMessage("Public-safe summary exported");
                  }} className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50">Export public-safe summary</button>
                </div>
              </div>
            ) : null}
          </Card>
        </div>

        <div className="grid gap-4 xl:grid-cols-3">
          <Card title="Version Diff and Restore">
            <div className="grid gap-2 sm:grid-cols-2">
              <input value={diffInput.from} onChange={(event) => setDiffInput((prev) => ({ ...prev, from: event.target.value }))} placeholder="From version" className="rounded border border-slate-300 px-2 py-1 text-sm" />
              <input value={diffInput.to} onChange={(event) => setDiffInput((prev) => ({ ...prev, to: event.target.value }))} placeholder="To version" className="rounded border border-slate-300 px-2 py-1 text-sm" />
            </div>
            {diff.data ? <div className="mt-2 max-h-24 overflow-y-auto text-xs text-slate-700">{diff.data.changes.slice(0, 10).map((item, index) => <div key={`${item.path}-${index}`}>{item.change_type}: {item.path}</div>)}</div> : null}
            <div className="mt-2 space-y-1 text-xs">
              {(versions.data ?? []).slice(0, 8).map((row) => (
                <div key={row.id} className="flex items-center justify-between rounded border border-slate-200 bg-slate-50 px-2 py-1">
                  <span>v{row.version} · {row.change_type}</span>
                  <button type="button" disabled={!canManageAOIs} onClick={async () => {
                    await apiFetch(`/api/v1/geospatial/aois/${selectedAoi.id}/versions/${row.version}/restore`, { token, method: "POST" });
                    setMessage(`Restored AOI to version ${row.version}`);
                    await invalidateAll();
                  }} className="rounded border border-slate-300 px-2 py-0.5 font-medium text-slate-700 hover:bg-white disabled:opacity-50">Restore</button>
                </div>
              ))}
            </div>
          </Card>

          <Card title="Activity Timeline">
            {activity.isLoading ? <LoadingState label="Loading activity..." /> : null}
            {activity.error ? <ErrorState message="Failed to load AOI activity" /> : null}
            <div className="max-h-52 space-y-1 overflow-y-auto text-xs text-slate-700">
              {(activity.data?.events ?? []).slice(0, 30).map((event, index) => (
                <div key={`${event.timestamp}-${index}`} className="rounded border border-slate-200 bg-slate-50 px-2 py-1">
                  <div className="font-medium">{event.type}</div>
                  <div>{event.summary}</div>
                  <div className="text-slate-500">{event.timestamp}</div>
                </div>
              ))}
            </div>
          </Card>

          <Card title="Notes, Comments, Mentions">
            <textarea value={noteBody} onChange={(event) => setNoteBody(event.target.value)} placeholder="Add note/comment text..." className="h-20 w-full rounded border border-slate-300 px-2 py-1 text-sm" />
            <div className="mt-2 flex flex-wrap gap-2">
              <button type="button" disabled={!noteBody.trim()} onClick={async () => {
                await apiFetch(`/api/v1/geospatial/aois/${selectedAoi.id}/notes`, { token, method: "POST", body: { note_type: "note", body: noteBody, mentions: ["@policy_reviewer"] } });
                setNoteBody("");
                setMessage("AOI note saved");
                await invalidateAll();
              }} className="rounded border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50">Add note</button>
              <button type="button" disabled={!noteBody.trim()} onClick={async () => {
                await apiFetch(`/api/v1/geospatial/aois/${selectedAoi.id}/notes`, { token, method: "POST", body: { note_type: "comment", body: noteBody, mentions: ["@market_analyst"] } });
                setNoteBody("");
                setMessage("AOI comment saved");
                await invalidateAll();
              }} className="rounded border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50">Add comment</button>
            </div>
            <div className="mt-2 max-h-32 space-y-1 overflow-y-auto text-xs text-slate-700">
              {(notes.data ?? []).slice(0, 10).map((row) => (
                <div key={row.id} className="rounded border border-slate-200 bg-slate-50 px-2 py-1">
                  <div className="font-medium">{row.note_type}</div>
                  <div>{row.body}</div>
                </div>
              ))}
            </div>
          </Card>
        </div>

        <Card title="Bulk Import/Export and Activation Controls">
          <div className="grid gap-2 md:grid-cols-3 xl:grid-cols-6">
            {aoiRows.slice(0, 24).map((row) => (
              <label key={row.id} className="flex items-center gap-2 rounded border border-slate-200 bg-slate-50 px-2 py-1 text-xs">
                <input type="checkbox" checked={selectedSet.has(row.id)} onChange={(event) => setSelectedIds((prev) => {
                  const next = new Set(prev);
                  if (event.target.checked) next.add(row.id);
                  else next.delete(row.id);
                  return Array.from(next);
                })} />
                <span className="truncate">{row.code}</span>
              </label>
            ))}
          </div>
          <div className="mt-2 flex flex-wrap gap-2 text-xs">
            <button type="button" disabled={!selectedIds.length} onClick={() => bulkStatus.mutate(true)} className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50">Bulk activate</button>
            <button type="button" disabled={!selectedIds.length} onClick={() => bulkStatus.mutate(false)} className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50">Bulk deactivate</button>
            <button type="button" onClick={async () => {
              const geojson = await apiFetch(`/api/v1/geospatial/aois/export/geojson`, { token });
              downloadBlob("geospatial-aois.geojson", JSON.stringify(geojson, null, 2), "application/geo+json");
              setMessage("GeoJSON export complete");
            }} className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50">Bulk export GeoJSON</button>
            <button type="button" onClick={async () => {
              const csv = await fetch("/api/v1/geospatial/aois/export/csv", { headers: token ? { Authorization: `Bearer ${token}` } : {} }).then((res) => res.text());
              downloadBlob("geospatial-aois.csv", csv, "text/csv;charset=utf-8");
              setMessage("CSV metadata export complete");
            }} className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50">Export CSV metadata</button>
          </div>
          <textarea value={importPayload} onChange={(event) => setImportPayload(event.target.value)} className="mt-2 h-20 w-full rounded border border-slate-300 px-2 py-1 font-mono text-xs" />
          <div className="mt-2 flex flex-wrap gap-2 text-xs">
            <button type="button" disabled={!canManageAOIs} onClick={async () => {
              try {
                const parsed = JSON.parse(importPayload);
                await apiFetch("/api/v1/geospatial/aois/bulk/import-geojson", { token, method: "POST", body: { feature_collection: parsed } });
                setMessage("Bulk GeoJSON import completed");
                await invalidateAll();
              } catch {
                setMessage("Bulk GeoJSON payload invalid");
              }
            }} className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50">Bulk import GeoJSON</button>
          </div>
        </Card>
      </div>
    </SectionShell>
  );
}
