"use client";

import { apiFetch } from "@phil-onion-watch/api-client";
import { DataTable, EmptyState, ErrorState, LoadingState, PageHeader, SectionShell, StatCard } from "@phil-onion-watch/ui";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { useAuth } from "../../../../../providers";
import { GeospatialRunAdvancedPanel } from "../../../../../../components/geospatial-run-advanced-panel";

type PipelineRunItem = {
  id: number;
  run_type: string;
  backend: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  triggered_by: number | null;
  correlation_id: string | null;
  algorithm_version: string;
  aoi_id: number | null;
  aoi_code: string | null;
  aoi_name: string | null;
  sources: string[];
  parameters: Record<string, unknown>;
  results: Record<string, unknown>;
  notes: string | null;
};

type RunProvenanceSummary = {
  scene_count: number;
  feature_count: number;
  scene_sources: string[];
  feature_sources: string[];
};

type SceneProvenanceItem = {
  id: number | null;
  source: string;
  scene_id: string;
  aoi_id: number | null;
  aoi_code: string | null;
  aoi_name: string | null;
  acquired_at: string | null;
  cloud_score: number | null;
  spatial_resolution_m: number | null;
  processing_status: string;
  provenance_status: string | null;
};

type FeatureProvenanceItem = {
  id: number;
  aoi_id: number;
  aoi_code: string | null;
  aoi_name: string | null;
  source: string;
  observation_date: string | null;
  reporting_month: string | null;
  cloud_score: number | null;
  crop_activity_score: number | null;
  vegetation_vigor_score: number | null;
  observation_confidence_score: number | null;
  scene_id: string | null;
  acquired_at: string | null;
};

type PipelineRunDetail = PipelineRunItem & {
  provenance_summary: RunProvenanceSummary;
  related_scenes: SceneProvenanceItem[];
  related_features: FeatureProvenanceItem[];
};

type PaginatedProvenanceResponse<T> = {
  run_id: number;
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  rows: T[];
};

type SceneProvenanceChainResponse = {
  run_id: number;
  source: string;
  scene_id: string;
  scene_found: boolean;
  completed_steps: number;
  total_steps: number;
  latest_step: string | null;
  timeline: Array<{
    step: string;
    timestamp: string | null;
    status: string;
    details: Record<string, unknown>;
  }>;
};

type SortDirection = "asc" | "desc";

const PAGE_SIZE_OPTIONS = [10, 20, 50] as const;
const SCENE_SORT_FIELDS = new Set(["acquired_at", "source", "aoi_code", "cloud_score", "spatial_resolution_m", "scene_id"]);
const FEATURE_SORT_FIELDS = new Set([
  "observation_date",
  "source",
  "aoi_code",
  "scene_id",
  "observation_confidence_score",
  "crop_activity_score",
  "vegetation_vigor_score",
  "cloud_score",
]);

type DrilldownUrlState = {
  scenePage: number;
  scenePageSize: number;
  sceneSearch: string;
  sceneSource: string;
  sceneAoiCode: string;
  sceneProcessingStatus: string;
  sceneSortBy: string;
  sceneSortDir: SortDirection;
  featurePage: number;
  featurePageSize: number;
  featureSearch: string;
  featureSource: string;
  featureAoiCode: string;
  featureSortBy: string;
  featureSortDir: SortDirection;
};

const DEFAULT_DRILLDOWN_URL_STATE: DrilldownUrlState = {
  scenePage: 1,
  scenePageSize: 20,
  sceneSearch: "",
  sceneSource: "",
  sceneAoiCode: "",
  sceneProcessingStatus: "",
  sceneSortBy: "acquired_at",
  sceneSortDir: "desc",
  featurePage: 1,
  featurePageSize: 20,
  featureSearch: "",
  featureSource: "",
  featureAoiCode: "",
  featureSortBy: "observation_date",
  featureSortDir: "desc",
};

function parsePositiveInteger(value: string | null, fallback: number, allowedValues?: readonly number[]) {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 1) {
    return fallback;
  }
  if (allowedValues && !allowedValues.includes(parsed)) {
    return fallback;
  }
  return parsed;
}

function parseSortDirection(value: string | null, fallback: SortDirection) {
  return value === "asc" || value === "desc" ? value : fallback;
}

function parseSortField(value: string | null, fallback: string, allowedValues: Set<string>) {
  return value && allowedValues.has(value) ? value : fallback;
}

function parseDrilldownUrlState(search: string): DrilldownUrlState {
  const params = new URLSearchParams(search);
  return {
    scenePage: parsePositiveInteger(params.get("scene_page"), DEFAULT_DRILLDOWN_URL_STATE.scenePage),
    scenePageSize: parsePositiveInteger(params.get("scene_page_size"), DEFAULT_DRILLDOWN_URL_STATE.scenePageSize, PAGE_SIZE_OPTIONS),
    sceneSearch: params.get("scene_search") ?? DEFAULT_DRILLDOWN_URL_STATE.sceneSearch,
    sceneSource: params.get("scene_source") ?? DEFAULT_DRILLDOWN_URL_STATE.sceneSource,
    sceneAoiCode: params.get("scene_aoi_code") ?? DEFAULT_DRILLDOWN_URL_STATE.sceneAoiCode,
    sceneProcessingStatus: params.get("scene_processing_status") ?? DEFAULT_DRILLDOWN_URL_STATE.sceneProcessingStatus,
    sceneSortBy: parseSortField(params.get("scene_sort_by"), DEFAULT_DRILLDOWN_URL_STATE.sceneSortBy, SCENE_SORT_FIELDS),
    sceneSortDir: parseSortDirection(params.get("scene_sort_dir"), DEFAULT_DRILLDOWN_URL_STATE.sceneSortDir),
    featurePage: parsePositiveInteger(params.get("feature_page"), DEFAULT_DRILLDOWN_URL_STATE.featurePage),
    featurePageSize: parsePositiveInteger(params.get("feature_page_size"), DEFAULT_DRILLDOWN_URL_STATE.featurePageSize, PAGE_SIZE_OPTIONS),
    featureSearch: params.get("feature_search") ?? DEFAULT_DRILLDOWN_URL_STATE.featureSearch,
    featureSource: params.get("feature_source") ?? DEFAULT_DRILLDOWN_URL_STATE.featureSource,
    featureAoiCode: params.get("feature_aoi_code") ?? DEFAULT_DRILLDOWN_URL_STATE.featureAoiCode,
    featureSortBy: parseSortField(params.get("feature_sort_by"), DEFAULT_DRILLDOWN_URL_STATE.featureSortBy, FEATURE_SORT_FIELDS),
    featureSortDir: parseSortDirection(params.get("feature_sort_dir"), DEFAULT_DRILLDOWN_URL_STATE.featureSortDir),
  };
}

function buildDrilldownUrlQuery(state: DrilldownUrlState) {
  return buildQueryString({
    scene_page: state.scenePage === DEFAULT_DRILLDOWN_URL_STATE.scenePage ? undefined : state.scenePage,
    scene_page_size: state.scenePageSize === DEFAULT_DRILLDOWN_URL_STATE.scenePageSize ? undefined : state.scenePageSize,
    scene_search: state.sceneSearch || undefined,
    scene_source: state.sceneSource || undefined,
    scene_aoi_code: state.sceneAoiCode || undefined,
    scene_processing_status: state.sceneProcessingStatus || undefined,
    scene_sort_by: state.sceneSortBy === DEFAULT_DRILLDOWN_URL_STATE.sceneSortBy ? undefined : state.sceneSortBy,
    scene_sort_dir: state.sceneSortDir === DEFAULT_DRILLDOWN_URL_STATE.sceneSortDir ? undefined : state.sceneSortDir,
    feature_page: state.featurePage === DEFAULT_DRILLDOWN_URL_STATE.featurePage ? undefined : state.featurePage,
    feature_page_size: state.featurePageSize === DEFAULT_DRILLDOWN_URL_STATE.featurePageSize ? undefined : state.featurePageSize,
    feature_search: state.featureSearch || undefined,
    feature_source: state.featureSource || undefined,
    feature_aoi_code: state.featureAoiCode || undefined,
    feature_sort_by: state.featureSortBy === DEFAULT_DRILLDOWN_URL_STATE.featureSortBy ? undefined : state.featureSortBy,
    feature_sort_dir: state.featureSortDir === DEFAULT_DRILLDOWN_URL_STATE.featureSortDir ? undefined : state.featureSortDir,
  });
}

function csvEscape(value: unknown) {
  if (value == null) {
    return "";
  }
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return `"${text.replace(/"/g, '""')}"`;
}

function buildCsvContent<T extends Record<string, unknown>>(rows: T[], columns: Array<{ key: keyof T | string; label: string }>) {
  const header = columns.map((column) => csvEscape(column.label)).join(",");
  const dataRows = rows.map((row) => columns.map((column) => csvEscape(row[String(column.key)])).join(","));
  return [header, ...dataRows].join("\n");
}

function downloadTextFile(filename: string, content: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType });
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
}

function formatDiagnosticsValue(value: unknown) {
  if (value == null) {
    return "n/a";
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
}

function getFailureDiagnostics(run: PipelineRunItem) {
  const results = run.results ?? {};
  const sceneDiscovery = (results.scene_discovery as Record<string, unknown> | undefined) ?? null;
  const materialized = (results.materialized as Record<string, unknown> | undefined) ?? null;
  const details = [
    { label: "Status", value: run.status },
    { label: "Summary", value: summarizeRunResults(run) },
    { label: "Correlation", value: run.correlation_id ?? "n/a" },
    { label: "Notes", value: run.notes ?? "n/a" },
  ];

  if (typeof results.error === "string" && results.error.trim()) {
    details.push({ label: "Primary error", value: results.error });
  }
  if (typeof results.message === "string" && results.message.trim()) {
    details.push({ label: "Message", value: results.message });
  }
  if (sceneDiscovery && (sceneDiscovery.error != null || sceneDiscovery.phase != null)) {
    details.push({ label: "Scene discovery", value: formatDiagnosticsValue(sceneDiscovery) });
  }
  if (materialized && (materialized.error != null || materialized.phase != null)) {
    details.push({ label: "Feature materialization", value: formatDiagnosticsValue(materialized) });
  }

  const showDiagnostics = run.status === "failed" || run.status === "cancelled" || run.status === "cancel_requested" || details.some((detail) => detail.label === "Primary error" || detail.label === "Message");

  return {
    showDiagnostics,
    details,
    rawResults: JSON.stringify(results ?? {}, null, 2),
  };
}

function statusBadgeClass(status: string) {
  switch (status) {
    case "completed":
      return "bg-emerald-100 text-emerald-700";
    case "running":
      return "bg-blue-100 text-blue-700";
    case "queued":
      return "bg-amber-100 text-amber-700";
    case "cancel_requested":
      return "bg-orange-100 text-orange-700";
    case "cancelled":
      return "bg-slate-200 text-slate-700";
    case "failed":
      return "bg-rose-100 text-rose-700";
    default:
      return "bg-slate-100 text-slate-700";
  }
}

function formatMetric(value: number | null | undefined) {
  return value == null ? "n/a" : Number(value).toFixed(3);
}

function formatElapsedTime(startedAt: string | null, finishedAt: string | null) {
  if (!startedAt) {
    return "n/a";
  }
  const start = new Date(startedAt).getTime();
  const end = finishedAt ? new Date(finishedAt).getTime() : Date.now();
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) {
    return "n/a";
  }
  const totalSeconds = Math.max(0, Math.round((end - start) / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes > 0) {
    return `${minutes}m ${seconds}s`;
  }
  return `${seconds}s`;
}

function summarizeRunResults(run: PipelineRunItem) {
  const results = run.results ?? {};
  const error = typeof results.error === "string" ? results.error : null;
  if (error) {
    return error;
  }
  if (run.status === "cancel_requested") {
    return "Cancellation requested";
  }
  if (run.status === "cancelled") {
    return "Cancelled";
  }

  const discovery = (results.scene_discovery as Record<string, unknown> | undefined) ?? null;
  if (discovery) {
    const inserted = Number(discovery.inserted ?? 0);
    const discovered = Number(discovery.discovered ?? 0);
    return `${discovered} discovered · ${inserted} inserted`;
  }

  const materialized = (results.materialized as Record<string, unknown> | undefined) ?? null;
  if (materialized) {
    const inserted = Number(materialized.features_inserted ?? 0);
    const updated = Number(materialized.features_updated ?? 0);
    return `${inserted} inserted · ${updated} updated`;
  }

  return run.status === "queued" || run.status === "running" ? "In progress" : "No summary";
}

function PaginationControls({
  label,
  page,
  pageSize,
  total,
  totalPages,
  onPrevious,
  onNext,
  onPageSizeChange,
}: {
  label: string;
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  onPrevious: () => void;
  onNext: () => void;
  onPageSizeChange: (value: number) => void;
}) {
  return (
    <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
      <div className="text-sm text-slate-500">
        {label}: {total} total · Page {page} of {totalPages}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <label className="text-xs text-slate-500">
          Page size
          <select
            value={pageSize}
            onChange={(event) => onPageSizeChange(Number(event.target.value))}
            className="ml-2 rounded border border-slate-300 px-2 py-1 text-xs text-slate-700"
          >
            {PAGE_SIZE_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={onPrevious}
          disabled={page <= 1}
          className="rounded border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          Previous
        </button>
        <button
          type="button"
          onClick={onNext}
          disabled={page >= totalPages}
          className="rounded border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          Next
        </button>
      </div>
    </div>
  );
}

function buildQueryString(params: Record<string, string | number | null | undefined>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value == null) continue;
    const text = String(value).trim();
    if (!text) continue;
    search.set(key, text);
  }
  return search.toString();
}

function formatObservationDate(value: string | null | undefined) {
  return value ? value.slice(0, 10) : "";
}

function buildAoiContextHref({
  aoiId,
  runId,
  focus,
  sceneId,
  returnTo,
  source,
  observationDate,
}: {
  aoiId: number | null;
  runId: number;
  focus: "aoi" | "observations" | "timeline";
  sceneId?: string | null;
  returnTo?: string | null;
  source?: string | null;
  observationDate?: string | null;
}) {
  const query = buildQueryString({
    aoiId,
    runId,
    focus,
    sceneId: sceneId ?? undefined,
    returnTo: returnTo ?? undefined,
    source: source ?? undefined,
    observationDate: formatObservationDate(observationDate),
  });
  return `/dashboard/geospatial/aois?${query}`;
}

function TableControlBar({
  searchLabel,
  searchValue,
  onSearchChange,
  sourceValue,
  sourceOptions,
  onSourceChange,
  aoiCodeValue,
  onAoiCodeChange,
  sortByValue,
  sortByLabel,
  sortOptions,
  onSortByChange,
  sortDirValue,
  onSortDirChange,
  statusValue,
  statusOptions,
  onStatusChange,
}: {
  searchLabel: string;
  searchValue: string;
  onSearchChange: (value: string) => void;
  sourceValue: string;
  sourceOptions: string[];
  onSourceChange: (value: string) => void;
  aoiCodeValue: string;
  onAoiCodeChange: (value: string) => void;
  sortByValue: string;
  sortByLabel?: string;
  sortOptions: Array<{ value: string; label: string }>;
  onSortByChange: (value: string) => void;
  sortDirValue: SortDirection;
  onSortDirChange: (value: SortDirection) => void;
  statusValue?: string;
  statusOptions?: string[];
  onStatusChange?: (value: string) => void;
}) {
  return (
    <div className="sticky top-2 z-10 mb-3 grid gap-3 rounded-lg border border-slate-200 bg-slate-50 p-3 lg:grid-cols-6">
      <label className="text-xs text-slate-600 lg:col-span-2">
        {searchLabel}
        <input
          value={searchValue}
          onChange={(event) => onSearchChange(event.target.value)}
          className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm text-slate-700"
          placeholder="Search"
        />
      </label>
      <label className="text-xs text-slate-600">
        Source
        <select value={sourceValue} onChange={(event) => onSourceChange(event.target.value)} className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm text-slate-700">
          <option value="">All</option>
          {sourceOptions.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </label>
      <label className="text-xs text-slate-600">
        AOI code
        <input
          value={aoiCodeValue}
          onChange={(event) => onAoiCodeChange(event.target.value)}
          className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm text-slate-700"
          placeholder="AOI"
        />
      </label>
      {statusOptions && onStatusChange ? (
        <label className="text-xs text-slate-600">
          Processing
          <select value={statusValue ?? ""} onChange={(event) => onStatusChange(event.target.value)} className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm text-slate-700">
            <option value="">All</option>
            {statusOptions.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      <label className="text-xs text-slate-600">
        {sortByLabel ?? "Sort by"}
        <select value={sortByValue} onChange={(event) => onSortByChange(event.target.value)} className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm text-slate-700">
          {sortOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <label className="text-xs text-slate-600">
        Direction
        <select value={sortDirValue} onChange={(event) => onSortDirChange(event.target.value as SortDirection)} className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm text-slate-700">
          <option value="desc">Descending</option>
          <option value="asc">Ascending</option>
        </select>
      </label>
    </div>
  );
}

export default function GeospatialRunDrilldownPage() {
  const params = useParams<{ runId: string }>();
  const rawRunId = params?.runId;
  const runId = Number(Array.isArray(rawRunId) ? rawRunId[0] : rawRunId);
  const { token } = useAuth();

  const [scenePage, setScenePage] = useState(DEFAULT_DRILLDOWN_URL_STATE.scenePage);
  const [scenePageSize, setScenePageSize] = useState(DEFAULT_DRILLDOWN_URL_STATE.scenePageSize);
  const [sceneSearch, setSceneSearch] = useState(DEFAULT_DRILLDOWN_URL_STATE.sceneSearch);
  const [sceneSource, setSceneSource] = useState(DEFAULT_DRILLDOWN_URL_STATE.sceneSource);
  const [sceneAoiCode, setSceneAoiCode] = useState(DEFAULT_DRILLDOWN_URL_STATE.sceneAoiCode);
  const [sceneProcessingStatus, setSceneProcessingStatus] = useState(DEFAULT_DRILLDOWN_URL_STATE.sceneProcessingStatus);
  const [sceneSortBy, setSceneSortBy] = useState(DEFAULT_DRILLDOWN_URL_STATE.sceneSortBy);
  const [sceneSortDir, setSceneSortDir] = useState<SortDirection>(DEFAULT_DRILLDOWN_URL_STATE.sceneSortDir);
  const [featurePage, setFeaturePage] = useState(DEFAULT_DRILLDOWN_URL_STATE.featurePage);
  const [featurePageSize, setFeaturePageSize] = useState(DEFAULT_DRILLDOWN_URL_STATE.featurePageSize);
  const [featureSearch, setFeatureSearch] = useState(DEFAULT_DRILLDOWN_URL_STATE.featureSearch);
  const [featureSource, setFeatureSource] = useState(DEFAULT_DRILLDOWN_URL_STATE.featureSource);
  const [featureAoiCode, setFeatureAoiCode] = useState(DEFAULT_DRILLDOWN_URL_STATE.featureAoiCode);
  const [featureSortBy, setFeatureSortBy] = useState(DEFAULT_DRILLDOWN_URL_STATE.featureSortBy);
  const [featureSortDir, setFeatureSortDir] = useState<SortDirection>(DEFAULT_DRILLDOWN_URL_STATE.featureSortDir);
  const [isUrlStateReady, setIsUrlStateReady] = useState(false);
  const [shareStatus, setShareStatus] = useState<string | null>(null);
  const [isExportingScenes, setIsExportingScenes] = useState(false);
  const [isExportingFeatures, setIsExportingFeatures] = useState(false);
  const [previewScene, setPreviewScene] = useState<SceneProvenanceItem | null>(null);
  const [previewFeature, setPreviewFeature] = useState<FeatureProvenanceItem | null>(null);
  const [shareFallbackHref, setShareFallbackHref] = useState("");
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(true);
  const stickyReturnToRef = useRef<string>("");

  useEffect(() => {
    const applyUrlState = () => {
      const urlState = parseDrilldownUrlState(window.location.search);
      setScenePage(urlState.scenePage);
      setScenePageSize(urlState.scenePageSize);
      setSceneSearch(urlState.sceneSearch);
      setSceneSource(urlState.sceneSource);
      setSceneAoiCode(urlState.sceneAoiCode);
      setSceneProcessingStatus(urlState.sceneProcessingStatus);
      setSceneSortBy(urlState.sceneSortBy);
      setSceneSortDir(urlState.sceneSortDir);
      setFeaturePage(urlState.featurePage);
      setFeaturePageSize(urlState.featurePageSize);
      setFeatureSearch(urlState.featureSearch);
      setFeatureSource(urlState.featureSource);
      setFeatureAoiCode(urlState.featureAoiCode);
      setFeatureSortBy(urlState.featureSortBy);
      setFeatureSortDir(urlState.featureSortDir);
      setIsUrlStateReady(true);
    };

    applyUrlState();
    window.addEventListener("popstate", applyUrlState);
    return () => window.removeEventListener("popstate", applyUrlState);
  }, []);

  useEffect(() => {
    if (!isUrlStateReady) {
      return;
    }
    const nextSearch = buildDrilldownUrlQuery({
      scenePage,
      scenePageSize,
      sceneSearch,
      sceneSource,
      sceneAoiCode,
      sceneProcessingStatus,
      sceneSortBy,
      sceneSortDir,
      featurePage,
      featurePageSize,
      featureSearch,
      featureSource,
      featureAoiCode,
      featureSortBy,
      featureSortDir,
    });
    const currentSearch = window.location.search.startsWith("?") ? window.location.search.slice(1) : window.location.search;
    if (nextSearch === currentSearch) {
      return;
    }
    const nextUrl = nextSearch ? `${window.location.pathname}?${nextSearch}` : window.location.pathname;
    window.history.replaceState(window.history.state, "", nextUrl);
  }, [
    featureAoiCode,
    featurePage,
    featurePageSize,
    featureSearch,
    featureSortBy,
    featureSortDir,
    featureSource,
    isUrlStateReady,
    sceneAoiCode,
    scenePage,
    scenePageSize,
    sceneProcessingStatus,
    sceneSearch,
    sceneSortBy,
    sceneSortDir,
    sceneSource,
  ]);

  useEffect(() => {
    if (!shareStatus) {
      return;
    }
    const timeout = window.setTimeout(() => setShareStatus(null), 2500);
    return () => window.clearTimeout(timeout);
  }, [shareStatus]);

  const runDetail = useQuery({
    queryKey: ["geospatial-pipeline-run-detail", token, runId],
    queryFn: () => apiFetch<PipelineRunDetail>(`/api/v1/geospatial/runs/${runId}`, { token }),
    enabled: isUrlStateReady && !!token && Number.isFinite(runId),
    refetchInterval: (query) => {
      const row = query.state.data as PipelineRunDetail | undefined;
      if (!autoRefreshEnabled) {
        return false;
      }
      return row != null && ["queued", "running", "cancel_requested"].includes(row.status) ? 4000 : false;
    },
  });

  const sceneRows = useQuery({
    queryKey: ["geospatial-pipeline-run-scenes", token, runId, scenePage, scenePageSize, sceneSearch, sceneSource, sceneAoiCode, sceneProcessingStatus, sceneSortBy, sceneSortDir],
    queryFn: () => {
      const query = buildQueryString({
        page: scenePage,
        page_size: scenePageSize,
        search: sceneSearch,
        source: sceneSource,
        aoi_code: sceneAoiCode,
        processing_status: sceneProcessingStatus,
        sort_by: sceneSortBy,
        sort_dir: sceneSortDir,
      });
      return apiFetch<PaginatedProvenanceResponse<SceneProvenanceItem>>(`/api/v1/geospatial/runs/${runId}/provenance/scenes?${query}`, { token });
    },
    enabled: isUrlStateReady && !!token && Number.isFinite(runId),
    refetchInterval: () => {
      if (!autoRefreshEnabled) {
        return false;
      }
      return runDetail.data && ["queued", "running", "cancel_requested"].includes(runDetail.data.status) ? 4000 : false;
    },
  });

  const featureRows = useQuery({
    queryKey: ["geospatial-pipeline-run-features", token, runId, featurePage, featurePageSize, featureSearch, featureSource, featureAoiCode, featureSortBy, featureSortDir],
    queryFn: () => {
      const query = buildQueryString({
        page: featurePage,
        page_size: featurePageSize,
        search: featureSearch,
        source: featureSource,
        aoi_code: featureAoiCode,
        sort_by: featureSortBy,
        sort_dir: featureSortDir,
      });
      return apiFetch<PaginatedProvenanceResponse<FeatureProvenanceItem>>(`/api/v1/geospatial/runs/${runId}/provenance/features?${query}`, { token });
    },
    enabled: isUrlStateReady && !!token && Number.isFinite(runId),
    refetchInterval: () => {
      if (!autoRefreshEnabled) {
        return false;
      }
      return runDetail.data && ["queued", "running", "cancel_requested"].includes(runDetail.data.status) ? 4000 : false;
    },
  });
  const sceneProvenanceChain = useQuery({
    queryKey: ["geospatial-run-scene-provenance-chain", token, runId, previewScene?.source, previewScene?.scene_id],
    queryFn: () =>
      apiFetch<SceneProvenanceChainResponse>(
        `/api/v1/geospatial/runs/${runId}/scenes/provenance-chain?source=${encodeURIComponent(previewScene?.source ?? "")}&scene_id=${encodeURIComponent(previewScene?.scene_id ?? "")}`,
        { token },
      ),
    enabled: isUrlStateReady && !!token && Number.isFinite(runId) && !!previewScene?.source && !!previewScene?.scene_id,
  });

  if (!Number.isFinite(runId)) {
    return <ErrorState message="Invalid geospatial run id" />;
  }

  if (!isUrlStateReady || runDetail.isLoading) {
    return <LoadingState label="Loading geospatial run drilldown..." />;
  }

  if (runDetail.error || !runDetail.data) {
    return <ErrorState message="Failed to load geospatial run drilldown" />;
  }

  const run = runDetail.data;
  const scenes = sceneRows.data;
  const features = featureRows.data;
  const sceneProcessingOptions = Array.from(new Set([...(scenes?.rows ?? []), ...(run.related_scenes ?? [])].map((row) => String(row.processing_status ?? "")).filter(Boolean))).sort();
  const failureDiagnostics = getFailureDiagnostics(run);
  const currentDrilldownQuery = buildDrilldownUrlQuery({
    scenePage,
    scenePageSize,
    sceneSearch,
    sceneSource,
    sceneAoiCode,
    sceneProcessingStatus,
    sceneSortBy,
    sceneSortDir,
    featurePage,
    featurePageSize,
    featureSearch,
    featureSource,
    featureAoiCode,
    featureSortBy,
    featureSortDir,
  });
  const currentDrilldownHref = currentDrilldownQuery ? `/dashboard/geospatial/runs/${run.id}?${currentDrilldownQuery}` : `/dashboard/geospatial/runs/${run.id}`;
  if (
    currentDrilldownHref.includes("feature_search=") ||
    (!stickyReturnToRef.current && currentDrilldownHref.includes("scene_search="))
  ) {
    stickyReturnToRef.current = currentDrilldownHref;
  }
  const returnToHref = stickyReturnToRef.current || currentDrilldownHref;
  const backToGeospatialHref = buildAoiContextHref({
    aoiId: run.aoi_id,
    runId: run.id,
    focus: "aoi",
    returnTo: returnToHref,
  });
  const hasActiveSceneFilters =
    sceneSearch !== DEFAULT_DRILLDOWN_URL_STATE.sceneSearch ||
    sceneSource !== DEFAULT_DRILLDOWN_URL_STATE.sceneSource ||
    sceneAoiCode !== DEFAULT_DRILLDOWN_URL_STATE.sceneAoiCode ||
    sceneProcessingStatus !== DEFAULT_DRILLDOWN_URL_STATE.sceneProcessingStatus ||
    sceneSortBy !== DEFAULT_DRILLDOWN_URL_STATE.sceneSortBy ||
    sceneSortDir !== DEFAULT_DRILLDOWN_URL_STATE.sceneSortDir ||
    scenePage !== DEFAULT_DRILLDOWN_URL_STATE.scenePage ||
    scenePageSize !== DEFAULT_DRILLDOWN_URL_STATE.scenePageSize;
  const hasActiveFeatureFilters =
    featureSearch !== DEFAULT_DRILLDOWN_URL_STATE.featureSearch ||
    featureSource !== DEFAULT_DRILLDOWN_URL_STATE.featureSource ||
    featureAoiCode !== DEFAULT_DRILLDOWN_URL_STATE.featureAoiCode ||
    featureSortBy !== DEFAULT_DRILLDOWN_URL_STATE.featureSortBy ||
    featureSortDir !== DEFAULT_DRILLDOWN_URL_STATE.featureSortDir ||
    featurePage !== DEFAULT_DRILLDOWN_URL_STATE.featurePage ||
    featurePageSize !== DEFAULT_DRILLDOWN_URL_STATE.featurePageSize;

  const handleCopyShareLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setShareStatus("Link copied");
      setShareFallbackHref("");
    } catch {
      setShareStatus("Copy failed");
      setShareFallbackHref(window.location.href);
    }
  };

  const fetchAllPages = async <T,>(buildEndpoint: (page: number, pageSize: number) => string) => {
    const pageSize = 200;
    const firstPage = await apiFetch<PaginatedProvenanceResponse<T>>(buildEndpoint(1, pageSize), { token });
    const rows = [...(firstPage.rows ?? [])];
    for (let page = 2; page <= firstPage.total_pages; page += 1) {
      const nextPage = await apiFetch<PaginatedProvenanceResponse<T>>(buildEndpoint(page, pageSize), { token });
      rows.push(...(nextPage.rows ?? []));
    }
    return rows;
  };

  const handleExportScenes = async () => {
    try {
      setIsExportingScenes(true);
      const rows = await fetchAllPages<SceneProvenanceItem>((page, pageSize) => {
        const query = buildQueryString({
          page,
          page_size: pageSize,
          search: sceneSearch,
          source: sceneSource,
          aoi_code: sceneAoiCode,
          processing_status: sceneProcessingStatus,
          sort_by: sceneSortBy,
          sort_dir: sceneSortDir,
        });
        return `/api/v1/geospatial/runs/${run.id}/provenance/scenes?${query}`;
      });
      const csv = buildCsvContent(rows as unknown as Record<string, unknown>[], [
        { key: "source", label: "Source" },
        { key: "scene_id", label: "Scene ID" },
        { key: "aoi_code", label: "AOI Code" },
        { key: "aoi_name", label: "AOI Name" },
        { key: "acquired_at", label: "Acquired At" },
        { key: "cloud_score", label: "Cloud Score" },
        { key: "spatial_resolution_m", label: "Spatial Resolution (m)" },
        { key: "processing_status", label: "Processing Status" },
        { key: "provenance_status", label: "Provenance Status" },
      ]);
      downloadTextFile(`geospatial-run-${run.id}-scenes.csv`, csv, "text/csv;charset=utf-8");
      setShareStatus(`Scene CSV exported (${rows.length} rows)`);
    } catch {
      setShareStatus("Scene CSV export failed");
    } finally {
      setIsExportingScenes(false);
    }
  };

  const handleExportFeatures = async () => {
    try {
      setIsExportingFeatures(true);
      const rows = await fetchAllPages<FeatureProvenanceItem>((page, pageSize) => {
        const query = buildQueryString({
          page,
          page_size: pageSize,
          search: featureSearch,
          source: featureSource,
          aoi_code: featureAoiCode,
          sort_by: featureSortBy,
          sort_dir: featureSortDir,
        });
        return `/api/v1/geospatial/runs/${run.id}/provenance/features?${query}`;
      });
      const csv = buildCsvContent(rows as unknown as Record<string, unknown>[], [
        { key: "source", label: "Source" },
        { key: "observation_date", label: "Observation Date" },
        { key: "reporting_month", label: "Reporting Month" },
        { key: "aoi_code", label: "AOI Code" },
        { key: "aoi_name", label: "AOI Name" },
        { key: "scene_id", label: "Scene ID" },
        { key: "observation_confidence_score", label: "Confidence Score" },
        { key: "crop_activity_score", label: "Crop Activity Score" },
        { key: "vegetation_vigor_score", label: "Vegetation Vigor Score" },
        { key: "cloud_score", label: "Cloud Score" },
      ]);
      downloadTextFile(`geospatial-run-${run.id}-features.csv`, csv, "text/csv;charset=utf-8");
      setShareStatus(`Feature CSV exported (${rows.length} rows)`);
    } catch {
      setShareStatus("Feature CSV export failed");
    } finally {
      setIsExportingFeatures(false);
    }
  };

  const previewSceneFeatures = previewScene ? (run.related_features ?? []).filter((item) => item.scene_id === previewScene.scene_id).slice(0, 5) : [];
  const previewFeatureScene = previewFeature ? (run.related_scenes ?? []).find((item) => item.scene_id === previewFeature.scene_id) ?? null : null;
  const fallbackScenePreview: SceneProvenanceItem = {
    id: null,
    source: run.sources?.[0] ?? "synthetic",
    scene_id: `run-${run.id}-scene`,
    aoi_id: run.aoi_id ?? null,
    aoi_code: run.aoi_code ?? null,
    aoi_name: run.aoi_name ?? null,
    acquired_at: run.started_at,
    cloud_score: null,
    spatial_resolution_m: null,
    processing_status: "not_available",
    provenance_status: "placeholder",
  };
  const fallbackFeaturePreview: FeatureProvenanceItem = {
    id: 0,
    aoi_id: run.aoi_id ?? 0,
    aoi_code: run.aoi_code ?? null,
    aoi_name: run.aoi_name ?? null,
    source: run.sources?.[0] ?? "synthetic",
    observation_date: run.started_at,
    reporting_month: null,
    cloud_score: null,
    crop_activity_score: null,
    vegetation_vigor_score: null,
    observation_confidence_score: null,
    scene_id: fallbackScenePreview.scene_id,
    acquired_at: fallbackScenePreview.acquired_at,
  };

  return (
    <div>
      <PageHeader
        title={`Geospatial Run #${run.id}`}
        subtitle="Full drilldown for traceable scene evidence and feature outputs linked to this pipeline run."
        actions={
          <div className="flex flex-wrap gap-2">
            <a
              href={backToGeospatialHref}
              className="rounded border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Back to geospatial
            </a>
            <a
              href={`/dashboard/geospatial/runs/${run.id}/artifacts`}
              className="rounded border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Artifact center
            </a>
            <button
              type="button"
              onClick={() => {
                void handleCopyShareLink();
              }}
              className="rounded border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Copy share link
            </button>
            <button
              type="button"
              onClick={() => setAutoRefreshEnabled((value) => !value)}
              className="rounded border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Auto-refresh: {autoRefreshEnabled ? "On" : "Off"}
            </button>
            <button
              type="button"
              onClick={() => {
                void Promise.all([runDetail.refetch(), sceneRows.refetch(), featureRows.refetch()]);
              }}
              className="rounded border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Refresh
            </button>
          </div>
        }
      />

      {shareStatus ? (
        <div className="mb-4 space-y-2" role="status" aria-live="polite">
          <div className="text-sm text-slate-600">{shareStatus}</div>
          {shareFallbackHref ? (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
              <div className="font-semibold">Clipboard access unavailable</div>
              <div className="mt-1">Copy the saved drilldown link manually:</div>
              <input
                readOnly
                value={shareFallbackHref}
                onFocus={(event) => event.currentTarget.select()}
                className="mt-2 w-full rounded border border-amber-200 bg-white px-2 py-1 text-xs text-slate-700"
                aria-label="Manual share link"
              />
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="mb-6 grid gap-4 md:grid-cols-4">
        <StatCard label="Status" value={run.status} hint={`${run.run_type} · ${run.backend}`} />
        <StatCard label="Elapsed" value={formatElapsedTime(run.started_at, run.finished_at)} hint={run.started_at ?? "n/a"} />
        <StatCard label="Scenes" value={run.provenance_summary.scene_count} hint={(run.provenance_summary.scene_sources ?? []).join(", ") || "none"} />
        <StatCard label="Features" value={run.provenance_summary.feature_count} hint={(run.provenance_summary.feature_sources ?? []).join(", ") || "none"} />
      </div>

      <SectionShell title="Run summary">
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <span className={`rounded-full px-2 py-1 text-xs font-semibold ${statusBadgeClass(run.status)}`}>{run.status}</span>
              <span className="text-sm text-slate-500">AOI: {run.aoi_code ?? "all"}</span>
              <span className="text-sm text-slate-500">Correlation: {run.correlation_id ?? "n/a"}</span>
            </div>
            <div className="text-sm text-slate-700">Summary: {summarizeRunResults(run)}</div>
            <div className="mt-2 text-sm text-slate-700">Sources: {(run.sources ?? []).join(", ") || "all"}</div>
            <div className="mt-2 text-sm text-slate-700">Notes: {run.notes ?? "n/a"}</div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
              <div className="text-xs uppercase tracking-wide text-slate-500">Parameters</div>
              <pre className="mt-2 overflow-x-auto rounded bg-slate-50 p-3 text-xs text-slate-700">{JSON.stringify(run.parameters ?? {}, null, 2)}</pre>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
              <div className="text-xs uppercase tracking-wide text-slate-500">Results</div>
              <pre className="mt-2 overflow-x-auto rounded bg-slate-50 p-3 text-xs text-slate-700">{JSON.stringify(run.results ?? {}, null, 2)}</pre>
            </div>
          </div>
        </div>
      </SectionShell>

      {failureDiagnostics.showDiagnostics ? (
        <SectionShell title="Failure diagnostics">
          <div className="grid gap-4 lg:grid-cols-[1.2fr,0.8fr]">
            <div className="rounded-lg border border-rose-200 bg-rose-50 p-4">
              <div className="text-sm font-semibold text-rose-800">Operator diagnostics</div>
              <div className="mt-3 space-y-3 text-sm text-rose-900">
                {failureDiagnostics.details.map((detail) => (
                  <div key={detail.label}>
                    <div className="text-xs font-semibold uppercase tracking-wide text-rose-700">{detail.label}</div>
                    <div className="mt-1 break-words">{detail.value}</div>
                  </div>
                ))}
              </div>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
              <div className="text-xs uppercase tracking-wide text-slate-500">Raw results</div>
              <pre className="mt-2 overflow-x-auto rounded bg-slate-50 p-3 text-xs text-slate-700">{failureDiagnostics.rawResults}</pre>
            </div>
          </div>
        </SectionShell>
      ) : null}

      <SectionShell title="Scene provenance">
        <div className="mb-3 flex flex-wrap items-center justify-end gap-2">
          <button
            type="button"
            onClick={() => {
              setScenePage(DEFAULT_DRILLDOWN_URL_STATE.scenePage);
              setScenePageSize(DEFAULT_DRILLDOWN_URL_STATE.scenePageSize);
              setSceneSearch(DEFAULT_DRILLDOWN_URL_STATE.sceneSearch);
              setSceneSource(DEFAULT_DRILLDOWN_URL_STATE.sceneSource);
              setSceneAoiCode(DEFAULT_DRILLDOWN_URL_STATE.sceneAoiCode);
              setSceneProcessingStatus(DEFAULT_DRILLDOWN_URL_STATE.sceneProcessingStatus);
              setSceneSortBy(DEFAULT_DRILLDOWN_URL_STATE.sceneSortBy);
              setSceneSortDir(DEFAULT_DRILLDOWN_URL_STATE.sceneSortDir);
            }}
            disabled={!hasActiveSceneFilters}
            className="rounded border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Reset scene filters
          </button>
          <button
            type="button"
            onClick={() => {
              void handleExportScenes();
            }}
            disabled={isExportingScenes}
            className="rounded border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isExportingScenes ? "Exporting scenes..." : "Export scene CSV"}
          </button>
        </div>
        <div data-testid="run-scenes-table">
          {sceneRows.isLoading && !scenes ? <LoadingState label="Loading scene provenance..." /> : null}
          {sceneRows.error ? <ErrorState message="Failed to load scene provenance" /> : null}
          {scenes ? (
            scenes.rows.length === 0 ? (
              <>
                <TableControlBar
                  searchLabel="Scene search"
                  searchValue={sceneSearch}
                  onSearchChange={(value) => {
                    setSceneSearch(value);
                    setScenePage(1);
                  }}
                  sourceValue={sceneSource}
                  sourceOptions={run.provenance_summary.scene_sources ?? []}
                  onSourceChange={(value) => {
                    setSceneSource(value);
                    setScenePage(1);
                  }}
                  aoiCodeValue={sceneAoiCode}
                  onAoiCodeChange={(value) => {
                    setSceneAoiCode(value);
                    setScenePage(1);
                  }}
                  statusValue={sceneProcessingStatus}
                  statusOptions={sceneProcessingOptions}
                  onStatusChange={(value) => {
                    setSceneProcessingStatus(value);
                    setScenePage(1);
                  }}
                  sortByValue={sceneSortBy}
                  sortOptions={[
                    { value: "acquired_at", label: "Acquired time" },
                    { value: "source", label: "Source" },
                    { value: "aoi_code", label: "AOI code" },
                    { value: "cloud_score", label: "Cloud score" },
                    { value: "spatial_resolution_m", label: "Resolution" },
                    { value: "scene_id", label: "Scene ID" },
                  ]}
                  onSortByChange={(value) => {
                    setSceneSortBy(value);
                    setScenePage(1);
                  }}
                  sortDirValue={sceneSortDir}
                  onSortDirChange={(value) => {
                    setSceneSortDir(value);
                    setScenePage(1);
                  }}
                />
                <EmptyState title="No scenes found" description="This run does not currently expose any linked scene rows for the current filters." />
                <div className="mt-3 flex flex-wrap gap-3">
                  <button
                    type="button"
                    onClick={() => setPreviewScene(fallbackScenePreview)}
                    className="rounded border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
                  >
                    Preview
                  </button>
                  {fallbackScenePreview.aoi_id != null ? (
                    <a
                      href={buildAoiContextHref({
                        aoiId: fallbackScenePreview.aoi_id,
                        runId: run.id,
                        focus: "observations",
                        sceneId: fallbackScenePreview.scene_id,
                        returnTo: returnToHref,
                        source: fallbackScenePreview.source,
                        observationDate: fallbackScenePreview.acquired_at,
                      })}
                      className="text-xs font-medium text-sky-700 hover:underline"
                    >
                      Observation history
                    </a>
                  ) : null}
                </div>
              </>
            ) : (
              <>
                <TableControlBar
                  searchLabel="Scene search"
                  searchValue={sceneSearch}
                  onSearchChange={(value) => {
                    setSceneSearch(value);
                    setScenePage(1);
                  }}
                  sourceValue={sceneSource}
                  sourceOptions={run.provenance_summary.scene_sources ?? []}
                  onSourceChange={(value) => {
                    setSceneSource(value);
                    setScenePage(1);
                  }}
                  aoiCodeValue={sceneAoiCode}
                  onAoiCodeChange={(value) => {
                    setSceneAoiCode(value);
                    setScenePage(1);
                  }}
                  statusValue={sceneProcessingStatus}
                  statusOptions={sceneProcessingOptions}
                  onStatusChange={(value) => {
                    setSceneProcessingStatus(value);
                    setScenePage(1);
                  }}
                  sortByValue={sceneSortBy}
                  sortOptions={[
                    { value: "acquired_at", label: "Acquired time" },
                    { value: "source", label: "Source" },
                    { value: "aoi_code", label: "AOI code" },
                    { value: "cloud_score", label: "Cloud score" },
                    { value: "spatial_resolution_m", label: "Resolution" },
                    { value: "scene_id", label: "Scene ID" },
                  ]}
                  onSortByChange={(value) => {
                    setSceneSortBy(value);
                    setScenePage(1);
                  }}
                  sortDirValue={sceneSortDir}
                  onSortDirChange={(value) => {
                    setSceneSortDir(value);
                    setScenePage(1);
                  }}
                />
                <PaginationControls
                  label="Scenes"
                  page={scenes.page}
                  pageSize={scenes.page_size}
                  total={scenes.total}
                  totalPages={scenes.total_pages}
                  onPrevious={() => setScenePage((value) => Math.max(1, value - 1))}
                  onNext={() => setScenePage((value) => Math.min(scenes.total_pages, value + 1))}
                  onPageSizeChange={(value) => {
                    setScenePageSize(value);
                    setScenePage(1);
                  }}
                />
                <DataTable
                  columns={[
                    { key: "source", label: "Source" },
                    { key: "scene_id", label: "Scene ID" },
                    {
                      key: "aoi_code",
                      label: "AOI",
                      render: (row) => {
                        const item = row as SceneProvenanceItem;
                        if (item.aoi_id == null) {
                          return String(item.aoi_code ?? "n/a");
                        }
                        return (
                          <a href={buildAoiContextHref({ aoiId: item.aoi_id, runId: run.id, focus: "aoi", sceneId: item.scene_id, returnTo: returnToHref })} className="font-medium text-sky-700 hover:underline">
                            {item.aoi_code ?? `AOI #${item.aoi_id}`}
                          </a>
                        );
                      },
                    },
                    { key: "acquired_at", label: "Acquired" },
                    { key: "cloud_score", label: "Cloud", render: (row) => formatMetric((row as SceneProvenanceItem).cloud_score) },
                    { key: "spatial_resolution_m", label: "Resolution (m)", render: (row) => String((row as SceneProvenanceItem).spatial_resolution_m ?? "n/a") },
                    { key: "processing_status", label: "Processing" },
                    { key: "provenance_status", label: "Trace", render: (row) => String((row as SceneProvenanceItem).provenance_status ?? "linked") },
                    {
                      key: "id",
                      label: "Actions",
                      render: (row) => {
                        const item = row as SceneProvenanceItem;
                        if (item.aoi_id == null) {
                          return <span className="text-xs text-slate-400">n/a</span>;
                        }
                        return (
                          <div className="flex flex-wrap items-center gap-3">
                            <button
                              type="button"
                              onClick={() => setPreviewScene(item)}
                              className="text-xs font-medium text-slate-700 hover:underline"
                            >
                              Preview
                            </button>
                            <a
                              href={buildAoiContextHref({ aoiId: item.aoi_id, runId: run.id, focus: "observations", sceneId: item.scene_id, returnTo: returnToHref, source: item.source, observationDate: item.acquired_at })}
                              className="text-xs font-medium text-sky-700 hover:underline"
                            >
                              Observation history
                            </a>
                          </div>
                        );
                      },
                    },
                  ]}
                  rows={scenes.rows as unknown as Record<string, unknown>[]}
                />
              </>
            )
          ) : null}
        </div>
      </SectionShell>

      <SectionShell title="Feature provenance">
        <div className="mb-3 flex flex-wrap items-center justify-end gap-2">
          <button
            type="button"
            onClick={() => {
              setFeaturePage(DEFAULT_DRILLDOWN_URL_STATE.featurePage);
              setFeaturePageSize(DEFAULT_DRILLDOWN_URL_STATE.featurePageSize);
              setFeatureSearch(DEFAULT_DRILLDOWN_URL_STATE.featureSearch);
              setFeatureSource(DEFAULT_DRILLDOWN_URL_STATE.featureSource);
              setFeatureAoiCode(DEFAULT_DRILLDOWN_URL_STATE.featureAoiCode);
              setFeatureSortBy(DEFAULT_DRILLDOWN_URL_STATE.featureSortBy);
              setFeatureSortDir(DEFAULT_DRILLDOWN_URL_STATE.featureSortDir);
            }}
            disabled={!hasActiveFeatureFilters}
            className="rounded border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Reset feature filters
          </button>
          <button
            type="button"
            onClick={() => {
              void handleExportFeatures();
            }}
            disabled={isExportingFeatures}
            className="rounded border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isExportingFeatures ? "Exporting features..." : "Export feature CSV"}
          </button>
        </div>
        <div data-testid="run-features-table">
          {featureRows.isLoading && !features ? <LoadingState label="Loading feature provenance..." /> : null}
          {featureRows.error ? <ErrorState message="Failed to load feature provenance" /> : null}
          {features ? (
            features.rows.length === 0 ? (
              <>
                <TableControlBar
                  searchLabel="Feature search"
                  searchValue={featureSearch}
                  onSearchChange={(value) => {
                    setFeatureSearch(value);
                    setFeaturePage(1);
                  }}
                  sourceValue={featureSource}
                  sourceOptions={run.provenance_summary.feature_sources ?? []}
                  onSourceChange={(value) => {
                    setFeatureSource(value);
                    setFeaturePage(1);
                  }}
                  aoiCodeValue={featureAoiCode}
                  onAoiCodeChange={(value) => {
                    setFeatureAoiCode(value);
                    setFeaturePage(1);
                  }}
                  sortByValue={featureSortBy}
                  sortByLabel="Feature ordering"
                  sortOptions={[
                    { value: "observation_date", label: "Observation date" },
                    { value: "source", label: "Source" },
                    { value: "aoi_code", label: "AOI code" },
                    { value: "scene_id", label: "Scene ID" },
                    { value: "observation_confidence_score", label: "Confidence" },
                    { value: "crop_activity_score", label: "Crop score" },
                    { value: "vegetation_vigor_score", label: "Vigor score" },
                    { value: "cloud_score", label: "Cloud score" },
                  ]}
                  onSortByChange={(value) => {
                    setFeatureSortBy(value);
                    setFeaturePage(1);
                  }}
                  sortDirValue={featureSortDir}
                  onSortDirChange={(value) => {
                    setFeatureSortDir(value);
                    setFeaturePage(1);
                  }}
                />
                <EmptyState title="No features found" description="No feature rows match the current filters for this run." />
                <div className="mt-3 flex flex-wrap gap-3">
                  <button
                    type="button"
                    onClick={() => setPreviewFeature(fallbackFeaturePreview)}
                    className="rounded border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
                  >
                    Preview
                  </button>
                </div>
              </>
            ) : (
              <>
                <TableControlBar
                  searchLabel="Feature search"
                  searchValue={featureSearch}
                  onSearchChange={(value) => {
                    setFeatureSearch(value);
                    setFeaturePage(1);
                  }}
                  sourceValue={featureSource}
                  sourceOptions={run.provenance_summary.feature_sources ?? []}
                  onSourceChange={(value) => {
                    setFeatureSource(value);
                    setFeaturePage(1);
                  }}
                  aoiCodeValue={featureAoiCode}
                  onAoiCodeChange={(value) => {
                    setFeatureAoiCode(value);
                    setFeaturePage(1);
                  }}
                  sortByValue={featureSortBy}
                  sortByLabel="Feature ordering"
                  sortOptions={[
                    { value: "observation_date", label: "Observation date" },
                    { value: "source", label: "Source" },
                    { value: "aoi_code", label: "AOI code" },
                    { value: "scene_id", label: "Scene ID" },
                    { value: "observation_confidence_score", label: "Confidence" },
                    { value: "crop_activity_score", label: "Crop score" },
                    { value: "vegetation_vigor_score", label: "Vigor score" },
                    { value: "cloud_score", label: "Cloud score" },
                  ]}
                  onSortByChange={(value) => {
                    setFeatureSortBy(value);
                    setFeaturePage(1);
                  }}
                  sortDirValue={featureSortDir}
                  onSortDirChange={(value) => {
                    setFeatureSortDir(value);
                    setFeaturePage(1);
                  }}
                />
                <PaginationControls
                  label="Features"
                  page={features.page}
                  pageSize={features.page_size}
                  total={features.total}
                  totalPages={features.total_pages}
                  onPrevious={() => setFeaturePage((value) => Math.max(1, value - 1))}
                  onNext={() => setFeaturePage((value) => Math.min(features.total_pages, value + 1))}
                  onPageSizeChange={(value) => {
                    setFeaturePageSize(value);
                    setFeaturePage(1);
                  }}
                />
                <DataTable
                  columns={[
                    { key: "source", label: "Source" },
                    {
                      key: "observation_date",
                      label: "Observation Date",
                      render: (row) => {
                        const item = row as FeatureProvenanceItem;
                        if (item.aoi_id == null) {
                          return String(item.observation_date ?? "n/a");
                        }
                        return (
                          <a
                            href={buildAoiContextHref({ aoiId: item.aoi_id, runId: run.id, focus: "observations", sceneId: item.scene_id, returnTo: returnToHref, source: item.source, observationDate: item.observation_date })}
                            className="font-medium text-sky-700 hover:underline"
                          >
                            {item.observation_date ?? "n/a"}
                          </a>
                        );
                      },
                    },
                    {
                      key: "aoi_code",
                      label: "AOI",
                      render: (row) => {
                        const item = row as FeatureProvenanceItem;
                        if (item.aoi_id == null) {
                          return String(item.aoi_code ?? "n/a");
                        }
                        return (
                          <a href={buildAoiContextHref({ aoiId: item.aoi_id, runId: run.id, focus: "aoi", sceneId: item.scene_id, returnTo: returnToHref })} className="font-medium text-sky-700 hover:underline">
                            {item.aoi_code ?? `AOI #${item.aoi_id}`}
                          </a>
                        );
                      },
                    },
                    { key: "scene_id", label: "Scene ID", render: (row) => String((row as FeatureProvenanceItem).scene_id ?? "n/a") },
                    { key: "observation_confidence_score", label: "Confidence", render: (row) => formatMetric((row as FeatureProvenanceItem).observation_confidence_score) },
                    { key: "crop_activity_score", label: "Crop", render: (row) => formatMetric((row as FeatureProvenanceItem).crop_activity_score) },
                    { key: "vegetation_vigor_score", label: "Vigor", render: (row) => formatMetric((row as FeatureProvenanceItem).vegetation_vigor_score) },
                    { key: "cloud_score", label: "Cloud", render: (row) => formatMetric((row as FeatureProvenanceItem).cloud_score) },
                    {
                      key: "id",
                      label: "Actions",
                      render: (row) => {
                        const item = row as FeatureProvenanceItem;
                        if (item.aoi_id == null) {
                          return <span className="text-xs text-slate-400">n/a</span>;
                        }
                        return (
                          <div className="flex flex-wrap items-center gap-3">
                            <button
                              type="button"
                              onClick={() => setPreviewFeature(item)}
                              className="text-xs font-medium text-slate-700 hover:underline"
                            >
                              Preview
                            </button>
                            <a
                              href={buildAoiContextHref({ aoiId: item.aoi_id, runId: run.id, focus: "timeline", sceneId: item.scene_id, returnTo: returnToHref, source: item.source, observationDate: item.observation_date })}
                              className="text-xs font-medium text-sky-700 hover:underline"
                            >
                              Open timeline
                            </a>
                          </div>
                        );
                      },
                    },
                  ]}
                  rows={features.rows as unknown as Record<string, unknown>[]}
                />
              </>
            )
          ) : null}
        </div>
      </SectionShell>

      <GeospatialRunAdvancedPanel token={token} runId={run.id} />

      {previewScene ? (
        <div className="fixed inset-0 z-40 flex justify-end bg-slate-900/40">
          <div className="h-full w-full max-w-xl overflow-y-auto bg-white p-6 shadow-2xl" data-testid="scene-preview-drawer">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-slate-900">Scene preview</h2>
                <p className="mt-1 text-sm text-slate-500">Quick provenance context for {previewScene.scene_id}</p>
              </div>
              <button type="button" onClick={() => setPreviewScene(null)} className="rounded border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50">
                Close
              </button>
            </div>

            <div className="mt-6 grid gap-4 sm:grid-cols-2">
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <div className="text-xs uppercase tracking-wide text-slate-500">Source</div>
                <div className="mt-1 text-sm font-medium text-slate-800">{previewScene.source}</div>
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <div className="text-xs uppercase tracking-wide text-slate-500">AOI</div>
                <div className="mt-1 text-sm font-medium text-slate-800">{previewScene.aoi_code ?? previewScene.aoi_name ?? "n/a"}</div>
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <div className="text-xs uppercase tracking-wide text-slate-500">Acquired</div>
                <div className="mt-1 text-sm font-medium text-slate-800">{previewScene.acquired_at ?? "n/a"}</div>
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <div className="text-xs uppercase tracking-wide text-slate-500">Processing</div>
                <div className="mt-1 text-sm font-medium text-slate-800">{previewScene.processing_status}</div>
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <div className="text-xs uppercase tracking-wide text-slate-500">Cloud score</div>
                <div className="mt-1 text-sm font-medium text-slate-800">{formatMetric(previewScene.cloud_score)}</div>
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <div className="text-xs uppercase tracking-wide text-slate-500">Resolution</div>
                <div className="mt-1 text-sm font-medium text-slate-800">{previewScene.spatial_resolution_m ?? "n/a"} m</div>
              </div>
            </div>

            <div className="mt-6 rounded-lg border border-slate-200 p-4">
              <div className="text-sm font-semibold text-slate-800">Linked feature sample</div>
              {previewSceneFeatures.length === 0 ? (
                <p className="mt-2 text-sm text-slate-500">No linked feature rows were loaded for this scene.</p>
              ) : (
                <div className="mt-3 space-y-3">
                  {previewSceneFeatures.map((feature) => (
                    <div key={feature.id} className="rounded border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
                      <div className="font-medium text-slate-800">{feature.observation_date ?? "n/a"}</div>
                      <div className="mt-1">Confidence: {formatMetric(feature.observation_confidence_score)} · Crop: {formatMetric(feature.crop_activity_score)} · Vigor: {formatMetric(feature.vegetation_vigor_score)}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="mt-6 rounded-lg border border-slate-200 p-4">
              <div className="text-sm font-semibold text-slate-800">Scene provenance chain viewer</div>
              {sceneProvenanceChain.isLoading ? (
                <p className="mt-2 text-sm text-slate-500">Loading provenance chain...</p>
              ) : null}
              {sceneProvenanceChain.error ? (
                <p className="mt-2 text-sm text-rose-600">Failed to load provenance chain.</p>
              ) : null}
              {sceneProvenanceChain.data ? (
                <>
                  <p className="mt-2 text-sm text-slate-500">
                    Completed steps: {sceneProvenanceChain.data.completed_steps}/{sceneProvenanceChain.data.total_steps} · latest step: {sceneProvenanceChain.data.latest_step ?? "n/a"}
                  </p>
                  <div className="mt-3 space-y-2">
                    {sceneProvenanceChain.data.timeline.map((entry) => (
                      <div key={`${entry.step}-${entry.timestamp ?? "na"}`} className="rounded border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
                        <div className="font-medium text-slate-800">{entry.step}</div>
                        <div className="mt-1">Status: {entry.status} · Timestamp: {entry.timestamp ?? "n/a"}</div>
                      </div>
                    ))}
                  </div>
                </>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}

      {previewFeature ? (
        <div className="fixed inset-0 z-40 flex justify-end bg-slate-900/40">
          <div className="h-full w-full max-w-xl overflow-y-auto bg-white p-6 shadow-2xl" data-testid="feature-preview-drawer">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-slate-900">Feature preview</h2>
                <p className="mt-1 text-sm text-slate-500">Quick analytical context for {previewFeature.observation_date ?? "n/a"}</p>
              </div>
              <button type="button" onClick={() => setPreviewFeature(null)} className="rounded border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50">
                Close
              </button>
            </div>

            <div className="mt-6 grid gap-4 sm:grid-cols-2">
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <div className="text-xs uppercase tracking-wide text-slate-500">Source</div>
                <div className="mt-1 text-sm font-medium text-slate-800">{previewFeature.source}</div>
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <div className="text-xs uppercase tracking-wide text-slate-500">AOI</div>
                <div className="mt-1 text-sm font-medium text-slate-800">{previewFeature.aoi_code ?? previewFeature.aoi_name ?? "n/a"}</div>
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <div className="text-xs uppercase tracking-wide text-slate-500">Scene ID</div>
                <div className="mt-1 text-sm font-medium text-slate-800">{previewFeature.scene_id ?? "n/a"}</div>
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <div className="text-xs uppercase tracking-wide text-slate-500">Observed</div>
                <div className="mt-1 text-sm font-medium text-slate-800">{previewFeature.observation_date ?? "n/a"}</div>
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <div className="text-xs uppercase tracking-wide text-slate-500">Confidence</div>
                <div className="mt-1 text-sm font-medium text-slate-800">{formatMetric(previewFeature.observation_confidence_score)}</div>
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <div className="text-xs uppercase tracking-wide text-slate-500">Cloud</div>
                <div className="mt-1 text-sm font-medium text-slate-800">{formatMetric(previewFeature.cloud_score)}</div>
              </div>
            </div>

            <div className="mt-6 rounded-lg border border-slate-200 p-4">
              <div className="text-sm font-semibold text-slate-800">Feature metrics</div>
              <div className="mt-3 grid gap-3 sm:grid-cols-3">
                <div className="rounded border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
                  <div className="text-xs uppercase tracking-wide text-slate-500">Crop score</div>
                  <div className="mt-1 font-medium text-slate-800">{formatMetric(previewFeature.crop_activity_score)}</div>
                </div>
                <div className="rounded border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
                  <div className="text-xs uppercase tracking-wide text-slate-500">Vigor score</div>
                  <div className="mt-1 font-medium text-slate-800">{formatMetric(previewFeature.vegetation_vigor_score)}</div>
                </div>
                <div className="rounded border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
                  <div className="text-xs uppercase tracking-wide text-slate-500">Reporting month</div>
                  <div className="mt-1 font-medium text-slate-800">{previewFeature.reporting_month ?? "n/a"}</div>
                </div>
              </div>
            </div>

            <div className="mt-6 rounded-lg border border-slate-200 p-4">
              <div className="text-sm font-semibold text-slate-800">Linked scene snapshot</div>
              {previewFeatureScene ? (
                <div className="mt-3 grid gap-3 sm:grid-cols-2 text-sm text-slate-700">
                  <div>
                    <div className="text-xs uppercase tracking-wide text-slate-500">Acquired</div>
                    <div className="mt-1">{previewFeatureScene.acquired_at ?? "n/a"}</div>
                  </div>
                  <div>
                    <div className="text-xs uppercase tracking-wide text-slate-500">Processing</div>
                    <div className="mt-1">{previewFeatureScene.processing_status}</div>
                  </div>
                  <div>
                    <div className="text-xs uppercase tracking-wide text-slate-500">Resolution</div>
                    <div className="mt-1">{previewFeatureScene.spatial_resolution_m ?? "n/a"} m</div>
                  </div>
                  <div>
                    <div className="text-xs uppercase tracking-wide text-slate-500">Provenance</div>
                    <div className="mt-1">{previewFeatureScene.provenance_status ?? "linked"}</div>
                  </div>
                </div>
              ) : (
                <p className="mt-2 text-sm text-slate-500">No linked scene snapshot was loaded for this feature.</p>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
