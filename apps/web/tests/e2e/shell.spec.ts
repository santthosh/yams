import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fixtures from "../transport-fixtures.json" with { type: "json" };
const apiPort = Number(process.env.YAMS_E2E_API_PORT || 3118);
test.beforeEach(async ({ request }) => {
  const response = await request.post(`http://127.0.0.1:${apiPort}/__control`, {
    data: { mode: "ready" },
  });
  expect(response.ok()).toBe(true);
});
test("foundation navigation, keyboard and modal at each viewport", async ({
  page,
}, info) => {
  const errors: string[] = [];
  const destinations: string[] = [];
  page.on("request", (request) =>
    destinations.push(new URL(request.url()).origin),
  );
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(page.getByText("Ready to explore")).toBeVisible();
  await expect(page.getByText("Synthetic demo")).toBeVisible();
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await expect(
    page.getByRole("link", { name: "Open paper portfolios →", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: /Arena|Journal|Portfolios/ }),
  ).toHaveCount(0);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: info.outputPath("dashboard.png"),
    fullPage: true,
  });
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("link", { name: "Skip to content" }),
  ).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main-content")).toBeFocused();
  await page.screenshot({
    path: info.outputPath("keyboard-focus.png"),
    fullPage: true,
  });
  const trigger = page.getByRole("button", { name: "About paper research" });
  await trigger.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await expect(dialog.getByRole("button", { name: "Got it" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(dialog.getByRole("button", { name: "Got it" })).toBeFocused();
  await page.screenshot({
    path: info.outputPath("dialog.png"),
    fullPage: false,
  });
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(trigger).toBeFocused();
  if (info.project.name === "mobile") {
    await page.getByText("Navigation", { exact: true }).focus();
    await page.keyboard.press("Enter");
  }
  const settings = page.getByRole("link", {
    name: "Settings & data",
    exact: true,
  });
  await settings.focus();
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("heading", { name: "Settings & data", exact: true }),
  ).toBeVisible();
  await expect(page.getByText(fixtures.workspace.id)).toBeVisible();
  await expect(page.getByLabel("Job ID")).toBeVisible();
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.screenshot({
    path: info.outputPath("settings.png"),
    fullPage: true,
  });
  expect(errors).toEqual([]);
  expect(new Set(destinations)).toEqual(new Set([new URL(page.url()).origin]));
});
test("read-only job lookup polls to a sealed result and handles missing IDs", async ({
  page,
}) => {
  await page.goto("/settings");
  await page.getByLabel("Job ID").fill(fixtures.job.id);
  await page.getByRole("button", { name: "Check status" }).click();
  await expect(
    page.getByRole("heading", { name: "Running", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("progressbar")).toHaveAttribute("value", "25");
  await expect(
    page.getByRole("heading", { name: "Completed", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("A sealed result is available.")).toBeVisible();
  await expect(
    page.getByRole("button", { name: /cancel|retry job/i }),
  ).toHaveCount(0);
  await page.getByLabel("Job ID").fill("44444444-4444-4444-8444-444444444444");
  await page.getByRole("button", { name: "Check status" }).click();
  await expect(page.getByText(/No job found for this ID/)).toBeVisible();
});
test("real proxy timeout is correlated, safe and recoverable", async ({
  page,
  request,
}, info) => {
  await request.post(`http://127.0.0.1:${apiPort}/__control`, {
    data: { mode: "timeout" },
  });
  await page.goto("/");
  await expect(page.getByRole("status")).toContainText("Initializing");
  await page.screenshot({
    path: info.outputPath("loading.png"),
    fullPage: true,
  });
  await expect(page.locator("main").getByRole("alert")).toContainText(
    "Diagnostic ID:",
  );
  await expect(page.getByText("$0.00")).toHaveCount(0);
  await page.screenshot({
    path: info.outputPath("timeout.png"),
    fullPage: true,
  });
  await request.post(`http://127.0.0.1:${apiPort}/__control`, {
    data: { mode: "ready" },
  });
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByText("Ready to explore")).toBeVisible();
});
test("not-ready and raw upstream failure remain useful and sanitized", async ({
  page,
  request,
}, info) => {
  await request.post(`http://127.0.0.1:${apiPort}/__control`, {
    data: { mode: "not_ready" },
  });
  await page.goto("/settings");
  await expect(page.locator("main").getByRole("alert")).toContainText(
    "Some local services are not ready",
  );
  await expect(page.getByText("Source unavailable")).toBeVisible();
  await expect(
    page.getByText("DATABASE_UNAVAILABLE", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: info.outputPath("not-ready.png"),
    fullPage: true,
  });
  await request.post(`http://127.0.0.1:${apiPort}/__control`, {
    data: { mode: "error" },
  });
  await page.getByRole("button", { name: "Refresh status" }).click();
  await expect(page.locator("main").getByRole("alert")).toContainText(
    "33333333-3333-4333-8333-333333333333",
  );
  await expect(
    page.getByText(/RAW_STACK_TRACE|secret_database_password/),
  ).toHaveCount(0);
});
test("unknown pages and proxy destinations are unavailable", async ({
  page,
  request,
}) => {
  const response = await page.goto("/not-a-page");
  expect(response?.status()).toBe(404);
  await expect(
    page.getByRole("heading", { name: "This path is still unexplored." }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Return to Dashboard" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "Your research starts here",
  );
  expect((await request.get("/api/v1/__control")).status()).toBe(404);
  expect((await request.post("/api/v1/workspace")).status()).toBe(405);
  expect(
    (await request.get("/api/v1/health?url=http://example.com")).status(),
  ).toBe(404);
});
