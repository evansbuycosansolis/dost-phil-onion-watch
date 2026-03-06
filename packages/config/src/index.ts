import { z } from "zod";

export const envSchema = z.object({
  NEXT_PUBLIC_API_BASE_URL: z.string().url().default("http://localhost:8000"),
  NEXT_PUBLIC_ENABLE_AI_SUMMARY: z
    .union([z.literal("true"), z.literal("false")])
    .transform((value) => value === "true")
    .default("true"),
});

export type AppEnv = z.infer<typeof envSchema>;

export const featureFlags = {
  knowledgeCenter: true,
  reportsCenter: true,
  aiSummary: true,
};

export const routes = {
  login: "/login",
  dashboardProvincial: "/dashboard/provincial",
  dashboardMunicipal: "/dashboard/municipal",
  dashboardWarehouses: "/dashboard/warehouses",
  dashboardPrices: "/dashboard/prices",
  dashboardImports: "/dashboard/imports",
  dashboardAlerts: "/dashboard/alerts",
  dashboardKnowledge: "/dashboard/knowledge",
  dashboardReports: "/dashboard/reports",
  dashboardAdmin: "/dashboard/admin",
} as const;

const envProcess =
  (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env ?? {};

export const apiConfig = {
  baseUrl: envProcess.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
  timeoutMs: 20000,
};
