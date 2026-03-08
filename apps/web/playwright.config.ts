import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

const isCI = !!process.env.CI;
const apiCwd = path.resolve(__dirname, "../api");
const apiPort = process.env.PLAYWRIGHT_API_PORT ?? "8011";
const webPort = process.env.PLAYWRIGHT_WEB_PORT ?? "3100";
const runId = process.env.PLAYWRIGHT_RUN_ID ?? `${Date.now()}`;
const apiBaseUrl = `http://127.0.0.1:${apiPort}`;
const webBaseUrl = `http://127.0.0.1:${webPort}`;

export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: {
    timeout: 15_000,
  },
  workers: 1,
  retries: isCI ? 1 : 0,
  reporter: isCI ? [["github"], ["html", { open: "never" }]] : [["list"]],
  use: {
    baseURL: webBaseUrl,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      command: `python -m uvicorn app.main:app --host 127.0.0.1 --port ${apiPort}`,
      cwd: apiCwd,
      url: `${apiBaseUrl}/health`,
      reuseExistingServer: !isCI,
      timeout: 240_000,
      env: {
        ...process.env,
        DATABASE_URL: `sqlite+pysqlite:///./e2e-web-${runId}.db`,
        FAISS_INDEX_PATH: `./e2e-web-${runId}.index`,
        FAISS_METADATA_PATH: `./e2e-web-${runId}-meta.json`,
        REPORTS_PATH: `./e2e-web-${runId}-reports`,
        SECRET_KEY: process.env.SECRET_KEY ?? "e2e-secret",
        OIDC_ENABLED: "false",
        ENFORCE_OIDC_FOR_PRIVILEGED_ROLES: "false",
        ENFORCE_MFA_FOR_PRIVILEGED_TOKENS: "false",
      },
    },
    {
      command: `pnpm exec next dev --hostname 127.0.0.1 --port ${webPort}`,
      cwd: __dirname,
      url: `${webBaseUrl}/login`,
      reuseExistingServer: !isCI,
      timeout: 240_000,
      env: {
        ...process.env,
        NEXT_PUBLIC_API_BASE_URL: apiBaseUrl,
      },
    },
  ],
});
