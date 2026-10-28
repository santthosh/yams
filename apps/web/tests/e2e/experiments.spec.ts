import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import sample from "../experiment-transport.json" with { type: "json" };
import candidate from "../candidate-transport.json" with { type: "json" };
import fixtures from "../transport-fixtures.json" with { type: "json" };

const run = sample.completed;
const root = {
  ...candidate.strategy,
  name: "Mean Reversion",
  template_key: "mean_reversion",
  published_version: {
    ...candidate.strategy.published_version,
    id: run.inputs.strategy_version_id,
    config: run.strategy_config,
    config_sha256: run.config_sha256,
  },
};
async function choices(page: Page) {
  await page.route("**/api/v1/strategies**", (route) =>
    route.fulfill({
      json: new URL(route.request().url()).pathname.endsWith("/versions")
        ? { items: [root.published_version], next_cursor: null }
        : { items: [root], next_cursor: null },
    }),
  );
  await page.route("**/api/v1/data/snapshots**", (route) =>
    route.fulfill({
      json: {
        items: [{ ...candidate.snapshot, id: run.inputs.snapshot_id }],
        next_cursor: null,
      },
    }),
  );
}
function pending(status = "running") {
  return {
    ...run,
    status,
    report: null,
    metrics: null,
    curve_artifact: null,
    trade_artifact: null,
    reproducibility_manifest: null,
    error:
      status === "failed"
        ? {
            code: "VALIDATION_ERROR",
            message: "The pinned price evidence is missing.",
            retryable: false,
            details: {},
            correlation_id: fixtures.job.id,
          }
        : null,
  };
}

test("builder blocks invalid coverage, submits exact inputs and shows immutable accessible report", async ({
  page,
}, info) => {
  await choices(page);
  let posted = "";
  let reads = 0;
  await page.route("**/api/v1/jobs/**", (route) =>
    route.fulfill({
      json: {
        ...fixtures.job,
        id: run.job_id,
        kind: "backtest",
        status: "running",
        progress: 50,
        result: null,
        error: null,
      },
    }),
  );
  await page.route("**/api/v1/experiments**", async (route) => {
    const url = new URL(route.request().url());
    if (route.request().method() === "POST") {
      posted = route.request().postData() ?? "";
      return route.fulfill({
        status: 202,
        json: { experiment_id: run.id, job_id: run.job_id },
      });
    }
    if (url.pathname.endsWith("/series"))
      return route.fulfill({
        json: { items: sample.series, next_cursor: null },
      });
    if (url.pathname.endsWith("/trades"))
      return route.fulfill({
        json: { items: sample.trades, next_cursor: null },
      });
    if (url.pathname.endsWith(run.id)) {
      reads++;
      return route.fulfill({ json: reads < 3 ? pending() : run });
    }
    return route.fulfill({ json: { items: [], next_cursor: null } });
  });
  await page.goto("/lab/experiments");
  await expect(
    page.getByRole("heading", { name: "Historical experiments", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("combobox", { name: "Published version", exact: true }),
  ).toHaveValue(run.inputs.strategy_version_id);
  await expect(
    page.getByLabel("End session (exclusive)", { exact: true }),
  ).toHaveValue(candidate.snapshot.coverage.last_session);
  await page.getByLabel("Start session", { exact: true }).fill("2020-01-01");
  await expect(
    page.getByRole("button", {
      name: "Run historical experiment",
      exact: true,
    }),
  ).toBeDisabled();
  await page
    .getByLabel("Start session", { exact: true })
    .fill(run.inputs.start_session);
  await page
    .getByLabel("End session (exclusive)", { exact: true })
    .fill(run.inputs.end_session_exclusive);
  await page.getByLabel("Initial synthetic capital (USD)").fill("0.00");
  await expect(
    page.getByRole("button", {
      name: "Run historical experiment",
      exact: true,
    }),
  ).toBeDisabled();
  await page.getByLabel("Initial synthetic capital (USD)").fill("1000.00");
  await page.getByLabel("Random seed", { exact: true }).fill("42");
  await page
    .getByRole("button", { name: "Run historical experiment", exact: true })
    .focus();
  await expect(
    page.getByRole("button", {
      name: "Run historical experiment",
      exact: true,
    }),
  ).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(new RegExp(`/lab/experiments/${run.id}$`));
  expect(posted).toContain('"random_seed":42');
  expect(posted).toContain('"initial_capital_usd":"1000.00"');
  await expect(
    page.getByRole("button", { name: "Cancel experiment", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("table", { name: /Net simulated performance/ }),
  ).toBeVisible();
  await expect(
    page.getByText("$1,000.22", { exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByRole("columnheader", { name: "Holdout", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("SYNTHETIC_DATA_ONLY", { exact: true }),
  ).toBeVisible();
  await expect(
    page.locator(".experiment-chart .main-svg").first(),
  ).toBeVisible();
  const region = page.getByLabel("Exact session series table", { exact: true });
  await region.focus();
  await expect(region).toBeFocused();
  await page.keyboard.press("ArrowRight");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page
    .locator(".experiment-figure")
    .first()
    .screenshot({
      path: `test-results/experiment-equity-${info.project.name}.png`,
    });
  await page.screenshot({
    path: `test-results/experiment-completed-${info.project.name}.png`,
    fullPage: true,
  });
});

test("cancel, failed and unknown reports remain distinct and exact rerun preserves the original", async ({
  page,
}, info) => {
  let state = "running";
  let originalReads = 0;
  let rerunBody = "";
  const nextId = "77777777-7777-4777-8777-777777777777";
  const exact = run.inputs_canonical_json.replace(
    '"random_seed":42',
    '"random_seed":18446744073709551615',
  );
  await page.route("**/api/v1/jobs/**", async (route) => {
    if (route.request().method() === "POST") {
      state = "cancelled";
      return route.fulfill({
        status: 202,
        json: {
          ...fixtures.job,
          id: run.job_id,
          status: "cancel_requested",
          error: null,
        },
      });
    }
    return route.fulfill({
      json: {
        ...fixtures.job,
        id: run.job_id,
        status: "running",
        kind: "backtest",
        progress: 30,
        result: null,
        error: null,
      },
    });
  });
  await page.route("**/api/v1/experiments**", async (route) => {
    const url = new URL(route.request().url());
    if (route.request().method() === "POST") {
      rerunBody = route.request().postData() ?? "";
      return route.fulfill({
        status: 202,
        json: { experiment_id: nextId, job_id: run.job_id },
      });
    }
    if (url.pathname.endsWith(nextId))
      return route.fulfill({
        json: {
          ...pending("queued"),
          id: nextId,
          inputs_canonical_json: exact,
        },
      });
    if (state === "unknown")
      return route.fulfill({
        status: 404,
        json: { error: { code: "NOT_FOUND" } },
      });
    originalReads++;
    return route.fulfill({
      json: { ...pending(state), inputs_canonical_json: exact },
    });
  });
  await page.goto(`/lab/experiments/${run.id}`);
  await page
    .getByRole("button", { name: "Cancel experiment", exact: true })
    .click();
  await expect(
    page.getByText("Cancelled. No completed financial report was published.", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.getByRole("table")).toHaveCount(0);
  await page
    .getByRole("button", { name: "Rerun with same inputs", exact: true })
    .click();
  await expect(page).toHaveURL(new RegExp(`${nextId}$`));
  expect(rerunBody).toBe(exact);
  expect(originalReads).toBeGreaterThan(0);
  state = "failed";
  await page.goto(`/lab/experiments/${run.id}`);
  await expect(page.locator("#main-content").getByRole("alert")).toContainText(
    "The pinned price evidence is missing",
  );
  await expect(
    page.getByRole("button", { name: "Rerun with same inputs", exact: true }),
  ).toBeVisible();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.screenshot({
    path: `test-results/experiment-failed-${info.project.name}.png`,
    fullPage: true,
  });
  state = "unknown";
  await page.goto(`/lab/experiments/${run.id}`);
  await expect(page.locator("#main-content").getByRole("alert")).toContainText(
    "unavailable",
  );
  await expect(page.getByRole("table")).toHaveCount(0);
});

test("report pages preserve unavailable gaps, empty windows and retry failed samples", async ({
  page,
}, info) => {
  let unavailable = true;
  let empty = false;
  let requests = 0;
  const gap = {
    ...run,
    report: {
      ...run.report,
      benchmark: {
        ...run.report.benchmark,
        available: false,
        unavailable_reason: "MISSING_BENCHMARK_BAR",
        periods: null,
      },
    },
  };
  await page.route("**/api/v1/experiments**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/series") || url.pathname.endsWith("/trades")) {
      requests++;
      if (unavailable)
        return route.fulfill({
          status: 503,
          json: { error: { code: "NOT_READY" } },
        });
      if (empty)
        return route.fulfill({ json: { items: [], next_cursor: null } });
      if (url.pathname.endsWith("/trades"))
        return route.fulfill({
          json: { items: sample.trades, next_cursor: null },
        });
      const points = sample.series.map((point, index) =>
        index === 1
          ? {
              ...point,
              benchmark_nav_usd: null,
              benchmark_unavailable_reason: "MISSING_BENCHMARK_BAR",
            }
          : point,
      );
      return route.fulfill({
        json: {
          items: url.searchParams.has("cursor")
            ? points.slice(2)
            : points.slice(0, 2),
          next_cursor: url.searchParams.has("cursor") ? null : "cursor-2",
        },
      });
    }
    return route.fulfill({ json: gap });
  });
  await page.goto(`/lab/experiments/${run.id}`);
  await expect(page.locator("#main-content").getByRole("alert")).toContainText(
    "Sealed samples",
  );
  await expect(
    page.getByRole("heading", {
      name: "No sessions in this window",
      exact: true,
    }),
  ).toHaveCount(0);
  unavailable = false;
  await page
    .getByRole("button", { name: "Retry samples", exact: true })
    .click();
  await expect(
    page.getByText(
      "More sessions are available; charts are partial until loaded.",
      { exact: false },
    ),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Load more session samples", exact: true })
    .click();
  await expect(
    page.getByRole("rowheader", { name: "2028-07-21", exact: true }),
  ).toHaveCount(1);
  await expect(
    page.getByRole("cell", {
      name: "Unavailable · MISSING_BENCHMARK_BAR",
      exact: true,
    }),
  ).toBeVisible();
  expect(requests).toBeGreaterThan(2);
  await page.getByLabel("Window start", { exact: true }).fill("2020-01-01");
  await expect(
    page.getByRole("button", { name: "Apply sample window", exact: true }),
  ).toBeDisabled();
  empty = true;
  await page.getByLabel("Window start", { exact: true }).fill("2028-07-22");
  await page
    .getByRole("button", { name: "Apply sample window", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "No sessions in this window",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", {
      name: "No simulated executions in this window",
      exact: true,
    }),
  ).toBeVisible();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.screenshot({
    path: `test-results/experiment-empty-${info.project.name}.png`,
    fullPage: true,
  });
});

test("input discovery distinguishes failure, genuine empty state and blocked quality", async ({
  page,
}, info) => {
  let mode = "failed";
  await choices(page);
  await page.route("**/api/v1/data/snapshots**", (route) =>
    mode === "failed"
      ? route.fulfill({ status: 503, json: { error: { code: "NOT_READY" } } })
      : route.fulfill({
          json: {
            items:
              mode === "empty"
                ? []
                : [{ ...candidate.snapshot, quality: "blocked" }],
            next_cursor: null,
          },
        }),
  );
  await page.route("**/api/v1/experiments**", (route) =>
    route.fulfill({ json: { items: [], next_cursor: null } }),
  );
  await page.goto("/lab/experiments");
  await expect(
    page.locator("#main-content").getByRole("alert").first(),
  ).toContainText("could not be loaded");
  await expect(
    page.getByRole("heading", {
      name: "No usable experiment inputs",
      exact: true,
    }),
  ).toHaveCount(0);
  mode = "empty";
  await page
    .getByRole("button", { name: "Reload choices and history", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "No usable experiment inputs",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "No experiments yet", exact: true }),
  ).toBeVisible();
  mode = "blocked";
  await page
    .getByRole("button", { name: "Reload choices and history", exact: true })
    .click();
  await expect(
    page.getByText("This snapshot is blocked for experiments.", {
      exact: false,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", {
      name: "Run historical experiment",
      exact: true,
    }),
  ).toBeDisabled();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.screenshot({
    path: `test-results/experiment-blocked-${info.project.name}.png`,
    fullPage: true,
  });
});
