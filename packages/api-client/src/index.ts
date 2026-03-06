"use client";

import { useQuery } from "@tanstack/react-query";
import { apiConfig } from "@phil-onion-watch/config";
import type {
  AlertItem,
  AnomalyEvent,
  DocumentSearchResult,
  ForecastOutput,
  ImportRecord,
  ProvincialOverview,
  ReportExportMetadata,
  ReportRecord,
  WarehouseOverviewRow,
} from "@phil-onion-watch/types";

const baseUrl = apiConfig.baseUrl;

export type ApiClientOptions = {
  token?: string;
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
    queryFn: () => apiFetch<{ run: Record<string, unknown>; outputs: ForecastOutput[] }>("/api/v1/forecasting/latest", { token }),
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

export function useDocuments(token?: string) {
  return useQuery({
    queryKey: ["documents", token],
    queryFn: () => apiFetch<Record<string, unknown>[]>("/api/v1/documents", { token }),
    enabled: !!token,
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
  return apiFetch<{ access_token: string; token_type: string }>("/api/v1/auth/login", {
    method: "POST",
    body: { email, password },
  });
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
