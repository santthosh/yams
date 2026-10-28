import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fixtures from "../transport-fixtures.json" with { type: "json" };

test("data coverage, search, failure retention and source isolation", async ({
  page,
  request,
}, info) => {
  const apiPort = Number(process.env.YAMS_E2E_API_PORT || 3118);
  await request.post(`http://127.0.0.1:${apiPort}/__control`, {
    data: { mode: "ready" },
  });
  let failed = false;
  const snapshot = {
    id: "11111111-1111-4111-8111-111111111111",
    provider: "authored_synthetic_test",
    mode: "synthetic_fixture",
    latest_completed_session: "2030-01-03",
    published_at: "2030-01-04T00:00:00Z",
    quality: "usable_with_warnings",
    warnings: ["SYNTHETIC_DATA_ONLY"],
    asset_count: 1,
    manifest_sha256: "a".repeat(64),
    coverage: {
      asset_ids: ["TEST:AAA"],
      first_session: "2029-01-01",
      last_session: "2030-01-03",
      latest_completed_session: "2030-01-03",
      missing_sessions: [],
      membership_basis: "synthetic",
    },
  };
  await page.route("**/api/v1/data/**", async (route) => {
    const url = new URL(route.request().url());
    const research = url.searchParams.get("mode") === "research_market_data";
    let body: unknown;
    if (url.pathname.endsWith("/health"))
      body = {
        mode: research ? "research_market_data" : "synthetic_fixture",
        checked_at: "2030-01-04T00:00:00Z",
        status: research ? "empty" : failed ? "failed" : "ready",
        current_snapshot: research ? null : snapshot,
        latest_job:
          failed && !research
            ? {
                ...fixtures.job,
                status: "failed",
                progress: 0,
                result: null,
                error: {
                  code: "PROVIDER_UNAVAILABLE",
                  message: "Refresh failed",
                  details: { reason: "PROVIDER_TIMEOUT" },
                  retryable: false,
                  correlation_id: "33333333-3333-4333-8333-333333333333",
                },
              }
            : null,
        warnings: failed ? ["LAST_REFRESH_FAILED"] : [],
        freshness: research
          ? "unknown"
          : failed
            ? "refresh_failed"
            : "synthetic",
      };
    else if (url.pathname.endsWith("/snapshots"))
      body = { items: research ? [] : [snapshot], next_cursor: null };
    else
      body = {
        mode: "synthetic_fixture",
        snapshot_id: snapshot.id,
        items:
          url.searchParams.get("query") === "missing"
            ? []
            : [
                {
                  asset_id: "TEST:AAA",
                  symbol: "AAA",
                  venue: "XNYS",
                  sector: "Unknown",
                  provider: "authored_synthetic_test",
                  provider_id: "AAA",
                  currency: "USD",
                  instrument: "ordinary_equity",
                },
              ],
        next_cursor: null,
      };
    await route.fulfill({ json: body });
  });
  await page.goto("/settings/data");
  await expect(
    page.getByRole("heading", { name: "Market data", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("authored_synthetic_test")).toBeVisible();
  await expect(page.getByText("AAA · XNYS", { exact: false })).toBeVisible();
  await page.getByLabel("Symbol or asset ID").fill("missing");
  await page.getByRole("button", { name: "Search assets" }).click();
  await expect(
    page.getByRole("heading", { name: "No matching assets" }),
  ).toBeVisible();
  failed = true;
  await page.getByRole("button", { name: "Reload data status" }).click();
  await expect(
    page.getByText(
      "Refresh failed. Last valid data is retained and may be stale.",
    ),
  ).toBeVisible();
  await expect(page.getByText("authored_synthetic_test")).toBeVisible();
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: info.outputPath("data-stale.png"),
    fullPage: true,
  });
  await page.getByLabel("Source mode").selectOption("research_market_data");
  await expect(
    page.getByRole("heading", { name: "No registered snapshot" }),
  ).toBeVisible();
  await expect(page.getByText("authored_synthetic_test")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Refresh selected source" }),
  ).toBeDisabled();
  await page.screenshot({
    path: info.outputPath("data-research-empty.png"),
    fullPage: true,
  });
});
