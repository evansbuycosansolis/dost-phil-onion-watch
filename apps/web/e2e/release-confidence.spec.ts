import { expect, Page, test } from "@playwright/test";

type SeededRole = {
  email: string;
  role: string;
  hasAdminNav: boolean;
};

const SEEDED_ROLES: SeededRole[] = [
  { email: "super_admin@onionwatch.ph", role: "super_admin", hasAdminNav: true },
  { email: "provincial_admin@onionwatch.ph", role: "provincial_admin", hasAdminNav: true },
  { email: "municipal_encoder@onionwatch.ph", role: "municipal_encoder", hasAdminNav: false },
  { email: "warehouse_operator@onionwatch.ph", role: "warehouse_operator", hasAdminNav: false },
  { email: "market_analyst@onionwatch.ph", role: "market_analyst", hasAdminNav: false },
  { email: "policy_reviewer@onionwatch.ph", role: "policy_reviewer", hasAdminNav: false },
  { email: "executive_viewer@onionwatch.ph", role: "executive_viewer", hasAdminNav: false },
  { email: "auditor@onionwatch.ph", role: "auditor", hasAdminNav: true },
];

const DEFAULT_PASSWORD = "ChangeMe123!";
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? `http://127.0.0.1:${process.env.PLAYWRIGHT_API_PORT ?? "8011"}`;

async function loginAs(page: Page, email: string) {
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "DOST Phil Onion Watch" })).toBeVisible();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(DEFAULT_PASSWORD);

  const loginResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().includes("/api/v1/auth/login"),
  );
  await page.getByRole("button", { name: "Sign in" }).click();
  const loginResponse = await loginResponsePromise;
  expect(loginResponse.status(), `Login failed for ${email} via ${loginResponse.url()}`).toBe(200);
  await expect(page).toHaveURL(/\/dashboard\/provincial$/);
  await expect(page.getByRole("heading", { name: "Provincial Command Dashboard" })).toBeVisible();
}

async function signOut(page: Page) {
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);
}

test("seeded roles can login and receive role-aware navigation", async ({ page }) => {
  for (const role of SEEDED_ROLES) {
    await loginAs(page, role.email);
    await expect(page.locator("aside")).toContainText(role.role);

    const adminNavLink = page.getByRole("link", { name: "Admin", exact: true });
    if (role.hasAdminNav) {
      await expect(adminNavLink).toBeVisible();
    } else {
      await expect(adminNavLink).toHaveCount(0);
    }

    await signOut(page);
  }
});

test("super admin dashboard navigation routes load successfully", async ({ page }) => {
  await loginAs(page, "super_admin@onionwatch.ph");

  const routes = [
    { label: "Provincial", path: /\/dashboard\/provincial$/, heading: "Provincial Command Dashboard" },
    { label: "Municipal", path: /\/dashboard\/municipal$/, heading: "Municipal Dashboard" },
    { label: "Warehouses", path: /\/dashboard\/warehouses$/, heading: "Warehouses Dashboard" },
    { label: "Prices", path: /\/dashboard\/prices$/, heading: "Prices Dashboard" },
    { label: "Imports", path: /\/dashboard\/imports$/, heading: "Imports Dashboard" },
    { label: "Alerts", path: /\/dashboard\/alerts$/, heading: "Alerts Center" },
    { label: "Knowledge", path: /\/dashboard\/knowledge$/, heading: "Knowledge Center" },
    { label: "Reports", path: /\/dashboard\/reports$/, heading: "Reports Center" },
    { label: "Admin", path: /\/dashboard\/admin$/, heading: "Admin Console" },
  ];

  for (const route of routes) {
    await page.getByRole("link", { name: route.label, exact: true }).click();
    await expect(page).toHaveURL(route.path);
    await expect(page.getByRole("heading", { name: route.heading })).toBeVisible();
  }
});

test("alerts page supports acknowledge and resolve flow", async ({ page }) => {
  await loginAs(page, "super_admin@onionwatch.ph");
  await page.getByRole("link", { name: "Alerts", exact: true }).click();
  await expect(page).toHaveURL(/\/dashboard\/alerts$/);
  await expect(page.getByRole("heading", { name: "Alerts Center" })).toBeVisible();

  const firstAck = page.getByRole("button", { name: "Ack" }).first();
  await expect(firstAck).toBeVisible();

  const acknowledgeResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/api/v1/alerts/") &&
      response.url().includes("/acknowledge") &&
      response.request().method() === "POST",
  );
  await firstAck.click();
  const acknowledgeResult = await acknowledgeResponse;
  expect(acknowledgeResult.status()).toBe(200);

  const firstResolve = page.getByRole("button", { name: "Resolve" }).first();
  await expect(firstResolve).toBeVisible();
  const resolveResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/api/v1/alerts/") &&
      response.url().includes("/resolve") &&
      response.request().method() === "POST",
  );
  await firstResolve.click();
  const resolveResult = await resolveResponse;
  expect(resolveResult.status()).toBe(200);

  await expect(page.locator("text=resolved").first()).toBeVisible();
});

test("reports page supports CSV and PDF export flow", async ({ page }) => {
  await loginAs(page, "super_admin@onionwatch.ph");
  await page.getByRole("link", { name: "Reports", exact: true }).click();
  await expect(page).toHaveURL(/\/dashboard\/reports$/);
  await expect(page.getByRole("heading", { name: "Reports Center" })).toBeVisible();

  const token = await page.evaluate(() => window.localStorage.getItem("pow_token"));
  expect(token).toBeTruthy();

  const reportSeedResponse = await page.request.post(`${API_BASE_URL}/api/v1/reports/generate`, {
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    data: {
      category: "price_trend",
      reporting_month: new Date().toISOString().slice(0, 10),
    },
  });
  expect(reportSeedResponse.status()).toBe(200);

  await page.reload();

  const csvButton = page.getByRole("button", { name: "CSV" }).first();
  await expect(csvButton).toBeVisible();
  const csvResponsePromise = page.waitForResponse(
    (response) =>
      response.url().includes("/api/v1/reports/") &&
      response.url().includes("/download/csv") &&
      response.request().method() === "GET",
  );
  await csvButton.click();
  const csvResponse = await csvResponsePromise;
  expect(csvResponse.status()).toBe(200);
  expect(csvResponse.headers()["content-type"] ?? "").toContain("text/csv");

  const pdfButton = page.getByRole("button", { name: "PDF" }).first();
  await expect(pdfButton).toBeVisible();
  const pdfResponsePromise = page.waitForResponse(
    (response) =>
      response.url().includes("/api/v1/reports/") &&
      response.url().includes("/download/pdf") &&
      response.request().method() === "GET",
  );
  await pdfButton.click();
  const pdfResponse = await pdfResponsePromise;
  expect(pdfResponse.status()).toBe(200);
  expect(pdfResponse.headers()["content-type"] ?? "").toContain("application/pdf");
});

test("geo ops monthly KPI automation computes status and creates review task", async ({ page }) => {
  await loginAs(page, "super_admin@onionwatch.ph");
  await page.getByRole("link", { name: "Geo Ops", exact: true }).click();
  await expect(page).toHaveURL(/\/dashboard\/ops\/geospatial\/rollout$/);
  await page.getByRole("link", { name: "KPI Scorecards", exact: true }).click();
  await expect(page).toHaveURL(/\/dashboard\/ops\/geospatial\/kpi$/);
  await expect(page.getByRole("heading", { name: "Geospatial KPI Scorecards" })).toBeVisible();

  const token = await page.evaluate(() => window.localStorage.getItem("pow_token"));
  expect(token).toBeTruthy();
  const periodMonth = await page.getByLabel("Period Month").inputValue();
  const automationResponse = await page.request.post(`${API_BASE_URL}/api/v1/geospatial/automation/monthly-kpi?reporting_month=${periodMonth}`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
  expect(automationResponse.status()).toBe(200);
  const automationPayload = await automationResponse.json();
  expect(["green", "yellow", "red"]).toContain(automationPayload.computed_status);

  await page.reload();
  await expect(page.getByText("Overall Status")).toBeVisible();
  await expect(page.getByText("Review geospatial KPI scorecard")).toBeVisible();
});
