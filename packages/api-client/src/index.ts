"use client";

import { useQuery } from "@tanstack/react-query";
import { apiConfig } from "@phil-onion-watch/config";
import type {
  AdminOverview,
  AuditEvent,
  AuditEventDiff,
  AlertItem,
  AnomalyEvent,
  AnomalyThresholdConfig,
  AnomalyThresholdVersion,
  ConnectorApprovalDecision,
  ConnectorApprovalWorkflow,
  ConnectorDefinition,
  ConnectorIngestionResponse,
  ConnectorSubmission,
  DocumentIngestionJob,
  KnowledgeDocument,
  DocumentSearchResult,
  ForecastDiagnostics,
  ForecastLatestResponse,
  ImportRecord,
  MobileSubmissionRecord,
  MobileSyncRequest,
  MobileSyncResponse,
  ProvincialOverview,
  ReportDeliveryLog,
  ReportDeliveryProcessResult,
  ReportExportMetadata,
  ReportRecord,
  ReportRecipientGroup,
  WarehouseOverviewRow,
} from "@phil-onion-watch/types";

const baseUrl = apiConfig.baseUrl;

export type ApiClientOptions = {
  token?: string | null;
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
};

export async function apiFetch<T>(path: string, options: ApiClientOptions = {}): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, {
    method: options.method ?? "GET",
    headers: {
      "Content-Type": "application/json",
      ...(options.token ? { Authorization: `Bearer ${options.token}` } : {}),
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }

  return (await response.json()) as T;
}

export const dashboardKeys = {
  provincial: ["dashboard", "provincial"] as const,
  warehouses: ["dashboard", "warehouses"] as const,
  prices: ["dashboard", "prices"] as const,
  imports: ["dashboard", "imports"] as const,
  alerts: ["dashboard", "alerts"] as const,
  reports: ["dashboard", "reports"] as const,
  admin: ["dashboard", "admin"] as const,
};

export function useAdminOverview(token?: string) {
  return useQuery({
    queryKey: ["admin-overview", token],
    queryFn: () => apiFetch<AdminOverview>("/api/v1/admin/overview", { token }),
    enabled: !!token,
  });
}

export type AuditEventQueryParams = {
  limit?: number;
  actorUserId?: number;
  actionType?: string;
  entityType?: string;
  entityId?: string;
  correlationId?: string;
  startTimestamp?: string;
  endTimestamp?: string;
};

function toAuditQueryString(params?: AuditEventQueryParams): string {
  const search = new URLSearchParams();
  if (typeof params?.limit === "number") {
    search.set("limit", String(params.limit));
  }
  if (typeof params?.actorUserId === "number") {
    search.set("actor_user_id", String(params.actorUserId));
  }
  if (params?.actionType) {
    search.set("action_type", params.actionType);
  }
  if (params?.entityType) {
    search.set("entity_type", params.entityType);
  }
  if (params?.entityId) {
    search.set("entity_id", params.entityId);
  }
  if (params?.correlationId) {
    search.set("correlation_id", params.correlationId);
  }
  if (params?.startTimestamp) {
    search.set("start_timestamp", params.startTimestamp);
  }
  if (params?.endTimestamp) {
    search.set("end_timestamp", params.endTimestamp);
  }
  return search.size > 0 ? `?${search.toString()}` : "";
}

export function useAuditEvents(token?: string, params?: AuditEventQueryParams) {
  const suffix = toAuditQueryString(params);
  return useQuery({
    queryKey: ["audit-events", token, suffix],
    queryFn: () => apiFetch<AuditEvent[]>(`/api/v1/audit/events${suffix}`, { token }),
    enabled: !!token,
  });
}

export function useAuditEventDiff(token: string | undefined, eventId: number | undefined) {
  return useQuery({
    queryKey: ["audit-event-diff", token, eventId],
    queryFn: () => apiFetch<AuditEventDiff>(`/api/v1/audit/events/${eventId}/diff`, { token }),
    enabled: !!token && typeof eventId === "number",
  });
}

export async function downloadAuditSlice(
  token: string | undefined,
  params: AuditEventQueryParams & { format?: "csv" | "json" } = {},
) {
  const search = new URLSearchParams();
  search.set("format", params.format ?? "csv");
  if (typeof params.limit === "number") {
    search.set("limit", String(params.limit));
  }
  if (typeof params.actorUserId === "number") {
    search.set("actor_user_id", String(params.actorUserId));
  }
  if (params.actionType) {
    search.set("action_type", params.actionType);
  }
  if (params.entityType) {
    search.set("entity_type", params.entityType);
  }
  if (params.entityId) {
    search.set("entity_id", params.entityId);
  }
  if (params.correlationId) {
    search.set("correlation_id", params.correlationId);
  }
  if (params.startTimestamp) {
    search.set("start_timestamp", params.startTimestamp);
  }
  if (params.endTimestamp) {
    search.set("end_timestamp", params.endTimestamp);
  }

  const response = await fetch(`${baseUrl}/api/v1/audit/events/export?${search.toString()}`, {
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
  if (!response.ok) {
    throw new Error(`Audit export failed: ${response.status}`);
  }
  return response.blob();
}

export function useConnectorDefinitions(token?: string) {
  return useQuery({
    queryKey: ["connector-definitions", token],
    queryFn: () => apiFetch<ConnectorDefinition[]>("/api/v1/admin/connectors", { token }),
    enabled: !!token,
  });
}

export function useConnectorSubmissions(
  token?: string,
  params?: { connectorKey?: string; status?: string; limit?: number },
) {
  const search = new URLSearchParams();
  if (params?.connectorKey) {
    search.set("connector_key", params.connectorKey);
  }
  if (params?.status) {
    search.set("status", params.status);
  }
  if (params?.limit) {
    search.set("limit", String(params.limit));
  }
  const suffix = search.size > 0 ? `?${search.toString()}` : "";
  return useQuery({
    queryKey: ["connector-submissions", token, params?.connectorKey, params?.status, params?.limit],
    queryFn: () => apiFetch<ConnectorSubmission[]>(`/api/v1/admin/connectors/submissions${suffix}`, { token }),
    enabled: !!token,
  });
}

export function useConnectorApprovals(
  token?: string,
  params?: { connectorKey?: string; status?: string; limit?: number },
) {
  const search = new URLSearchParams();
  if (params?.connectorKey) {
    search.set("connector_key", params.connectorKey);
  }
  if (params?.status) {
    search.set("status", params.status);
  }
  if (params?.limit) {
    search.set("limit", String(params.limit));
  }
  const suffix = search.size > 0 ? `?${search.toString()}` : "";
  return useQuery({
    queryKey: ["connector-approvals", token, params?.connectorKey, params?.status, params?.limit],
    queryFn: () => apiFetch<ConnectorApprovalWorkflow[]>(`/api/v1/admin/connectors/approvals${suffix}`, { token }),
    enabled: !!token,
  });
}

export async function ingestConnector(
  token: string | undefined,
  connectorKey: string,
  payload: { limit?: number; dry_run?: boolean },
) {
  return apiFetch<ConnectorIngestionResponse>(`/api/v1/admin/connectors/${connectorKey}/ingest`, {
    token,
    method: "POST",
    body: payload,
  });
}

export async function approveConnectorSubmission(token: string | undefined, workflowId: number, notes?: string) {
  return apiFetch<ConnectorApprovalDecision>(`/api/v1/admin/connectors/approvals/${workflowId}/approve`, {
    token,
    method: "POST",
    body: { notes },
  });
}

export async function rejectConnectorSubmission(token: string | undefined, workflowId: number, notes?: string) {
  return apiFetch<ConnectorApprovalDecision>(`/api/v1/admin/connectors/approvals/${workflowId}/reject`, {
    token,
    method: "POST",
    body: { notes },
  });
}

export function useProvincialOverview(token?: string) {
  return useQuery({
    queryKey: [...dashboardKeys.provincial, token],
    queryFn: () => apiFetch<ProvincialOverview>("/api/v1/dashboard/provincial/overview", { token }),
    enabled: !!token,
  });
}

export function useWarehousesOverview(token?: string) {
  return useQuery({
    queryKey: [...dashboardKeys.warehouses, token],
    queryFn: () => apiFetch<WarehouseOverviewRow[]>("/api/v1/dashboard/warehouses/overview", { token }),
    enabled: !!token,
  });
}

export function usePricesOverview(token?: string) {
  return useQuery({
    queryKey: [...dashboardKeys.prices, token],
    queryFn: () => apiFetch<Record<string, unknown>>("/api/v1/dashboard/prices/overview", { token }),
    enabled: !!token,
  });
}

export function useImportsOverview(token?: string) {
  return useQuery({
    queryKey: [...dashboardKeys.imports, token],
    queryFn: () => apiFetch<Record<string, unknown>>("/api/v1/dashboard/imports/overview", { token }),
    enabled: !!token,
  });
}

export function useAlerts(token?: string) {
  return useQuery({
    queryKey: ["alerts", token],
    queryFn: () => apiFetch<AlertItem[]>("/api/v1/alerts", { token }),
    enabled: !!token,
  });
}

export function useAnomalies(token?: string) {
  return useQuery({
    queryKey: ["anomalies", token],
    queryFn: () => apiFetch<AnomalyEvent[]>("/api/v1/anomalies", { token }),
    enabled: !!token,
  });
}

export function useAnomalyThresholds(token?: string) {
  return useQuery({
    queryKey: ["anomaly-thresholds", token],
    queryFn: () => apiFetch<AnomalyThresholdConfig[]>("/api/v1/anomalies/thresholds", { token }),
    enabled: !!token,
  });
}

export function useAnomalyThresholdVersions(token: string | undefined, anomalyType: string | undefined) {
  return useQuery({
    queryKey: ["anomaly-threshold-versions", token, anomalyType],
    queryFn: () =>
      apiFetch<AnomalyThresholdVersion[]>(`/api/v1/anomalies/thresholds/${anomalyType}/versions?limit=25`, {
        token,
      }),
    enabled: !!token && !!anomalyType,
  });
}

export async function updateAnomalyThreshold(
  token: string | undefined,
  anomalyType: string,
  thresholds: Record<string, number | boolean>,
  reason: string,
) {
  return apiFetch<AnomalyThresholdConfig>(`/api/v1/anomalies/thresholds/${anomalyType}`, {
    token,
    method: "POST",
    body: { thresholds, reason },
  });
}

export function useImports(token?: string) {
  return useQuery({
    queryKey: ["imports", token],
    queryFn: () => apiFetch<ImportRecord[]>("/api/v1/imports", { token }),
    enabled: !!token,
  });
}

export function useForecastLatest(token?: string) {
  return useQuery({
    queryKey: ["forecast-latest", token],
    queryFn: () => apiFetch<ForecastLatestResponse>("/api/v1/forecasting/latest", { token }),
    enabled: !!token,
  });
}

export function useForecastDiagnostics(token?: string) {
  return useQuery({
    queryKey: ["forecast-diagnostics", token],
    queryFn: () => apiFetch<ForecastDiagnostics>("/api/v1/forecasting/diagnostics/latest", { token }),
    enabled: !!token,
  });
}

export async function syncMobileBatch(token: string | undefined, payload: MobileSyncRequest) {
  return apiFetch<MobileSyncResponse>("/api/v1/production/mobile-sync", {
    token,
    method: "POST",
    body: payload,
  });
}

export function useMobileSubmissionHistory(token?: string, params?: { status?: string; syncBatchId?: string; limit?: number }) {
  const search = new URLSearchParams();
  if (params?.status) {
    search.set("status", params.status);
  }
  if (params?.syncBatchId) {
    search.set("sync_batch_id", params.syncBatchId);
  }
  if (params?.limit) {
    search.set("limit", String(params.limit));
  }
  const suffix = search.size > 0 ? `?${search.toString()}` : "";

  return useQuery({
    queryKey: ["mobile-submission-history", token, params?.status, params?.syncBatchId, params?.limit],
    queryFn: () => apiFetch<MobileSubmissionRecord[]>(`/api/v1/production/mobile-sync/submissions${suffix}`, { token }),
    enabled: !!token,
  });
}

export function useReports(token?: string) {
  return useQuery({
    queryKey: ["reports", token],
    queryFn: () => apiFetch<ReportRecord[]>("/api/v1/reports", { token }),
    enabled: !!token,
  });
}

export function useReportRecipientGroups(token?: string, activeOnly = false) {
  const suffix = activeOnly ? "?active_only=true" : "";
  return useQuery({
    queryKey: ["report-recipient-groups", token, activeOnly],
    queryFn: () => apiFetch<ReportRecipientGroup[]>(`/api/v1/reports/distribution/groups${suffix}`, { token }),
    enabled: !!token,
  });
}

export function useDistributionDeliveries(token?: string, status?: string, limit = 100) {
  const params = new URLSearchParams();
  if (status) {
    params.set("status", status);
  }
  params.set("limit", String(limit));
  return useQuery({
    queryKey: ["report-distribution-deliveries", token, status, limit],
    queryFn: () => apiFetch<ReportDeliveryLog[]>(`/api/v1/reports/distribution/deliveries?${params.toString()}`, { token }),
    enabled: !!token,
  });
}

export function useReportDeliveries(token: string | undefined, reportId: number | undefined, status?: string, limit = 100) {
  const params = new URLSearchParams();
  if (status) {
    params.set("status", status);
  }
  params.set("limit", String(limit));
  return useQuery({
    queryKey: ["report-deliveries", token, reportId, status, limit],
    queryFn: () => apiFetch<ReportDeliveryLog[]>(`/api/v1/reports/${reportId}/deliveries?${params.toString()}`, { token }),
    enabled: !!token && typeof reportId === "number",
  });
}

export async function processReportDistributionQueue(token: string | undefined, limit = 50) {
  return apiFetch<ReportDeliveryProcessResult>(`/api/v1/reports/distribution/process?limit=${limit}`, {
    token,
    method: "POST",
  });
}

export async function queueReportDistribution(token: string | undefined, reportId: number) {
  return apiFetch<{ report_id: number; queued_count: number; skipped_count: number; group_count: number }>(
    `/api/v1/reports/${reportId}/distribution/queue`,
    {
      token,
      method: "POST",
    },
  );
}

export function useDocuments(token?: string) {
  return useQuery({
    queryKey: ["documents", token],
    queryFn: () => apiFetch<KnowledgeDocument[]>("/api/v1/documents", { token }),
    enabled: !!token,
  });
}

export function useDocumentIngestionJobs(token?: string, documentId?: number) {
  const suffix = documentId ? `?document_id=${documentId}` : "";
  return useQuery({
    queryKey: ["document-ingestion-jobs", token, documentId],
    queryFn: () => apiFetch<DocumentIngestionJob[]>(`/api/v1/documents/jobs${suffix}`, { token }),
    enabled: !!token,
  });
}

export async function processDocumentQueue(token: string | undefined, limit = 4) {
  return apiFetch<{ processed_jobs: DocumentIngestionJob[]; processed_count: number }>(`/api/v1/documents/jobs/process?limit=${limit}`, {
    token,
    method: "POST",
  });
}

export async function searchDocuments(token: string | undefined, query: string, topK = 5) {
  return apiFetch<{ query: string; results: DocumentSearchResult[] }>("/api/v1/documents/search", {
    token,
    method: "POST",
    body: { query, top_k: topK },
  });
}

export async function login(email: string, password: string) {
  return apiFetch<{ access_token: string; token_type: string; expires_in_minutes: number; auth_source?: string; mfa_verified?: boolean }>(
    "/api/v1/auth/login",
    {
      method: "POST",
      body: { email, password },
    },
  );
}

export async function oidcLogin(idToken: string) {
  return apiFetch<{ access_token: string; token_type: string; expires_in_minutes: number; auth_source?: string; mfa_verified?: boolean }>(
    "/api/v1/auth/oidc/login",
    {
      method: "POST",
      body: { id_token: idToken },
    },
  );
}

export async function currentUser(token: string) {
  return apiFetch<{ user: Record<string, unknown> }>("/api/v1/auth/me", { token });
}

export async function getReportExportMetadata(token: string | undefined, reportId: number, format: "csv" | "pdf") {
  return apiFetch<ReportExportMetadata>(`/api/v1/reports/${reportId}/export/${format}`, { token });
}

export async function downloadReportFile(token: string | undefined, reportId: number, format: "csv" | "pdf") {
  const response = await fetch(`${baseUrl}/api/v1/reports/${reportId}/download/${format}`, {
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
  if (!response.ok) {
    throw new Error(`Report download failed: ${response.status}`);
  }
  return response.blob();
}
