import { expect, Page, test } from "@playwright/test";

const DEFAULT_PASSWORD = "ChangeMe123!";

async function loginAs(page: Page, email: string) {
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "DOST Phil Onion Watch" })).toBeVisible();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(DEFAULT_PASSWORD);

  const loginResponsePromise = page.waitForResponse(
    (response) => response.request().method() === "POST" && response.url().includes("/api/v1/auth/login"),
  );
  await page.getByRole("button", { name: "Sign in" }).click();
  const loginResponse = await loginResponsePromise;
  expect(loginResponse.status()).toBe(200);
  await expect(page).toHaveURL(/\/dashboard\/provincial$/);
}

test("super admin can validate, create, inspect, edit, and deactivate AOIs", async ({ page }) => {
  const uniqueCode = `PW-AOI-${Date.now()}`;
  const initialName = `Playwright AOI ${Date.now()}`;
  const updatedName = `${initialName} Updated`;

  await loginAs(page, "super_admin@onionwatch.ph");
  await page.getByRole("link", { name: "Geospatial", exact: true }).click();
  await expect(page).toHaveURL(/\/dashboard\/geospatial\/aois$/);
  await expect(page.getByRole("heading", { name: "Geospatial AOIs" })).toBeVisible();
  await expect(page.getByText("Pipeline Controls and Runs")).toBeVisible();
  await expect(page.getByText("Recent pipeline runs")).toBeVisible();

  const recomputeResponse = page.waitForResponse(
    (response) => response.request().method() === "POST" && response.url().includes("/api/v1/geospatial/features/recompute"),
  );
  await page.getByRole("button", { name: "Queue feature recompute", exact: true }).click();
  expect((await recomputeResponse).status()).toBe(200);
  await expect(page.getByTestId("selected-run-details")).toContainText("Selected run details");
  await expect(page.getByTestId("selected-run-details")).toContainText("Scene provenance");
  await page.getByRole("link", { name: "Open drilldown" }).click();
  await expect(page).toHaveURL(/\/dashboard\/geospatial\/runs\/\d+$/);
  await expect(page.getByRole("heading", { name: /Geospatial Run #/ })).toBeVisible();
  await page.getByRole("link", { name: "Artifact center" }).click();
  await expect(page).toHaveURL(/\/dashboard\/geospatial\/runs\/\d+\/artifacts$/);
  await expect(page.getByRole("heading", { name: /Artifact Download Center/ })).toBeVisible();
  await page.getByRole("link", { name: "Back to run" }).click();
  await expect(page).toHaveURL(/\/dashboard\/geospatial\/runs\/\d+$/);
  await expect(page.getByText("Scene provenance")).toBeVisible();
  await expect(page.getByText("Feature provenance")).toBeVisible();
  await page.evaluate(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: async () => undefined },
    });
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: () => "blob:playwright",
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: () => undefined,
    });
  });
  await page.getByRole("button", { name: "Copy share link" }).click();
  await expect(page.getByRole("status")).toContainText("Link copied");
  await page.getByRole("button", { name: "Export scene CSV" }).click();
  await expect(page.getByRole("status")).toContainText(/Scene CSV exported/i);
  await page.getByLabel("Scene search").fill("sentinel");
  await page.getByLabel("Sort by").first().selectOption("source");
  await expect(page).toHaveURL(/scene_search=sentinel/);
  await expect(page).toHaveURL(/scene_sort_by=source/);
  await page.getByRole("button", { name: "Reset scene filters" }).click();
  await expect(page.getByLabel("Scene search")).toHaveValue("");
  await expect(page.getByLabel("Sort by").first()).toHaveValue("acquired_at");
  await page.getByLabel("Scene search").fill("sentinel");
  await page.getByLabel("Sort by").first().selectOption("source");
  await page.reload();
  await expect(page.getByLabel("Scene search")).toHaveValue("sentinel");
  await expect(page.getByLabel("Sort by").first()).toHaveValue("source");
  await expect(page.getByTestId("run-scenes-table")).toBeVisible();
  await page.getByRole("button", { name: "Preview" }).first().click();
  await expect(page.getByTestId("scene-preview-drawer")).toBeVisible();
  await page.getByRole("button", { name: "Close" }).click();
  const observationHistoryLink = page.getByRole("link", { name: "Observation history" }).first();
  await expect(observationHistoryLink).toBeVisible();
  await observationHistoryLink.click();
  await expect(page).toHaveURL(/\/dashboard\/geospatial\/aois\?/);
  await expect(page.getByTestId("selected-aoi-insights")).toBeVisible();
  await expect(page.getByText("Deep-linked context active for AOI")).toBeVisible();
  await expect(page.getByText(/Scene ID:/i)).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(/\/dashboard\/geospatial\/runs\/\d+\?/);
  await expect(page.getByLabel("Scene search")).toHaveValue("sentinel");
  await page.getByLabel("Feature search").fill("sentinel");
  await expect(page).toHaveURL(/feature_search=sentinel/);
  await page.reload();
  await expect(page.getByLabel("Feature search")).toHaveValue("sentinel");
  await expect(page.getByTestId("run-features-table")).toBeVisible();
  await page.getByRole("button", { name: "Preview" }).nth(1).click();
  await expect(page.getByTestId("feature-preview-drawer")).toBeVisible();
  await page.getByRole("button", { name: "Close" }).click();
  await page.getByRole("button", { name: "Export feature CSV" }).click();
  await expect(page.getByRole("status")).toContainText(/Feature CSV exported/i);
  await page.getByRole("button", { name: "Reset feature filters" }).click();
  await expect(page.getByLabel("Feature search")).toHaveValue("");
  await page.getByRole("link", { name: "Back to geospatial" }).click();
  await expect(page).toHaveURL(/\/dashboard\/geospatial\/aois\?/);
  await expect(page.getByTestId("saved-drilldown-context-hint")).toBeVisible();
  await expect(page.getByRole("link", { name: "Open drilldown" })).toHaveAttribute("href", /feature_search=sentinel/);
  await page.getByRole("link", { name: "Open drilldown" }).click();
  await expect(page).toHaveURL(/scene_search=sentinel/);
  await expect(page).toHaveURL(/feature_search=sentinel/);
  await page.getByRole("link", { name: "Back to geospatial" }).click();
  await expect(page).toHaveURL(/\/dashboard\/geospatial\/aois\?/);
  await page.getByRole("link", { name: "Geospatial", exact: true }).click();
  await expect(page).toHaveURL(/\/dashboard\/geospatial\/aois$/);

  await expect(page.getByRole("button", { name: "Inspect OM-SJ-DEMO-AOI" })).toBeVisible();
  await page.getByRole("button", { name: "Inspect OM-SJ-DEMO-AOI" }).click();
  await expect(page.getByText("Timeline and layers")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Recent observations" })).toBeVisible();

  const createSection = page.locator("section").filter({ hasText: "Create AOI" }).first();
  await createSection.getByRole("button", { name: "Create AOI geometry: clear polygon" }).click();
  await expect(createSection.getByText("Polygon needs at least 3 vertices.")).toBeVisible();
  await expect(createSection.getByRole("button", { name: "Create AOI", exact: true })).toBeDisabled();
  await createSection.getByRole("button", { name: "Create AOI geometry: reset polygon" }).click();

  await createSection.getByLabel("Create AOI code").fill(uniqueCode);
  await createSection.getByLabel("Create AOI name").fill(initialName);
  await createSection.getByLabel("Create AOI description").fill("Created by Playwright for AOI flow coverage");

  const createResponse = page.waitForResponse(
    (response) => response.request().method() === "POST" && response.url().includes("/api/v1/geospatial/aois"),
  );
  await createSection.getByRole("button", { name: "Create AOI", exact: true }).click();
  expect((await createResponse).status()).toBe(200);

  const createdRow = page.locator("tr", { hasText: uniqueCode });
  await expect(createdRow).toBeVisible();

  await createdRow.getByRole("button", { name: `Edit ${uniqueCode}` }).click();
  const editSection = page.locator("section").filter({ hasText: "Edit AOI" }).first();
  await expect(editSection.getByText(/Editing AOI #/)).toBeVisible();
  await editSection.getByLabel("Edit AOI name").fill(updatedName);
  await editSection.getByRole("button", { name: "Edit AOI geometry: add point" }).click();

  const updateResponse = page.waitForResponse(
    (response) => response.request().method() === "PUT" && response.url().includes("/api/v1/geospatial/aois/"),
  );
  await editSection.getByRole("button", { name: "Save changes", exact: true }).click();
  expect((await updateResponse).status()).toBe(200);
  await expect(page.locator("tr", { hasText: updatedName })).toBeVisible();

  await page.locator("tr", { hasText: uniqueCode }).getByRole("button", { name: `Inspect ${uniqueCode}` }).click();
  await expect(page.getByTestId("selected-aoi-insights").getByText(uniqueCode)).toBeVisible();

  const deactivateResponse = page.waitForResponse(
    (response) => response.request().method() === "DELETE" && response.url().includes("/api/v1/geospatial/aois/"),
  );
  await page.locator("tr", { hasText: uniqueCode }).getByRole("button", { name: `Deactivate ${uniqueCode}` }).click();
  expect((await deactivateResponse).status()).toBe(200);
  await expect(page.locator("tr", { hasText: uniqueCode })).toHaveCount(0);

  await page.getByLabel("Include inactive AOIs").check();
  const inactiveRow = page.locator("tr", { hasText: uniqueCode });
  await expect(inactiveRow).toBeVisible();
  await expect(inactiveRow).toContainText("no");
});
