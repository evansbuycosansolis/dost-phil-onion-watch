import { z } from "zod";

declare const process: { env?: Record<string, string | undefined> } | undefined;

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
  dashboardGeospatial: "/dashboard/geospatial",
  dashboardGeospatialAOIs: "/dashboard/geospatial/aois",
  dashboardGeospatialExecutive: "/dashboard/geospatial/executive",
  dashboardGeospatialIntelligence: "/dashboard/geospatial/intelligence",
  dashboardAdmin: "/dashboard/admin",
} as const;

const parsedEnv = envSchema.parse({
  NEXT_PUBLIC_API_BASE_URL:
    typeof process !== "undefined" ? process.env?.NEXT_PUBLIC_API_BASE_URL : undefined,
  NEXT_PUBLIC_ENABLE_AI_SUMMARY:
    typeof process !== "undefined" ? process.env?.NEXT_PUBLIC_ENABLE_AI_SUMMARY : undefined,
});

export const apiConfig = {
  baseUrl: parsedEnv.NEXT_PUBLIC_API_BASE_URL,
  timeoutMs: 20000,
};
