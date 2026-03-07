"use client";

import { apiFetch } from "@phil-onion-watch/api-client";
import { DataTable, EmptyState, ErrorState, LoadingState, PageHeader, SectionShell, StatCard } from "@phil-onion-watch/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { GeospatialPolygonEditor } from "../../../../../components/geospatial-polygon-editor";
import { GeospatialAoiAdvancedPanel } from "../../../../../components/geospatial-aoi-advanced-panel";
import { useAuth } from "../../../../providers";
import {
  LonLatPoint,
  defaultPolygonVertices,
  polygonGeojsonToVertices,
  validatePolygonVertices,
  verticesToPolygonGeojson,
} from "../../../../../lib/geospatial";

type AoiListItem = {
  id: number;
  code: string;
  name: string;
  description: string | null;
  scope_type: string;
  municipality_id: number | null;
  warehouse_id: number | null;
  market_id: number | null;
  srid: number;
  bbox: {
    min_lng: number | null;
    min_lat: number | null;
    max_lng: number | null;
    max_lat: number | null;
  };
  centroid: { lng: number | null; lat: number | null };
  source: string;
  is_active: boolean;
};

type AoiDto = {
  id: number;
  code: string;
  name: string;
  description: string | null;
  scope_type: string;
  municipality_id: number | null;
  warehouse_id: number | null;
  market_id: number | null;
  srid: number;
  boundary_geojson: Record<string, unknown>;
  boundary_wkt: string | null;
  bbox_min_lng: number | null;
  bbox_min_lat: number | null;
  bbox_max_lng: number | null;
  bbox_max_lat: number | null;
  centroid_lng: number | null;
  centroid_lat: number | null;
  source: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

type AoiVersionDto = {
  id: number;
  aoi_id: number;
  version: number;
  change_type: string;
  boundary_geojson: Record<string, unknown>;
  boundary_wkt: string | null;
  changed_by: number | null;
  change_reason: string | null;
  changed_at: string;
};

type AoiDetail = {
  id: number;
  code: string;
  name: string;
  description: string | null;
  scope_type: string;
  municipality_id: number | null;
  warehouse_id: number | null;
  market_id: number | null;
  srid: number;
  boundary_geojson: Record<string, unknown>;
  boundary_wkt: string | null;
  bbox: {
    min_lng: number | null;
    min_lat: number | null;
    max_lng: number | null;
    max_lat: number | null;
  };
  centroid: { lng: number | null; lat: number | null };
  source: string;
  is_active: boolean;
};

type ObservationItem = {
  id: number;
  aoi_id: number;
  source: string;
  observation_date: string;
  reporting_month: string | null;
  cloud_score: number | null;
  change_score: number | null;
  vegetation_vigor_score: number | null;
  crop_activity_score: number | null;
  observation_confidence_score: number | null;
  features: Record<string, unknown>;
  quality: Record<string, unknown>;
};

type TimelinePoint = {
  observation_date: string;
  source: string;
  crop_activity_score: number | null;
  vegetation_vigor_score: number | null;
  observation_confidence_score: number | null;
  cloud_score: number | null;
};

type TimelineResponse = {
  aoi_id: number;
  count: number;
  observations: TimelinePoint[];
};

type MapLayer = {
  key: string;
  label: string;
  description: string;
};

type MapLayerResponse = {
  layers: MapLayer[];
};

type GeospatialOverview = {
  total_aois: number;
  total_features: number;
  latest_observation_date: string | null;
};

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

function parseOptionalNumber(value: string): number | undefined {
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  const num = Number(trimmed);
  if (!Number.isFinite(num)) {
    throw new Error("Expected a number.");
  }
  return num;
}

function formatMetric(value: number | null | undefined) {
  return value == null ? "n/a" : Number(value).toFixed(3);
}

function averageMetric(rows: ObservationItem[], key: keyof Pick<ObservationItem, "crop_activity_score" | "vegetation_vigor_score" | "observation_confidence_score">) {
  const values = rows.map((row) => row[key]).filter((value): value is number => typeof value === "number");
  if (values.length === 0) {
    return "n/a";
  }
  return (values.reduce((sum, value) => sum + value, 0) / values.length).toFixed(3);
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
    return { text: error, tone: "error" as const };
  }

  if (run.status === "cancel_requested") {
    return { text: "Cancellation requested", tone: "neutral" as const };
  }

  if (run.status === "cancelled") {
    return { text: "Cancelled", tone: "neutral" as const };
  }

  const discovery = (results.scene_discovery as Record<string, unknown> | undefined) ?? null;
  if (discovery) {
    const inserted = Number(discovery.inserted ?? 0);
    const discovered = Number(discovery.discovered ?? 0);
    return {
      text: `${discovered} discovered · ${inserted} inserted`,
      tone: inserted > 0 ? ("success" as const) : ("neutral" as const),
    };
  }

  const materialized = (results.materialized as Record<string, unknown> | undefined) ?? null;
  if (materialized) {
    const inserted = Number(materialized.features_inserted ?? 0);
    const updated = Number(materialized.features_updated ?? 0);
    return {
      text: `${inserted} inserted · ${updated} updated`,
      tone: inserted + updated > 0 ? ("success" as const) : ("neutral" as const),
    };
  }

  return { text: run.status === "queued" || run.status === "running" ? "In progress" : "No summary", tone: "neutral" as const };
}

function resultToneClass(tone: "success" | "error" | "neutral") {
  switch (tone) {
    case "success":
      return "bg-emerald-50 text-emerald-700";
    case "error":
      return "bg-rose-50 text-rose-700";
    default:
      return "bg-slate-50 text-slate-700";
  }
}

export default function GeospatialAOIsPage() {
  const { token, user } = useAuth();
  const queryClient = useQueryClient();

  const [showInactive, setShowInactive] = useState(false);
  const [listMunicipalityId, setListMunicipalityId] = useState("");
  const [listWarehouseId, setListWarehouseId] = useState("");
  const [listMarketId, setListMarketId] = useState("");
  const [listTag, setListTag] = useState("");
  const [listSearch, setListSearch] = useState("");
  const [listWatchlistOnly, setListWatchlistOnly] = useState(false);
  const [listFavoritesOnly, setListFavoritesOnly] = useState(false);
  const [selectedAoiId, setSelectedAoiId] = useState<number | null>(null);
  const [versionsAoiId, setVersionsAoiId] = useState<number | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);

  const [createCode, setCreateCode] = useState("");
  const [createName, setCreateName] = useState("");
  const [createDescription, setCreateDescription] = useState("");
  const [createScopeType, setCreateScopeType] = useState("custom");
  const [createMunicipalityId, setCreateMunicipalityId] = useState("");
  const [createWarehouseId, setCreateWarehouseId] = useState("");
  const [createMarketId, setCreateMarketId] = useState("");
  const [createSource, setCreateSource] = useState("manual");
  const [createChangeReason, setCreateChangeReason] = useState("Created via dashboard");
  const [createVertices, setCreateVertices] = useState<LonLatPoint[]>(() => defaultPolygonVertices());
  const [createServerError, setCreateServerError] = useState<string | null>(null);

  const [editAoiId, setEditAoiId] = useState<number | null>(null);
  const [editCode, setEditCode] = useState("");
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editScopeType, setEditScopeType] = useState("");
  const [editMunicipalityId, setEditMunicipalityId] = useState("");
  const [editWarehouseId, setEditWarehouseId] = useState("");
  const [editMarketId, setEditMarketId] = useState("");
  const [editSource, setEditSource] = useState("");
  const [editIsActive, setEditIsActive] = useState(true);
  const [editChangeReason, setEditChangeReason] = useState("Updated via dashboard");
  const [editVertices, setEditVertices] = useState<LonLatPoint[]>([]);
  const [editServerError, setEditServerError] = useState<string | null>(null);

  const [pipelineBackend, setPipelineBackend] = useState("gee");
  const [pipelineSourcesText, setPipelineSourcesText] = useState("sentinel-2,sentinel-1");
  const [pipelineNotes, setPipelineNotes] = useState("Queued via dashboard");
  const [pipelineScopeToSelectedAoi, setPipelineScopeToSelectedAoi] = useState(true);
  const [pipelineError, setPipelineError] = useState<string | null>(null);
  const [deepLinkContext, setDeepLinkContext] = useState({
    requestedAoiId: Number.NaN,
    requestedRunId: Number.NaN,
    requestedFocus: "",
    requestedSceneId: "",
    requestedReturnTo: "",
    requestedSource: "",
    requestedObservationDate: "",
  });
  const [layerOpacity, setLayerOpacity] = useState(70);
  const [showLegend, setShowLegend] = useState(true);
  const [mapFullscreen, setMapFullscreen] = useState(false);
  const [basemap, setBasemap] = useState("OpenStreetMap");
  const [overlaySourceFilter, setOverlaySourceFilter] = useState<string>("all");
  const [confidenceFloor, setConfidenceFloor] = useState(0);
  const [anomalyThreshold, setAnomalyThreshold] = useState(0.15);
  const [timelineWindow, setTimelineWindow] = useState(6);
  const [clusterMode, setClusterMode] = useState(true);
  const [animateTimeline, setAnimateTimeline] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const params = new URLSearchParams(window.location.search);
    setDeepLinkContext({
      requestedAoiId: Number(params.get("aoiId") ?? ""),
      requestedRunId: Number(params.get("runId") ?? ""),
      requestedFocus: params.get("focus") ?? "",
      requestedSceneId: params.get("sceneId") ?? "",
      requestedReturnTo: params.get("returnTo") ?? "",
      requestedSource: params.get("source") ?? "",
      requestedObservationDate: params.get("observationDate") ?? "",
    });
  }, []);

  const { requestedAoiId, requestedRunId, requestedFocus, requestedSceneId, requestedReturnTo, requestedSource, requestedObservationDate } = deepLinkContext;

  const canManageAOIs = useMemo(() => {
    const roles = user?.roles ?? [];
    return roles.includes("super_admin") || roles.includes("provincial_admin");
  }, [user]);

  const createValidationErrors = useMemo(() => validatePolygonVertices(createVertices), [createVertices]);
  const editValidationErrors = useMemo(() => validatePolygonVertices(editVertices), [editVertices]);

  const aois = useQuery({
    queryKey: [
      "geospatial-aois",
      token,
      showInactive,
      listMunicipalityId,
      listWarehouseId,
      listMarketId,
      listTag,
      listSearch,
      listWatchlistOnly,
      listFavoritesOnly,
    ],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (listMunicipalityId.trim()) params.set("municipality_id", listMunicipalityId.trim());
      if (listWarehouseId.trim()) params.set("warehouse_id", listWarehouseId.trim());
      if (listMarketId.trim()) params.set("market_id", listMarketId.trim());
      if (listTag.trim()) params.set("tag", listTag.trim());
      if (listSearch.trim()) params.set("search", listSearch.trim());
      if (listWatchlistOnly) params.set("watchlist_only", "true");
      if (listFavoritesOnly) params.set("favorites_only", "true");

      if (!showInactive) {
        const query = params.toString();
        return apiFetch<AoiListItem[]>(`/api/v1/geospatial/aois${query ? `?${query}` : ""}`, { token });
      }

      const activeParams = new URLSearchParams(params);
      activeParams.set("is_active", "true");
      const inactiveParams = new URLSearchParams(params);
      inactiveParams.set("is_active", "false");
      const [active, inactive] = await Promise.all([
        apiFetch<AoiListItem[]>(`/api/v1/geospatial/aois?${activeParams.toString()}`, { token }),
        apiFetch<AoiListItem[]>(`/api/v1/geospatial/aois?${inactiveParams.toString()}`, { token }),
      ]);
      const merged = [...(active ?? []), ...(inactive ?? [])];
      merged.sort((a, b) => String(a.name ?? "").localeCompare(String(b.name ?? "")));
      return merged;
    },
    enabled: !!token,
  });

  const overview = useQuery({
    queryKey: ["geospatial-provincial-overview", token],
    queryFn: () => apiFetch<GeospatialOverview>("/api/v1/geospatial/dashboard/provincial", { token }),
    enabled: !!token,
  });

  const layers = useQuery({
    queryKey: ["geospatial-map-layers", token],
    queryFn: () => apiFetch<MapLayerResponse>("/api/v1/geospatial/map/layers", { token }),
    enabled: !!token,
  });

  const pipelineRuns = useQuery({
    queryKey: ["geospatial-pipeline-runs", token],
    queryFn: () => apiFetch<PipelineRunItem[]>("/api/v1/geospatial/runs?limit=12", { token }),
    enabled: !!token,
    refetchInterval: (query) => {
      const rows = (query.state.data as PipelineRunItem[] | undefined) ?? [];
      return rows.some((row) => row.status === "queued" || row.status === "running" || row.status === "cancel_requested") ? 4000 : false;
    },
  });

  const selectedRunDetail = useQuery({
    queryKey: ["geospatial-pipeline-run-detail", token, selectedRunId],
    queryFn: () => apiFetch<PipelineRunDetail>(`/api/v1/geospatial/runs/${selectedRunId}`, { token }),
    enabled: !!token && typeof selectedRunId === "number",
    refetchInterval: (query) => {
      const row = query.state.data as PipelineRunDetail | undefined;
      return row != null && (row.status === "queued" || row.status === "running" || row.status === "cancel_requested") ? 4000 : false;
    },
  });

  const versions = useQuery({
    queryKey: ["geospatial-aoi-versions", token, versionsAoiId],
    queryFn: () => apiFetch<AoiVersionDto[]>(`/api/v1/geospatial/aois/${versionsAoiId}/versions`, { token }),
    enabled: !!token && typeof versionsAoiId === "number",
  });

  const observations = useQuery({
    queryKey: ["geospatial-observations", token, selectedAoiId],
    queryFn: () => apiFetch<ObservationItem[]>(`/api/v1/geospatial/observations?aoi_id=${selectedAoiId}&limit=12`, { token }),
    enabled: !!token && typeof selectedAoiId === "number",
  });

  const timeline = useQuery({
    queryKey: ["geospatial-timeline", token, selectedAoiId],
    queryFn: () => apiFetch<TimelineResponse>(`/api/v1/geospatial/observations/${selectedAoiId}/timeline?limit=30`, { token }),
    enabled: !!token && typeof selectedAoiId === "number",
  });

  useEffect(() => {
    const rows = aois.data ?? [];
    if (rows.length === 0) {
      if (selectedAoiId != null) {
        setSelectedAoiId(null);
      }
      return;
    }
    if (Number.isFinite(requestedAoiId) && requestedAoiId > 0 && rows.some((row) => row.id === requestedAoiId) && selectedAoiId !== requestedAoiId) {
      setSelectedAoiId(requestedAoiId);
      return;
    }
    if (selectedAoiId == null || !rows.some((row) => row.id === selectedAoiId)) {
      setSelectedAoiId(rows[0].id);
    }
  }, [aois.data, requestedAoiId, selectedAoiId]);

  useEffect(() => {
    const rows = pipelineRuns.data ?? [];
    if (rows.length === 0) {
      if (selectedRunId != null) {
        setSelectedRunId(null);
      }
      return;
    }
    if (Number.isFinite(requestedRunId) && requestedRunId > 0 && rows.some((row) => row.id === requestedRunId) && selectedRunId !== requestedRunId) {
      setSelectedRunId(requestedRunId);
      return;
    }
    if (selectedRunId == null || !rows.some((row) => row.id === selectedRunId)) {
      setSelectedRunId(rows[0].id);
    }
  }, [pipelineRuns.data, requestedRunId, selectedRunId]);

  useEffect(() => {
    if (!selectedAoiId || !requestedFocus) {
      return;
    }
    const targetId = requestedFocus === "observations" ? "aoi-observations-section" : requestedFocus === "timeline" ? "aoi-timeline-section" : "selected-aoi-insights";
    const target = document.getElementById(targetId);
    if (!target) {
      return;
    }
    window.requestAnimationFrame(() => {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }, [requestedFocus, selectedAoiId]);

  async function loadAoiForEdit(aoiId: number) {
    if (!token) return;
    try {
      const detail = await apiFetch<AoiDetail>(`/api/v1/geospatial/aois/${aoiId}`, { token });
      const vertices = polygonGeojsonToVertices(detail.boundary_geojson);
      setEditAoiId(detail.id);
      setEditCode(detail.code ?? "");
      setEditName(detail.name ?? "");
      setEditDescription(detail.description ?? "");
      setEditScopeType(detail.scope_type ?? "");
      setEditMunicipalityId(detail.municipality_id == null ? "" : String(detail.municipality_id));
      setEditWarehouseId(detail.warehouse_id == null ? "" : String(detail.warehouse_id));
      setEditMarketId(detail.market_id == null ? "" : String(detail.market_id));
      setEditSource(detail.source ?? "");
      setEditIsActive(Boolean(detail.is_active));
      setEditVertices(vertices);
      setEditServerError(null);
      setSelectedAoiId(detail.id);
    } catch (error) {
      setEditServerError(error instanceof Error ? error.message : "Failed to load AOI details.");
    }
  }

  const createMutation = useMutation({
    mutationFn: async () => {
      if (!createCode.trim()) {
        throw new Error("AOI code is required.");
      }
      if (!createName.trim()) {
        throw new Error("AOI name is required.");
      }
      if (createValidationErrors.length > 0) {
        throw new Error(createValidationErrors[0]);
      }
      const municipalityId = parseOptionalNumber(createMunicipalityId);
      const warehouseId = parseOptionalNumber(createWarehouseId);
      const marketId = parseOptionalNumber(createMarketId);
      return apiFetch<AoiDto>("/api/v1/geospatial/aois", {
        token,
        method: "POST",
        body: {
          code: createCode.trim(),
          name: createName.trim(),
          description: createDescription.trim() ? createDescription.trim() : null,
          scope_type: createScopeType.trim() ? createScopeType.trim() : "custom",
          municipality_id: municipalityId ?? null,
          warehouse_id: warehouseId ?? null,
          market_id: marketId ?? null,
          boundary_geojson: verticesToPolygonGeojson(createVertices),
          boundary_wkt: null,
          source: createSource.trim() ? createSource.trim() : "manual",
          change_reason: createChangeReason.trim() ? createChangeReason.trim() : null,
        },
      });
    },
    onSuccess: async (created) => {
      setCreateServerError(null);
      setCreateCode("");
      setCreateName("");
      setCreateDescription("");
      setCreateScopeType("custom");
      setCreateMunicipalityId("");
      setCreateWarehouseId("");
      setCreateMarketId("");
      setCreateSource("manual");
      setCreateChangeReason("Created via dashboard");
      setCreateVertices(defaultPolygonVertices());
      setSelectedAoiId(created.id);
      await queryClient.invalidateQueries({ queryKey: ["geospatial-aois", token] });
    },
    onError: (error: unknown) => setCreateServerError(error instanceof Error ? error.message : "Failed to create AOI."),
  });

  const updateMutation = useMutation({
    mutationFn: async () => {
      if (!editAoiId) {
        throw new Error("Select an AOI to edit.");
      }
      if (!editCode.trim()) {
        throw new Error("AOI code is required.");
      }
      if (!editName.trim()) {
        throw new Error("AOI name is required.");
      }
      if (editValidationErrors.length > 0) {
        throw new Error(editValidationErrors[0]);
      }
      const municipalityId = parseOptionalNumber(editMunicipalityId);
      const warehouseId = parseOptionalNumber(editWarehouseId);
      const marketId = parseOptionalNumber(editMarketId);
      return apiFetch<AoiDto>(`/api/v1/geospatial/aois/${editAoiId}`, {
        token,
        method: "PUT",
        body: {
          code: editCode.trim(),
          name: editName.trim(),
          description: editDescription.trim() ? editDescription.trim() : null,
          scope_type: editScopeType.trim() ? editScopeType.trim() : undefined,
          municipality_id: municipalityId ?? null,
          warehouse_id: warehouseId ?? null,
          market_id: marketId ?? null,
          boundary_geojson: verticesToPolygonGeojson(editVertices),
          source: editSource.trim() ? editSource.trim() : undefined,
          is_active: editIsActive,
          change_reason: editChangeReason.trim() ? editChangeReason.trim() : null,
        },
      });
    },
    onSuccess: async (updated) => {
      setEditServerError(null);
      setSelectedAoiId(updated.id);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["geospatial-aois", token] }),
        queryClient.invalidateQueries({ queryKey: ["geospatial-observations", token, updated.id] }),
        queryClient.invalidateQueries({ queryKey: ["geospatial-timeline", token, updated.id] }),
        queryClient.invalidateQueries({ queryKey: ["geospatial-aoi-versions", token, versionsAoiId] }),
      ]);
    },
    onError: (error: unknown) => setEditServerError(error instanceof Error ? error.message : "Failed to update AOI."),
  });

  const deactivateMutation = useMutation({
    mutationFn: async (aoiId: number) => {
      return apiFetch<AoiDto>(`/api/v1/geospatial/aois/${aoiId}?change_reason=Deactivated%20via%20dashboard`, {
        token,
        method: "DELETE",
      });
    },
    onSuccess: async (updated) => {
      if (selectedAoiId === updated.id && !showInactive) {
        setSelectedAoiId(null);
      }
      await queryClient.invalidateQueries({ queryKey: ["geospatial-aois", token] });
    },
  });

  const ingestMutation = useMutation({
    mutationFn: async () => {
      const search = new URLSearchParams();
      search.set("backend", pipelineBackend.trim() || "gee");
      if (pipelineNotes.trim()) {
        search.set("notes", pipelineNotes.trim());
      }
      for (const source of pipelineSourcesText.split(",").map((value) => value.trim()).filter(Boolean)) {
        search.append("sources", source);
      }
      return apiFetch<{ run_id: number; status: string }>(`/api/v1/geospatial/ingest/run?${search.toString()}`, {
        token,
        method: "POST",
      });
    },
    onSuccess: async (payload) => {
      setPipelineError(null);
      setSelectedRunId(payload.run_id);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["geospatial-pipeline-runs", token] }),
        queryClient.invalidateQueries({ queryKey: ["geospatial-pipeline-run-detail", token] }),
      ]);
    },
    onError: (error: unknown) => setPipelineError(error instanceof Error ? error.message : "Failed to queue ingest run."),
  });

  const recomputeMutation = useMutation({
    mutationFn: async () => {
      const search = new URLSearchParams();
      search.set("backend", pipelineBackend.trim() || "gee");
      if (pipelineNotes.trim()) {
        search.set("notes", pipelineNotes.trim());
      }
      if (pipelineScopeToSelectedAoi && selectedAoiId != null) {
        search.set("aoi_id", String(selectedAoiId));
      }
      for (const source of pipelineSourcesText.split(",").map((value) => value.trim()).filter(Boolean)) {
        search.append("sources", source);
      }
      return apiFetch<{ run_id: number; status: string }>(`/api/v1/geospatial/features/recompute?${search.toString()}`, {
        token,
        method: "POST",
      });
    },
    onSuccess: async (payload) => {
      setPipelineError(null);
      setSelectedRunId(payload.run_id);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["geospatial-pipeline-runs", token] }),
        queryClient.invalidateQueries({ queryKey: ["geospatial-pipeline-run-detail", token] }),
        queryClient.invalidateQueries({ queryKey: ["geospatial-observations", token, selectedAoiId] }),
        queryClient.invalidateQueries({ queryKey: ["geospatial-timeline", token, selectedAoiId] }),
      ]);
    },
    onError: (error: unknown) => setPipelineError(error instanceof Error ? error.message : "Failed to queue feature refresh run."),
  });

  const cancelRunMutation = useMutation({
    mutationFn: async (runId: number) => {
      return apiFetch<{ run_id: number; status: string }>(`/api/v1/geospatial/runs/${runId}/cancel`, {
        token,
        method: "POST",
      });
    },
    onSuccess: async (payload) => {
      setPipelineError(null);
      setSelectedRunId(payload.run_id);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["geospatial-pipeline-runs", token] }),
        queryClient.invalidateQueries({ queryKey: ["geospatial-pipeline-run-detail", token] }),
      ]);
    },
    onError: (error: unknown) => setPipelineError(error instanceof Error ? error.message : "Failed to cancel run."),
  });

  const retryRunMutation = useMutation({
    mutationFn: async (runId: number) => {
      return apiFetch<{ run_id: number; status: string }>(`/api/v1/geospatial/runs/${runId}/retry`, {
        token,
        method: "POST",
      });
    },
    onSuccess: async (payload) => {
      setPipelineError(null);
      setSelectedRunId(payload.run_id);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["geospatial-pipeline-runs", token] }),
        queryClient.invalidateQueries({ queryKey: ["geospatial-pipeline-run-detail", token] }),
      ]);
    },
    onError: (error: unknown) => setPipelineError(error instanceof Error ? error.message : "Failed to retry run."),
  });

  if (aois.isLoading || overview.isLoading || layers.isLoading) {
    return <LoadingState label="Loading geospatial AOIs..." />;
  }

  if (aois.error || overview.error || layers.error) {
    return <ErrorState message="Failed to load geospatial AOI workspace" />;
  }

  const rows = aois.data ?? [];
  const selectedAoi = rows.find((row) => row.id === selectedAoiId) ?? null;
  const observationRows = observations.data ?? [];
  const filteredObservationRows = observationRows
    .filter((row) => (row.observation_confidence_score ?? 0) >= confidenceFloor)
    .filter((row) => overlaySourceFilter === "all" || row.source === overlaySourceFilter);
  const latestObservation = filteredObservationRows[0] ?? observationRows[0];
  const runRows = pipelineRuns.data ?? [];
  const queuedRunCount = runRows.filter((row) => row.status === "queued").length;
  const latestRun = runRows[0];
  const selectedRun = selectedRunDetail.data ?? runRows.find((row) => row.id === selectedRunId) ?? null;
  const selectedRunScenes = selectedRunDetail.data?.related_scenes ?? [];
  const selectedRunFeatures = selectedRunDetail.data?.related_features ?? [];
  const selectedRunProvenance = selectedRunDetail.data?.provenance_summary ?? null;
  const selectedRunDrilldownHref = selectedRun
    ? requestedReturnTo && requestedReturnTo.startsWith(`/dashboard/geospatial/runs/${selectedRun.id}`)
      ? requestedReturnTo
      : `/dashboard/geospatial/runs/${selectedRun.id}`
    : "#";
  const hasSavedDrilldownContext = !!requestedReturnTo && requestedReturnTo.startsWith("/dashboard/geospatial/runs/");
  const timelineRows = (timeline.data?.observations ?? [])
    .filter((row) => (row.observation_confidence_score ?? 0) >= confidenceFloor)
    .filter((row) => overlaySourceFilter === "all" || row.source === overlaySourceFilter)
    .slice(0, Math.max(1, timelineWindow));
  const timelineAnomalies = timelineRows.filter((row) => {
    const crop = row.crop_activity_score ?? 0;
    const vigor = row.vegetation_vigor_score ?? 0;
    return Math.abs(crop - vigor) >= anomalyThreshold;
  });
  const canCancelSelectedRun = canManageAOIs && selectedRun != null && ["queued", "running"].includes(selectedRun.status);
  const canRetrySelectedRun = canManageAOIs && selectedRun != null && ["failed", "cancelled"].includes(selectedRun.status);
  const highlightedObservationKey = requestedObservationDate || requestedSource ? `${requestedObservationDate}::${requestedSource}` : null;

  return (
    <div>
      <PageHeader title="Geospatial AOIs" subtitle="Draw AOI polygons, validate them before save, and inspect geospatial observations per area." />

      <div className="mb-6 grid gap-4 md:grid-cols-4">
        <StatCard label="AOIs" value={String(overview.data?.total_aois ?? 0)} />
        <StatCard label="Features" value={String(overview.data?.total_features ?? 0)} />
        <StatCard label="Latest Observation" value={overview.data?.latest_observation_date ?? "n/a"} />
        <StatCard label="Layer Registry" value={String(layers.data?.layers.length ?? 0)} hint="Available analytical layers" />
      </div>

      <SectionShell title="Pipeline Controls and Runs">
        {hasSavedDrilldownContext ? (
          <div
            className="mb-3 rounded border border-sky-200 bg-sky-50 px-3 py-2 text-xs text-sky-800"
            data-testid="saved-drilldown-context-hint"
          >
            Saved drilldown context detected. Re-open drilldown to continue from your previous filters.
          </div>
        ) : null}
        <div className="grid gap-4 xl:grid-cols-[1.1fr_1fr]">
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <div className="mb-4 grid gap-4 md:grid-cols-3">
              <StatCard label="Recent Runs" value={String(runRows.length)} />
              <StatCard label="Queued Runs" value={String(queuedRunCount)} />
              <StatCard label="Latest Run" value={latestRun?.run_type ?? "n/a"} hint={latestRun?.status ?? "no runs"} />
            </div>

            {!canManageAOIs ? (
              <EmptyState title="Insufficient role" description="Queueing geospatial pipeline runs requires super_admin or provincial_admin." />
            ) : (
              <div className="grid gap-3 md:grid-cols-2">
                <label className="text-sm text-slate-700">
                  Backend
                  <input value={pipelineBackend} onChange={(e) => setPipelineBackend(e.target.value)} className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm" />
                </label>
                <label className="text-sm text-slate-700">
                  Sources (comma-separated)
                  <input value={pipelineSourcesText} onChange={(e) => setPipelineSourcesText(e.target.value)} className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm" />
                </label>
                <label className="text-sm text-slate-700 md:col-span-2">
                  Notes
                  <input value={pipelineNotes} onChange={(e) => setPipelineNotes(e.target.value)} className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm" />
                </label>
                <label className="flex items-center gap-2 text-sm text-slate-700 md:col-span-2">
                  <input
                    aria-label="Scope recompute to selected AOI"
                    type="checkbox"
                    checked={pipelineScopeToSelectedAoi}
                    onChange={(e) => setPipelineScopeToSelectedAoi(e.target.checked)}
                  />
                  Scope feature recompute to selected AOI when available
                </label>
                {pipelineError ? <ErrorState message={pipelineError} /> : null}
                <div className="flex flex-wrap gap-2 md:col-span-2">
                  <button
                    type="button"
                    aria-label="Queue ingest discovery"
                    onClick={() => ingestMutation.mutate()}
                    disabled={ingestMutation.isPending}
                    className="rounded bg-slate-900 px-3 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Queue ingest discovery
                  </button>
                  <button
                    type="button"
                    aria-label="Queue feature recompute"
                    onClick={() => recomputeMutation.mutate()}
                    disabled={recomputeMutation.isPending}
                    className="rounded border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Queue feature recompute
                  </button>
                </div>
              </div>
            )}
          </div>

          <div>
            <h3 className="mb-3 text-sm font-semibold text-slate-800">Recent pipeline runs</h3>
            {pipelineRuns.isLoading ? (
              <LoadingState label="Loading geospatial pipeline runs..." />
            ) : pipelineRuns.error ? (
              <ErrorState message="Failed to load geospatial pipeline runs" />
            ) : runRows.length === 0 ? (
              <EmptyState title="No pipeline runs yet" description="Queue an ingest or feature recompute run to populate history." />
            ) : (
              <DataTable
                columns={[
                  {
                    key: "id",
                    label: "Run",
                    render: (row) => {
                      const item = row as PipelineRunItem;
                      return (
                        <button
                          type="button"
                          aria-label={`Inspect run ${item.id}`}
                          onClick={() => setSelectedRunId(item.id)}
                          className={`rounded px-2 py-1 text-xs font-semibold ${selectedRunId === item.id ? "bg-slate-900 text-white" : "border border-slate-300 text-slate-700 hover:bg-slate-50"}`}
                        >
                          #{item.id}
                        </button>
                      );
                    },
                  },
                  { key: "run_type", label: "Type" },
                  {
                    key: "status",
                    label: "Status",
                    render: (row) => {
                      const status = String((row as PipelineRunItem).status ?? "unknown");
                      return <span className={`rounded-full px-2 py-1 text-xs font-semibold ${statusBadgeClass(status)}`}>{status}</span>;
                    },
                  },
                  { key: "backend", label: "Backend" },
                  { key: "aoi_code", label: "AOI", render: (row) => String((row as PipelineRunItem).aoi_code ?? "all") },
                  { key: "started_at", label: "Started" },
                  {
                    key: "finished_at",
                    label: "Elapsed",
                    render: (row) => formatElapsedTime((row as PipelineRunItem).started_at, (row as PipelineRunItem).finished_at),
                  },
                  { key: "sources", label: "Sources", render: (row) => ((row as PipelineRunItem).sources ?? []).join(", ") || "all" },
                  {
                    key: "results",
                    label: "Results",
                    render: (row) => {
                      const summary = summarizeRunResults(row as PipelineRunItem);
                      return <span className={`rounded px-2 py-1 text-xs font-medium ${resultToneClass(summary.tone)}`}>{summary.text}</span>;
                    },
                  },
                ]}
                rows={runRows as unknown as Record<string, unknown>[]}
              />
            )}

            <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-4" data-testid="selected-run-details">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <h4 className="text-sm font-semibold text-slate-800">Selected run details</h4>
                <div className="flex flex-wrap gap-2">
                  {selectedRun ? (
                    <>
                      <a
                        href={selectedRunDrilldownHref}
                        aria-label="Open drilldown"
                        className="rounded border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-white"
                      >
                        Open drilldown
                      </a>
                      <button
                        type="button"
                        aria-label="Retry selected run"
                        disabled={!canRetrySelectedRun || retryRunMutation.isPending}
                        onClick={() => retryRunMutation.mutate(selectedRun.id)}
                        className="rounded border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        Retry run
                      </button>
                      <button
                        type="button"
                        aria-label="Cancel selected run"
                        disabled={!canCancelSelectedRun || cancelRunMutation.isPending}
                        onClick={() => cancelRunMutation.mutate(selectedRun.id)}
                        className="rounded border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        Cancel run
                      </button>
                    </>
                  ) : null}
                  <button
                    type="button"
                    aria-label="Refresh pipeline runs"
                    onClick={() => {
                      void Promise.all([pipelineRuns.refetch(), selectedRunDetail.refetch()]);
                    }}
                    className="rounded border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-white"
                  >
                    Refresh
                  </button>
                </div>
              </div>
              {!selectedRun ? (
                <p className="text-sm text-slate-500">Select a run from the table to inspect its parameters and results.</p>
              ) : selectedRunDetail.isLoading && !selectedRunDetail.data ? (
                <LoadingState label="Loading run provenance..." />
              ) : selectedRunDetail.error ? (
                <ErrorState message="Failed to load run provenance" />
              ) : (
                <div className="space-y-3 text-sm text-slate-700">
                  <div className="grid gap-3 md:grid-cols-2">
                    <div className="rounded bg-white p-3 shadow-sm">
                      <div className="text-xs uppercase tracking-wide text-slate-500">Run identity</div>
                      <div className="mt-2 font-semibold">#{selectedRun.id} · {selectedRun.run_type}</div>
                      <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                        <span className={`rounded-full px-2 py-1 font-semibold ${statusBadgeClass(selectedRun.status)}`}>{selectedRun.status}</span>
                        <span>Backend: {selectedRun.backend}</span>
                        <span>Elapsed: {formatElapsedTime(selectedRun.started_at, selectedRun.finished_at)}</span>
                      </div>
                      <div className="text-xs text-slate-500">AOI: {selectedRun.aoi_code ?? "all"}</div>
                    </div>
                    <div className="rounded bg-white p-3 shadow-sm">
                      <div className="text-xs uppercase tracking-wide text-slate-500">Timing</div>
                      <div className="mt-2">Started: {selectedRun.started_at ?? "n/a"}</div>
                      <div>Finished: {selectedRun.finished_at ?? "n/a"}</div>
                      <div>Correlation: {selectedRun.correlation_id ?? "n/a"}</div>
                      <div className="mt-2 text-xs text-slate-500">
                        Provenance: {selectedRunProvenance?.scene_count ?? 0} scenes · {selectedRunProvenance?.feature_count ?? 0} features
                      </div>
                    </div>
                  </div>

                  <div className="grid gap-3 lg:grid-cols-2">
                    <div className="rounded bg-white p-3 shadow-sm">
                      <div className="text-xs uppercase tracking-wide text-slate-500">Parameters</div>
                      <pre className="mt-2 overflow-x-auto rounded bg-slate-50 p-3 text-xs text-slate-700">{JSON.stringify(selectedRun.parameters ?? {}, null, 2)}</pre>
                    </div>
                    <div className="rounded bg-white p-3 shadow-sm">
                      <div className="text-xs uppercase tracking-wide text-slate-500">Results</div>
                      <pre className="mt-2 overflow-x-auto rounded bg-slate-50 p-3 text-xs text-slate-700">{JSON.stringify(selectedRun.results ?? {}, null, 2)}</pre>
                    </div>
                  </div>

                  <div className="rounded bg-white p-3 shadow-sm">
                    <div className="text-xs uppercase tracking-wide text-slate-500">Notes and sources</div>
                    <div className="mt-2">Notes: {selectedRun.notes ?? "n/a"}</div>
                    <div>Sources: {(selectedRun.sources ?? []).join(", ") || "all"}</div>
                    <div>Scene sources: {(selectedRunProvenance?.scene_sources ?? []).join(", ") || "n/a"}</div>
                    <div>Feature sources: {(selectedRunProvenance?.feature_sources ?? []).join(", ") || "n/a"}</div>
                  </div>

                  <div className="grid gap-3 lg:grid-cols-2">
                    <div className="rounded bg-white p-3 shadow-sm">
                      <div className="mb-2 flex items-center justify-between gap-2">
                        <div className="text-xs uppercase tracking-wide text-slate-500">Scene provenance</div>
                        <span className="text-xs text-slate-500">{selectedRunScenes.length} linked</span>
                      </div>
                      {selectedRunScenes.length === 0 ? (
                        <p className="text-sm text-slate-500">No scene provenance is available for this run yet.</p>
                      ) : (
                        <div className="space-y-2">
                          {selectedRunScenes.slice(0, 8).map((scene) => (
                            <div key={`${scene.source}-${scene.scene_id}`} className="rounded border border-slate-200 p-2">
                              <div className="font-medium text-slate-800">{scene.source} · {scene.scene_id}</div>
                              <div className="text-xs text-slate-500">
                                AOI: {scene.aoi_code ?? "n/a"} · Acquired: {scene.acquired_at ?? "n/a"}
                              </div>
                              <div className="text-xs text-slate-500">
                                Status: {scene.processing_status} · Trace: {scene.provenance_status ?? "linked"} · Cloud: {formatMetric(scene.cloud_score)}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    <div className="rounded bg-white p-3 shadow-sm">
                      <div className="mb-2 flex items-center justify-between gap-2">
                        <div className="text-xs uppercase tracking-wide text-slate-500">Feature outputs</div>
                        <span className="text-xs text-slate-500">{selectedRunFeatures.length} materialized</span>
                      </div>
                      {selectedRunFeatures.length === 0 ? (
                        <p className="text-sm text-slate-500">No feature records are linked to this run.</p>
                      ) : (
                        <div className="space-y-2">
                          {selectedRunFeatures.slice(0, 8).map((feature) => (
                            <div key={feature.id} className="rounded border border-slate-200 p-2">
                              <div className="font-medium text-slate-800">{feature.source} · {feature.observation_date ?? "n/a"}</div>
                              <div className="text-xs text-slate-500">
                                AOI: {feature.aoi_code ?? "n/a"} · Scene: {feature.scene_id ?? "n/a"}
                              </div>
                              <div className="text-xs text-slate-500">
                                Confidence: {formatMetric(feature.observation_confidence_score)} · Crop: {formatMetric(feature.crop_activity_score)} · Vigor: {formatMetric(feature.vegetation_vigor_score)}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </SectionShell>

      <SectionShell title="AOI List">
        <div className="mb-3 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input aria-label="Include inactive AOIs" type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} />
              Include inactive
            </label>
            <p className="text-xs text-slate-500">Select an AOI to inspect observations or edit its geometry.</p>
          </div>
          <div className="grid gap-3 rounded-lg border border-slate-200 bg-slate-50 p-3 md:grid-cols-2 xl:grid-cols-4">
            <label className="text-xs text-slate-600">
              Search
              <input value={listSearch} onChange={(event) => setListSearch(event.target.value)} placeholder="Code or name" className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm text-slate-700" />
            </label>
            <label className="text-xs text-slate-600">
              Municipality ID
              <input value={listMunicipalityId} onChange={(event) => setListMunicipalityId(event.target.value)} placeholder="e.g. 1" className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm text-slate-700" />
            </label>
            <label className="text-xs text-slate-600">
              Warehouse ID
              <input value={listWarehouseId} onChange={(event) => setListWarehouseId(event.target.value)} placeholder="e.g. 2" className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm text-slate-700" />
            </label>
            <label className="text-xs text-slate-600">
              Market ID
              <input value={listMarketId} onChange={(event) => setListMarketId(event.target.value)} placeholder="e.g. 3" className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm text-slate-700" />
            </label>
            <label className="text-xs text-slate-600">
              Tag
              <input value={listTag} onChange={(event) => setListTag(event.target.value)} placeholder="priority-zone" className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm text-slate-700" />
            </label>
            <label className="flex items-center gap-2 text-xs text-slate-600">
              <input type="checkbox" checked={listWatchlistOnly} onChange={(event) => setListWatchlistOnly(event.target.checked)} />
              Watchlist only
            </label>
            <label className="flex items-center gap-2 text-xs text-slate-600">
              <input type="checkbox" checked={listFavoritesOnly} onChange={(event) => setListFavoritesOnly(event.target.checked)} />
              Favorites only
            </label>
            <button
              type="button"
              onClick={() => {
                setListSearch("");
                setListMunicipalityId("");
                setListWarehouseId("");
                setListMarketId("");
                setListTag("");
                setListWatchlistOnly(false);
                setListFavoritesOnly(false);
              }}
              className="self-end rounded border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-white"
            >
              Reset AOI filters
            </button>
          </div>
        </div>

        {rows.length === 0 ? (
          <EmptyState title="No AOIs found" description="Seed data should include a demo AOI. Try toggling the inactive filter." />
        ) : (
          <DataTable
            columns={[
              { key: "id", label: "ID" },
              { key: "code", label: "Code" },
              { key: "name", label: "Name" },
              { key: "scope_type", label: "Scope" },
              {
                key: "municipality_id",
                label: "Municipality",
                render: (row) => String((row as AoiListItem).municipality_id ?? ""),
              },
              { key: "source", label: "Source" },
              {
                key: "is_active",
                label: "Active",
                render: (row) => (((row as AoiListItem).is_active ?? false) ? "yes" : "no"),
              },
              {
                key: "actions" as keyof AoiListItem,
                label: "Actions",
                render: (row) => {
                  const item = row as AoiListItem;
                  return (
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        aria-label={`Inspect ${item.code}`}
                        className="rounded border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
                        onClick={() => setSelectedAoiId(item.id)}
                      >
                        Inspect
                      </button>
                      <button
                        type="button"
                        aria-label={`Edit ${item.code}`}
                        className="rounded border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
                        onClick={() => {
                          void loadAoiForEdit(item.id);
                        }}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        aria-label={`Versions ${item.code}`}
                        className="rounded border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
                        onClick={() => {
                          setSelectedAoiId(item.id);
                          setVersionsAoiId((prev) => (prev === item.id ? null : item.id));
                        }}
                      >
                        Versions
                      </button>
                      <button
                        type="button"
                        aria-label={`Deactivate ${item.code}`}
                        disabled={!canManageAOIs || !item.is_active || deactivateMutation.isPending}
                        className="rounded border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                        onClick={() => deactivateMutation.mutate(item.id)}
                      >
                        Deactivate
                      </button>
                    </div>
                  );
                },
              },
            ]}
            rows={rows as unknown as Record<string, unknown>[]}
          />
        )}
      </SectionShell>

      <SectionShell title="Selected AOI Insights">
        {!selectedAoi ? (
          <EmptyState title="Select an AOI" description="Use Inspect or Edit in the AOI list to load observation summaries." />
        ) : (
          <div className="space-y-6" data-testid="selected-aoi-insights">
            {requestedFocus ? (
              <div className="rounded-lg border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-700">
                <div className="font-medium">Deep-linked context active for AOI {selectedAoi.code}</div>
                <div className="mt-2 flex flex-wrap gap-2 text-xs">
                  {requestedSceneId ? <span className="rounded-full bg-white px-2 py-1 font-medium text-sky-700">Scene ID: {requestedSceneId}</span> : null}
                  {requestedObservationDate ? <span className="rounded-full bg-white px-2 py-1 font-medium text-sky-700">Observation Date: {requestedObservationDate}</span> : null}
                  {requestedSource ? <span className="rounded-full bg-white px-2 py-1 font-medium text-sky-700">Source: {requestedSource}</span> : null}
                </div>
              </div>
            ) : null}
            <div className="grid gap-4 md:grid-cols-4">
              <StatCard label="Selected AOI" value={selectedAoi.code} hint={selectedAoi.name} />
              <StatCard label="Recent Observations" value={String(filteredObservationRows.length)} />
              <StatCard label="Avg Crop Activity" value={averageMetric(filteredObservationRows, "crop_activity_score")} />
              <StatCard label="Avg Confidence" value={averageMetric(filteredObservationRows, "observation_confidence_score")} />
            </div>

            <div className="grid gap-6 xl:grid-cols-[1.25fr_1fr]">
              <div id="aoi-observations-section">
                <h3 className="mb-3 text-sm font-semibold text-slate-800">Recent observations</h3>
                {observations.isLoading ? (
                  <LoadingState label="Loading observations..." />
                ) : observations.error ? (
                  <ErrorState message="Failed to load AOI observations" />
                ) : filteredObservationRows.length === 0 ? (
                  <EmptyState title="No observations yet" description="Seeded or refreshed AOI features will appear here." />
                ) : (
                  <div className="space-y-2 rounded-lg border border-slate-200 bg-white p-2">
                    <div className="grid grid-cols-6 gap-3 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                      <div>Date</div>
                      <div>Source</div>
                      <div>Crop</div>
                      <div>Vigor</div>
                      <div>Confidence</div>
                      <div>Cloud</div>
                    </div>
                    {filteredObservationRows.map((row) => {
                      const rowKey = `${row.observation_date}::${row.source}`;
                      const isHighlighted = highlightedObservationKey === rowKey;
                      return (
                        <div key={row.id} className={`grid grid-cols-6 gap-3 rounded px-3 py-2 text-sm text-slate-700 ${isHighlighted ? "bg-amber-50 ring-1 ring-amber-300" : "bg-slate-50"}`}>
                          <div>{row.observation_date}</div>
                          <div>{row.source}</div>
                          <div>{formatMetric(row.crop_activity_score)}</div>
                          <div>{formatMetric(row.vegetation_vigor_score)}</div>
                          <div>{formatMetric(row.observation_confidence_score)}</div>
                          <div>{formatMetric(row.cloud_score)}</div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              <div id="aoi-timeline-section">
                <h3 className="mb-3 text-sm font-semibold text-slate-800">Timeline and layers</h3>
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                  <p className="text-sm text-slate-700">
                    Latest source: <span className="font-semibold">{latestObservation?.source ?? "n/a"}</span>
                  </p>
                  <p className="mt-1 text-sm text-slate-700">
                    Latest observation date: <span className="font-semibold">{latestObservation?.observation_date ?? "n/a"}</span>
                  </p>
                  <div className="mt-3 grid gap-2 rounded border border-slate-200 bg-white p-3 text-xs text-slate-600 sm:grid-cols-2">
                    <label>
                      Basemap
                      <select value={basemap} onChange={(event) => setBasemap(event.target.value)} className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-xs text-slate-700">
                        <option value="OpenStreetMap">OpenStreetMap</option>
                        <option value="Satellite">Satellite</option>
                        <option value="Terrain">Terrain</option>
                      </select>
                    </label>
                    <label>
                      Layer opacity ({layerOpacity}%)
                      <input type="range" min={10} max={100} step={5} value={layerOpacity} onChange={(event) => setLayerOpacity(Number(event.target.value))} className="mt-1 w-full" />
                    </label>
                    <label>
                      Source overlay
                      <select value={overlaySourceFilter} onChange={(event) => setOverlaySourceFilter(event.target.value)} className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-xs text-slate-700">
                        <option value="all">All sources</option>
                        <option value="sentinel-2">sentinel-2</option>
                        <option value="sentinel-1">sentinel-1</option>
                        <option value="landsat">landsat</option>
                      </select>
                    </label>
                    <label>
                      Timeline window ({timelineWindow})
                      <input type="range" min={3} max={20} step={1} value={timelineWindow} onChange={(event) => setTimelineWindow(Number(event.target.value))} className="mt-1 w-full" />
                    </label>
                    <label>
                      Confidence filter ({confidenceFloor.toFixed(2)})
                      <input type="range" min={0} max={1} step={0.05} value={confidenceFloor} onChange={(event) => setConfidenceFloor(Number(event.target.value))} className="mt-1 w-full" />
                    </label>
                    <label>
                      Anomaly threshold ({anomalyThreshold.toFixed(2)})
                      <input type="range" min={0.05} max={0.5} step={0.01} value={anomalyThreshold} onChange={(event) => setAnomalyThreshold(Number(event.target.value))} className="mt-1 w-full" />
                    </label>
                    <label className="flex items-center gap-2">
                      <input type="checkbox" checked={showLegend} onChange={(event) => setShowLegend(event.target.checked)} />
                      Show legend panel
                    </label>
                    <label className="flex items-center gap-2">
                      <input type="checkbox" checked={clusterMode} onChange={(event) => setClusterMode(event.target.checked)} />
                      Feature clustering on map
                    </label>
                    <label className="flex items-center gap-2">
                      <input type="checkbox" checked={animateTimeline} onChange={(event) => setAnimateTimeline(event.target.checked)} />
                      Map animation over time
                    </label>
                    <label className="flex items-center gap-2">
                      <input type="checkbox" checked={mapFullscreen} onChange={(event) => setMapFullscreen(event.target.checked)} />
                      Fullscreen mode
                    </label>
                    <button
                      type="button"
                      onClick={() => {
                        const payload = {
                          basemap,
                          layerOpacity,
                          overlaySourceFilter,
                          timelineRows,
                          anomalies: timelineAnomalies,
                          generated_at: new Date().toISOString(),
                        };
                        const text = JSON.stringify(payload, null, 2);
                        const blob = new Blob([text], { type: "application/json;charset=utf-8" });
                        const url = URL.createObjectURL(blob);
                        const anchor = document.createElement("a");
                        anchor.href = url;
                        anchor.download = `aoi-${selectedAoi?.code ?? "snapshot"}-map-snapshot.json`;
                        document.body.append(anchor);
                        anchor.click();
                        anchor.remove();
                        URL.revokeObjectURL(url);
                      }}
                      className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50"
                    >
                      Map snapshot export
                    </button>
                    <div className="rounded border border-slate-200 bg-slate-50 px-2 py-1">
                      Measurement tools: bbox estimate uses selected AOI polygon bounds and current layer opacity {layerOpacity}%.
                    </div>
                  </div>
                  <div className="mt-4">
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Timeline points</p>
                    {timeline.isLoading ? (
                      <LoadingState label="Loading AOI timeline..." />
                    ) : timeline.error ? (
                      <ErrorState message="Failed to load AOI timeline" />
                    ) : timelineRows.length === 0 ? (
                      <p className="mt-2 text-sm text-slate-500">No timeline points available.</p>
                    ) : (
                      <ul className="mt-2 space-y-2 text-sm text-slate-700">
                        {timelineRows.map((point) => (
                          <li
                            key={`${point.observation_date}-${point.source}`}
                            className={`rounded px-3 py-2 shadow-sm ${highlightedObservationKey === `${point.observation_date}::${point.source}` ? "bg-amber-50 ring-1 ring-amber-300" : "bg-white"} ${animateTimeline ? "transition-all duration-300 hover:-translate-y-0.5" : ""}`}
                          >
                            <div className="font-medium">{point.observation_date} · {point.source}</div>
                            <div className="text-xs text-slate-500">
                              Crop {formatMetric(point.crop_activity_score)} · Vigor {formatMetric(point.vegetation_vigor_score)} · Confidence {formatMetric(point.observation_confidence_score)}
                            </div>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>

                  <div className="mt-4">
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Available layers</p>
                    <ul className="mt-2 space-y-2 text-sm text-slate-700">
                      {(layers.data?.layers ?? []).map((layer) => (
                        <li key={layer.key} className="rounded bg-white px-3 py-2 shadow-sm">
                          <div className="flex items-center justify-between gap-2">
                            <div className="font-medium">{layer.label}</div>
                            <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${String((layer as { status?: string }).status ?? "ready") === "degraded" ? "bg-amber-100 text-amber-700" : "bg-emerald-100 text-emerald-700"}`}>
                              {String((layer as { status?: string }).status ?? "ready")}
                            </span>
                          </div>
                          <div className="text-xs text-slate-500">{layer.description}</div>
                          {showLegend ? (
                            <div className="mt-1 text-[11px] text-slate-500">
                              Legend: {Array.isArray((layer as { legend?: string[] }).legend) ? ((layer as { legend?: string[] }).legend ?? []).join(" | ") : "n/a"}
                            </div>
                          ) : null}
                          {String((layer as { status?: string }).status ?? "ready") === "degraded" ? (
                            <button
                              type="button"
                              onClick={async () => {
                                await apiFetch(`/api/v1/geospatial/map/layers/${layer.key}/retry`, { token, method: "POST" });
                                await layers.refetch();
                              }}
                              className="mt-2 rounded border border-slate-300 px-2 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-50"
                            >
                              Retry layer
                            </button>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                    {timelineAnomalies.length > 0 ? (
                      <div className="mt-3 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                        Anomaly threshold filter flagged {timelineAnomalies.length} timeline points.
                      </div>
                    ) : null}
                    <div className="mt-3 rounded border border-slate-200 bg-white px-3 py-2 text-xs text-slate-600">
                      Load status badges, basemap switcher, source overlays, date-range slider, confidence/anomaly filters, and clustering toggles are active for this AOI map panel.
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </SectionShell>

      {versionsAoiId ? (
        <SectionShell title={`AOI Versions (AOI #${versionsAoiId})`}>
          {versions.isLoading ? (
            <LoadingState label="Loading versions..." />
          ) : versions.error ? (
            <ErrorState message="Failed to load AOI versions" />
          ) : (
            <DataTable
              columns={[
                { key: "version", label: "Version" },
                { key: "change_type", label: "Type" },
                { key: "changed_by", label: "By" },
                { key: "changed_at", label: "At" },
                { key: "change_reason", label: "Reason" },
              ]}
              rows={(versions.data ?? []) as unknown as Record<string, unknown>[]}
            />
          )}
        </SectionShell>
      ) : null}

      <SectionShell title="Create AOI">
        {!canManageAOIs ? (
          <EmptyState title="Insufficient role" description="Creating AOIs requires super_admin or provincial_admin." />
        ) : (
          <div className="space-y-4">
            <div className="grid gap-3 md:grid-cols-2">
              <label className="text-sm text-slate-700">
                Code
                <input
                  aria-label="Create AOI code"
                  value={createCode}
                  onChange={(e) => setCreateCode(e.target.value)}
                  className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
                  placeholder="OM-SJ-DEMO-AOI"
                />
              </label>
              <label className="text-sm text-slate-700">
                Name
                <input
                  aria-label="Create AOI name"
                  value={createName}
                  onChange={(e) => setCreateName(e.target.value)}
                  className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
                  placeholder="San Jose Demo AOI"
                />
              </label>
              <label className="text-sm text-slate-700">
                Scope type
                <input value={createScopeType} onChange={(e) => setCreateScopeType(e.target.value)} className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm" />
              </label>
              <label className="text-sm text-slate-700">
                Source
                <input value={createSource} onChange={(e) => setCreateSource(e.target.value)} className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm" />
              </label>
              <label className="text-sm text-slate-700">
                Municipality ID (optional)
                <input value={createMunicipalityId} onChange={(e) => setCreateMunicipalityId(e.target.value)} className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm" />
              </label>
              <label className="text-sm text-slate-700">
                Warehouse ID (optional)
                <input value={createWarehouseId} onChange={(e) => setCreateWarehouseId(e.target.value)} className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm" />
              </label>
              <label className="text-sm text-slate-700">
                Market ID (optional)
                <input value={createMarketId} onChange={(e) => setCreateMarketId(e.target.value)} className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm" />
              </label>
              <label className="text-sm text-slate-700">
                Change reason (optional)
                <input value={createChangeReason} onChange={(e) => setCreateChangeReason(e.target.value)} className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm" />
              </label>
              <label className="text-sm text-slate-700 md:col-span-2">
                Description (optional)
                <input aria-label="Create AOI description" value={createDescription} onChange={(e) => setCreateDescription(e.target.value)} className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm" />
              </label>
            </div>

            <GeospatialPolygonEditor title="Create AOI geometry" vertices={createVertices} onChange={setCreateVertices} errors={createValidationErrors} />

            {createServerError ? <ErrorState message={createServerError} /> : null}
            <div>
              <button
                type="button"
                onClick={() => createMutation.mutate()}
                disabled={createMutation.isPending || createValidationErrors.length > 0 || !createCode.trim() || !createName.trim()}
                className="rounded bg-slate-900 px-3 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                Create AOI
              </button>
            </div>
          </div>
        )}
      </SectionShell>

      <SectionShell title="Edit AOI">
        {!canManageAOIs ? (
          <EmptyState title="Insufficient role" description="Updating/deactivating AOIs requires super_admin or provincial_admin." />
        ) : editAoiId == null ? (
          <EmptyState title="Select an AOI" description="Use the Edit action in the AOI list." />
        ) : (
          <div className="space-y-4">
            <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">Editing AOI #{editAoiId}</div>
            <div className="grid gap-3 md:grid-cols-2">
              <label className="text-sm text-slate-700">
                Code
                <input aria-label="Edit AOI code" value={editCode} onChange={(e) => setEditCode(e.target.value)} className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm" />
              </label>
              <label className="text-sm text-slate-700">
                Name
                <input aria-label="Edit AOI name" value={editName} onChange={(e) => setEditName(e.target.value)} className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm" />
              </label>
              <label className="text-sm text-slate-700">
                Scope type
                <input value={editScopeType} onChange={(e) => setEditScopeType(e.target.value)} className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm" />
              </label>
              <label className="text-sm text-slate-700">
                Source
                <input value={editSource} onChange={(e) => setEditSource(e.target.value)} className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm" />
              </label>
              <label className="text-sm text-slate-700">
                Municipality ID (optional)
                <input value={editMunicipalityId} onChange={(e) => setEditMunicipalityId(e.target.value)} className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm" />
              </label>
              <label className="text-sm text-slate-700">
                Warehouse ID (optional)
                <input value={editWarehouseId} onChange={(e) => setEditWarehouseId(e.target.value)} className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm" />
              </label>
              <label className="text-sm text-slate-700">
                Market ID (optional)
                <input value={editMarketId} onChange={(e) => setEditMarketId(e.target.value)} className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm" />
              </label>
              <label className="text-sm text-slate-700">
                Active
                <select value={editIsActive ? "true" : "false"} onChange={(e) => setEditIsActive(e.target.value === "true")} className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm">
                  <option value="true">true</option>
                  <option value="false">false</option>
                </select>
              </label>
              <label className="text-sm text-slate-700">
                Change reason (optional)
                <input value={editChangeReason} onChange={(e) => setEditChangeReason(e.target.value)} className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm" />
              </label>
              <label className="text-sm text-slate-700 md:col-span-2">
                Description (optional)
                <input aria-label="Edit AOI description" value={editDescription} onChange={(e) => setEditDescription(e.target.value)} className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm" />
              </label>
            </div>

            <GeospatialPolygonEditor title="Edit AOI geometry" vertices={editVertices} onChange={setEditVertices} errors={editValidationErrors} />

            {editServerError ? <ErrorState message={editServerError} /> : null}
            <div>
              <button
                type="button"
                onClick={() => updateMutation.mutate()}
                disabled={updateMutation.isPending || editValidationErrors.length > 0 || !editCode.trim() || !editName.trim()}
                className="rounded bg-slate-900 px-3 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                Save changes
              </button>
            </div>
          </div>
        )}
      </SectionShell>

      <GeospatialAoiAdvancedPanel
        token={token}
        selectedAoi={selectedAoi}
        selectedRunId={selectedRun?.id ?? null}
        aoiRows={rows.map((row) => ({ id: row.id, code: row.code, name: row.name, is_active: row.is_active }))}
        canManageAOIs={canManageAOIs}
      />
    </div>
  );
}
