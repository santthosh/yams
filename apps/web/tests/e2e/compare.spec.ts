import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import sample from "../experiment-transport.json" with { type: "json" };

// Presentation-only transport pairs. Financial goldens remain independent FIX-07.
const first = sample.completed;
const secondId = "77777777-7777-4777-8777-777777777777";
const versionId = "88888888-8888-4888-8888-888888888888";
const second = {
  ...first,
  id: secondId,
  config_sha256: "b".repeat(64),
  report: {
    ...first.report,
    portfolio: {
      ...first.report.portfolio,
      total: {
        ...first.report.portfolio.total,
        metrics: {
          ...first.report.portfolio.total.metrics,
          cumulative_return_fraction: { value: 0.1, unavailable_reason: null },
          max_drawdown_fraction: { value: 0.2, unavailable_reason: null },
        },
      },
    },
  },
  inputs: { ...first.inputs, strategy_version_id: versionId },
  strategy_config: {
    ...first.strategy_config,
    portfolio: {
      ...first.strategy_config.portfolio,
      max_position_weight: "0.1",
    },
  },
};
async function reports(
  page: Page,
  mode: "aligned" | "misaligned" | "failed" = "aligned",
) {
  await page.route("**/api/v1/experiments**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/series"))
      return route.fulfill({
        json: { items: sample.series, next_cursor: null },
      });
    if (path.endsWith("/trades"))
      return route.fulfill({
        json: { items: sample.trades, next_cursor: null },
      });
    if (path.endsWith(first.id)) return route.fulfill({ json: first });
    if (path.endsWith(secondId)) {
      if (mode === "failed")
        return route.fulfill({
          json: { ...second, status: "failed", report: null, metrics: null },
        });
      return route.fulfill({
        json:
          mode === "misaligned"
            ? {
                ...second,
                report: {
                  ...second.report,
                  comparison_sha256: "d".repeat(64),
                  comparison: {
                    ...second.report.comparison,
                    initial_capital_usd: "2000.00",
                  },
                },
              }
            : second,
      });
    }
    return route.fulfill({
      json: { items: [first, second], next_cursor: null },
    });
  });
}
test("aligned immutable reports expose chosen sorting, risk, cash and accessible numeric curves", async ({
  page,
}, info) => {
  await reports(page);
  await page.goto(`/lab/compare?ids=${first.id},${secondId}`);
  await expect(
    page.getByRole("heading", {
      name: "Aligned experiment comparison",
      exact: true,
    }),
  ).toBeVisible();
  const metricRows = page
    .getByRole("region", { name: "Historical metric comparison", exact: true })
    .locator("tbody tr");
  await expect(metricRows.first()).toContainText(secondId.slice(0, 8));
  await page
    .getByRole("combobox", { name: "Sort by metric", exact: true })
    .selectOption("max_drawdown_fraction");
  await expect(
    page.getByText("Sorted by maximum drawdown", { exact: false }),
  ).toBeVisible();
  await expect(metricRows.first()).toContainText(first.id.slice(0, 8));
  await expect(
    page.getByRole("columnheader", { name: "Turnover", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("columnheader", { name: "Slippage (USD)", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(/Repeated parameter.*holdout/i).first(),
  ).toBeVisible();
  await expect(
    page.getByText("portfolio.max_position_weight", { exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.locator(".comparison-chart .main-svg").first(),
  ).toBeVisible();
  const table = page.getByRole("region", {
    name: "Exact comparison session values",
    exact: true,
  });
  await table.focus();
  await expect(table).toBeFocused();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.screenshot({
    path: `test-results/comparison-aligned-${info.project.name}.png`,
    fullPage: true,
  });
});
test("incompatible terms show exact differences and require fair rerun before ranking", async ({
  page,
}, info) => {
  await reports(page, "misaligned");
  await page.goto(`/lab/compare?ids=${first.id},${secondId}`);
  await expect(
    page.getByRole("heading", {
      name: "Incompatible experiment settings",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByText("initial_capital_usd", { exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByText('"2000.00"', { exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByRole("combobox", { name: "Sort by metric", exact: true }),
  ).toHaveCount(0);
  await expect(page.locator(".comparison-chart")).toHaveCount(0);
  await expect(
    page.getByRole("button", {
      name: "Rerun all with reference settings",
      exact: true,
    }),
  ).toBeVisible();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.screenshot({
    path: `test-results/comparison-misaligned-${info.project.name}.png`,
    fullPage: true,
  });
});
test("insufficient, failed and unknown selections retain explicit accessible recovery", async ({
  page,
}) => {
  await reports(page, "failed");
  await page.goto("/lab/compare");
  await expect(
    page.getByRole("button", {
      name: "Compare selected experiments",
      exact: true,
    }),
  ).toBeDisabled();
  await page.goto(`/lab/compare?ids=${first.id},${secondId}`);
  await expect(
    page.getByText(/Only completed experiments can be compared/),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Refresh selected reports", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".comparison-chart")).toHaveCount(0);
  await page.route(`**/api/v1/experiments/${secondId}`, (route) =>
    route.fulfill({ status: 404, json: { error: { code: "NOT_FOUND" } } }),
  );
  await page
    .getByRole("button", { name: "Refresh selected reports", exact: true })
    .click();
  await expect(
    page.locator("#main-content").getByRole("alert").first(),
  ).toContainText("unavailable");
  await expect(page.locator(".comparison-chart")).toHaveCount(0);
});

test("one-rule challenge preserves originals and exact source seed through publication and queued comparison", async ({
  page,
}) => {
  await reports(page);
  const challengeId = "dddddddd-dddd-4ddd-8ddd-dddddddddddd";
  await page.route(`**/api/v1/experiments/${challengeId}`, (route) =>
    route.fulfill({ json: { ...second, id: challengeId } }),
  );
  const exact = first.inputs_canonical_json.replace(
    '"random_seed":42',
    '"random_seed":18446744073709551615',
  );
  await page.route(`**/api/v1/experiments/${first.id}`, (route) =>
    route.fulfill({ json: { ...first, inputs_canonical_json: exact } }),
  );
  let published: { name: string; config: typeof first.strategy_config } | null =
    null;
  let body = "";
  await page.route("**/api/v1/strategies", async (route) => {
    published = route.request().postDataJSON();
    return route.fulfill({
      status: 201,
      json: {
        id: "99999999-9999-4999-8999-999999999999",
        name: published!.name,
        published_version: { id: versionId, config: published!.config },
      },
    });
  });
  await page.route("**/api/v1/experiments", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    body = route.request().postData() ?? "";
    return route.fulfill({
      status: 202,
      json: { experiment_id: challengeId, job_id: first.job_id },
    });
  });
  await page.goto(`/lab/compare?ids=${first.id},${secondId}`);
  await page
    .getByLabel("New maximum position weight", { exact: true })
    .fill("0.10");
  await page
    .getByLabel("Challenge strategy name", { exact: true })
    .fill("A controlled cap challenge");
  await page
    .getByRole("button", { name: "Publish challenge version", exact: true })
    .click();
  await expect(
    page.getByRole("button", {
      name: "Run challenge with source settings",
      exact: true,
    }),
  ).toBeVisible();
  expect(published!.config).toEqual({
    ...first.strategy_config,
    portfolio: {
      ...first.strategy_config.portfolio,
      max_position_weight: "0.10",
    },
  });
  await page
    .getByRole("button", {
      name: "Run challenge with source settings",
      exact: true,
    })
    .click();
  await expect(
    page.getByRole("link", {
      name: "Open source and challenge comparison",
      exact: true,
    }),
  ).toHaveAttribute("href", `/lab/compare?ids=${first.id},${challengeId}`);
  expect(body).toContain('"random_seed":18446744073709551615');
  expect(JSON.parse(body)).toEqual({
    ...JSON.parse(exact),
    strategy_version_id: versionId,
  });
  expect(first.strategy_config.portfolio.max_position_weight).toBe("0.2");
  await expect(
    page.getByRole("button", {
      name: "Publish challenge version",
      exact: true,
    }),
  ).toBeDisabled();
  await page
    .getByRole("link", {
      name: "Open source and challenge comparison",
      exact: true,
    })
    .click();
  await expect(
    page.getByRole("heading", {
      name: `${challengeId.slice(0, 8)} · One-rule comparison`,
      exact: true,
    }),
  ).toBeVisible();
});

test("fair reruns retain accepted jobs and forbid uncertain duplicate submissions", async ({
  page,
}) => {
  await reports(page, "misaligned");
  const exact = first.inputs_canonical_json.replace(
    '"random_seed":42',
    '"random_seed":18446744073709551615',
  );
  await page.route(`**/api/v1/experiments/${first.id}`, (route) =>
    route.fulfill({ json: { ...first, inputs_canonical_json: exact } }),
  );
  const posts: string[] = [];
  await page.route("**/api/v1/experiments", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    posts.push(route.request().postData() ?? "");
    return posts.length === 1
      ? route.fulfill({
          status: 202,
          json: {
            experiment_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            job_id: first.job_id,
          },
        })
      : route.fulfill({ status: 503, json: { error: { code: "NOT_READY" } } });
  });
  await page.goto(`/lab/compare?ids=${first.id},${secondId}`);
  await page
    .getByRole("button", {
      name: "Rerun all with reference settings",
      exact: true,
    })
    .click();
  await expect(
    page.locator("#main-content").getByRole("alert").first(),
  ).toContainText("Accepted jobs below are retained");
  await expect(
    page.getByRole("link", {
      name: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", {
      name: "Continue remaining reruns",
      exact: true,
    }),
  ).toBeDisabled();
  expect(posts).toHaveLength(2);
  for (const body of posts)
    expect(body).toContain('"random_seed":18446744073709551615');
  expect(JSON.parse(posts[1]).initial_capital_usd).toBe("1000.00");
});

test("history selection is bounded to four and invalid direct identities never become a comparison", async ({
  page,
}) => {
  await reports(page);
  const extra = [
    "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
  ].map((id) => ({ ...first, id }));
  await page.route("**/api/v1/experiments?limit=25", (route) =>
    route.fulfill({
      json: { items: [first, second, ...extra], next_cursor: null },
    }),
  );
  await page.goto("/lab/compare");
  const boxes = page.locator("#main-content").getByRole("checkbox");
  await expect(boxes).toHaveCount(5);
  for (let index = 0; index < 4; index++) await boxes.nth(index).check();
  await expect(boxes.nth(4)).toBeDisabled();
  await expect(
    page.getByRole("button", {
      name: "Compare selected experiments",
      exact: true,
    }),
  ).toBeEnabled();
  await boxes.nth(0).uncheck();
  await expect(boxes.nth(4)).toBeEnabled();
  await page.goto(`/lab/compare?ids=${first.id},invalid`);
  await expect(
    page.locator("#main-content").getByRole("alert").first(),
  ).toContainText("two to four distinct valid");
  await expect(
    page.getByRole("heading", {
      name: "Aligned experiment comparison",
      exact: true,
    }),
  ).toHaveCount(0);
});

test("sealed sample failures, pagination and genuine empty windows remain distinct", async ({
  page,
}) => {
  await reports(page);
  let mode = "error";
  await page.route("**/api/v1/experiments/*/series**", (route) => {
    if (mode === "error")
      return route.fulfill({
        status: 503,
        json: { error: { code: "NOT_READY" } },
      });
    if (mode === "empty")
      return route.fulfill({ json: { items: [], next_cursor: null } });
    const cursor = new URL(route.request().url()).searchParams.get("cursor");
    return route.fulfill({
      json: {
        items: cursor ? sample.series.slice(2) : sample.series.slice(0, 2),
        next_cursor: cursor ? null : "next-page",
      },
    });
  });
  await page.goto(`/lab/compare?ids=${first.id},${secondId}`);
  await expect(
    page.locator("#main-content").getByRole("alert").first(),
  ).toContainText("Sealed samples are unavailable");
  await expect(
    page.getByRole("heading", {
      name: "No stored session samples",
      exact: true,
    }),
  ).toHaveCount(0);
  mode = "pages";
  await page
    .getByRole("button", { name: "Refresh selected reports", exact: true })
    .click();
  await expect(page.getByText(/Partial session pages:/)).toBeVisible();
  await page
    .getByRole("button", {
      name: `Load more sessions · ${first.id.slice(0, 8)}`,
      exact: true,
    })
    .click();
  await page
    .getByRole("button", {
      name: `Load more sessions · ${secondId.slice(0, 8)}`,
      exact: true,
    })
    .click();
  await expect(
    page.getByText("All original session pages are loaded.", { exact: true }),
  ).toBeVisible();
  const table = page
    .getByRole("region", {
      name: "Exact comparison session values",
      exact: true,
    })
    .getByRole("table");
  await expect(table.locator("tbody tr")).toHaveCount(8);
  mode = "empty";
  await page
    .getByRole("button", { name: "Refresh selected reports", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "No stored session samples",
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.locator(".comparison-chart")).toHaveCount(0);
});
