import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import sample from "../candidate-transport.json" with { type: "json" };
import fixtures from "../transport-fixtures.json" with { type: "json" };

async function choices(page: Page) {
  await page.route("**/api/v1/strategies**", (route) =>
    route.fulfill({ json: { items: [sample.strategy], next_cursor: null } }),
  );
  await page.route("**/api/v1/data/snapshots**", (route) => {
    const research =
      new URL(route.request().url()).searchParams.get("mode") ===
      "research_market_data";
    return route.fulfill({
      json: { items: research ? [] : [sample.snapshot], next_cursor: null },
    });
  });
}

test("pinned diagnostics: polling, rerun evidence, keyboard and responsive tables", async ({
  page,
}, info) => {
  await choices(page);
  let reads = 0;
  let submissions = 0;
  let rejectNext = false;
  let identity = sample.completed.id;
  const posts: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST")
      posts.push(new URL(request.url()).pathname);
  });
  await page.route("**/api/v1/strategy-evaluations**", async (route) => {
    if (route.request().method() === "POST") {
      if (rejectNext) {
        rejectNext = false;
        await route.fulfill({
          status: 409,
          json: { error: { code: "STALE_DATA" } },
        });
        return;
      }
      expect(route.request().postDataJSON()).toEqual({
        strategy_version_id: sample.strategy.published_version.id,
        snapshot_id: sample.snapshot.id,
        as_of_session: sample.completed.inputs.as_of_session,
      });
      submissions += 1;
      reads = 0;
      identity =
        submissions === 1
          ? sample.completed.id
          : "77777777-7777-4777-8777-777777777777";
      await route.fulfill({
        status: 202,
        json: { evaluation_id: identity, job_id: sample.completed.job_id },
      });
      return;
    }
    reads += 1;
    await route.fulfill({
      json: {
        ...sample.completed,
        id: identity,
        ...(reads === 1
          ? { status: "running", result: null, result_sha256: null }
          : {}),
      },
    });
  });
  await page.route("**/api/v1/jobs/**", (route) =>
    route.fulfill({
      json: {
        ...fixtures.job,
        id: sample.completed.job_id,
        kind: "evaluate_strategy",
        status: reads < 2 ? "running" : "completed",
        progress: reads < 2 ? 0 : 100,
        result:
          reads < 2
            ? null
            : {
                kind: "resource",
                resource_id: identity,
                message: "Synthetic transport diagnostics completed.",
              },
      },
    }),
  );
  await page.goto("/lab/candidates");
  await expect(
    page.getByRole("combobox", { name: "Snapshot", exact: true }),
  ).toHaveValue(sample.snapshot.id);
  await page
    .getByLabel("As-of session")
    .fill(sample.completed.inputs.as_of_session);
  await page
    .getByRole("combobox", { name: "Strategy version", exact: true })
    .focus();
  await expect(
    page.getByRole("combobox", { name: "Strategy version", exact: true }),
  ).toBeFocused();
  await page.getByRole("button", { name: "Evaluate pinned inputs" }).click();
  await expect(
    page.getByText("The worker is processing pinned inputs.", { exact: false }),
  ).toBeVisible();
  rejectNext = true;
  await page.getByRole("button", { name: "Evaluate pinned inputs" }).click();
  const admissionError = page.getByText(
    "The selected snapshot is blocked or lacks a completed session at that date.",
  );
  await expect(admissionError).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Target allocation", exact: true }),
  ).toBeVisible();
  await expect(admissionError).toBeVisible();
  const targets = page.getByRole("region", { name: "Target allocation table" });
  await expect(
    targets.getByRole("rowheader", { name: "SYN:AAA", exact: true }),
  ).toBeVisible();
  const table = page.getByRole("region", { name: "Candidate evidence table" });
  await table.focus();
  await expect(table).toBeFocused();
  if (info.project.name === "mobile") {
    await page.keyboard.press("ArrowRight");
    await expect
      .poll(() => table.evaluate((element) => element.scrollLeft))
      .toBeGreaterThan(0);
  }
  await page.getByText("Evidence for SYN:AAA", { exact: true }).click();
  await expect(
    table
      .getByRole("rowheader", { name: "SYN:AAA", exact: true })
      .locator("..")
      .getByText('"input_sha256":', { exact: false }),
  ).toBeVisible();
  await page
    .getByText("Strategy rules and reproducibility", { exact: true })
    .click();
  await expect(
    page.getByText(sample.completed.result_sha256, { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Find an asset ID").fill("SYN:ZERO");
  await expect(
    table.getByRole("rowheader", { name: "SYN:ZERO", exact: true }),
  ).toBeVisible();
  await expect(
    table.getByRole("rowheader", { name: "SYN:AAA", exact: true }),
  ).toHaveCount(0);
  await page.getByLabel("Find an asset ID").fill("");
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
    path: info.outputPath("candidate-evidence.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Evaluate pinned inputs" }).click();
  await expect(
    page.getByRole("heading", { name: "Target allocation", exact: true }),
  ).toBeVisible();
  await page
    .getByText("Strategy rules and reproducibility", { exact: true })
    .click();
  await expect(
    page.getByText(sample.completed.result_sha256, { exact: true }),
  ).toBeVisible();
  expect(submissions).toBe(2);
  expect(posts).toEqual([
    "/api/v1/strategy-evaluations",
    "/api/v1/strategy-evaluations",
    "/api/v1/strategy-evaluations",
  ]);
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Target allocation", exact: true }),
  ).toBeVisible();
});

test("cash-only, failed, unknown, stale and research-empty states remain explicit", async ({
  page,
}, info) => {
  await choices(page);
  const failedId = "77777777-7777-4777-8777-777777777777";
  const error = {
    code: "INSUFFICIENT_MARKET_DATA",
    message: "Synthetic test failure",
    details: {},
    retryable: false,
    correlation_id: "33333333-3333-4333-8333-333333333333",
  };
  await page.route("**/api/v1/strategy-evaluations**", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({
        status: 409,
        json: { error: { ...error, code: "STALE_DATA" } },
      });
      return;
    }
    const identity = new URL(route.request().url()).pathname.split("/").at(-1);
    if (identity === sample.empty.id)
      await route.fulfill({ json: sample.empty });
    else if (identity === failedId)
      await route.fulfill({
        json: {
          ...sample.empty,
          id: failedId,
          status: "failed",
          result: null,
          result_sha256: null,
          error,
        },
      });
    else
      await route.fulfill({
        status: 404,
        json: { error: { ...error, code: "NOT_FOUND" } },
      });
  });
  await page.route("**/api/v1/jobs/**", (route) =>
    route.fulfill({
      json: {
        ...fixtures.job,
        status: "completed",
        progress: 100,
        result: {
          kind: "resource",
          resource_id: sample.empty.id,
          message: "Synthetic transport completion.",
        },
      },
    }),
  );
  await page.goto(`/lab/candidates?evaluation=${sample.empty.id}`);
  await expect(
    page.getByRole("heading", { name: "Cash-only target" }),
  ).toBeVisible();
  await expect(
    page.getByText("EMPTY_ELIGIBLE_UNIVERSE", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: info.outputPath("candidate-cash-only.png"),
    fullPage: true,
  });
  await page.getByLabel("Evaluation ID", { exact: true }).fill(failedId);
  await page.getByRole("button", { name: "Load saved evaluation" }).click();
  await expect(
    page.getByText("Evaluation failed:", { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Target allocation", exact: true }),
  ).toHaveCount(0);
  await page
    .getByLabel("Evaluation ID", { exact: true })
    .fill("99999999-9999-4999-8999-999999999999");
  await page.getByRole("button", { name: "Load saved evaluation" }).click();
  await expect(
    page.getByText("That evaluation was not found. Check its saved ID."),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "Data source", exact: true })
    .selectOption("research_market_data");
  await expect(
    page.getByRole("heading", { name: "No research snapshot registered" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Evaluate pinned inputs" }),
  ).toBeDisabled();
  await page
    .getByRole("combobox", { name: "Data source", exact: true })
    .selectOption("synthetic_fixture");
  await expect(
    page.getByRole("combobox", { name: "Snapshot", exact: true }),
  ).toHaveValue(sample.snapshot.id);
  await page.getByRole("button", { name: "Evaluate pinned inputs" }).click();
  await expect(
    page.getByText(
      "The selected snapshot is blocked or lacks a completed session at that date.",
    ),
  ).toBeVisible();
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
    path: info.outputPath("candidate-errors.png"),
    fullPage: true,
  });
});
