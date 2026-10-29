// Readonly inspection of already executed genuine core journeys after restart.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { chromium, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
const origin = process.env.YAMS_SMOKE_URL;
const destination = process.env.YAMS_SMOKE_EVIDENCE;
const stage = process.env.YAMS_SMOKE_CORE_STAGE;
assert(
  origin && destination && ["initial", "restart", "rebuild"].includes(stage),
);
const positive = JSON.parse(
  fs.readFileSync(path.join(destination, "decision-browser.json"), "utf8"),
).evidence;
const negative = JSON.parse(
  fs.readFileSync(path.join(destination, "core-negative-browser.json"), "utf8"),
).records;
const baselineFile = path.join(destination, "core-retained-baseline.json");
const baseline =
  stage === "initial"
    ? null
    : JSON.parse(fs.readFileSync(baselineFile, "utf8"));
const browser = await chromium.launch();
const records = [];
const economic = (account) => ({
  id: account.id,
  cash_usd: account.cash_usd,
  opening_cash_usd: account.opening_cash_usd,
  opening_snapshot_id: account.opening_snapshot_id,
  strategy_version_id: account.strategy_version_id,
  revision: account.revision,
  last_sequence: account.last_sequence,
  state: account.state,
  reconciliation_failed: account.reconciliation_failed,
  holdings: account.holdings
    .map((h) => ({
      asset_id: h.asset_id,
      quantity: h.quantity,
      total_basis_usd: h.total_basis_usd,
    }))
    .sort((a, b) => a.asset_id.localeCompare(b.asset_id)),
});
const immutable = (detail) =>
  Object.fromEntries(
    Object.entries(detail).filter(
      ([key]) =>
        !["is_current", "current_portfolio_revision", "stale_reasons"].includes(
          key,
        ),
    ),
  );
try {
  for (const record of positive) {
    const context = await browser.newContext({
      viewport: { width: record.width, height: 900 },
    });
    // The smoke harness uses an ephemeral loopback port on each install. Restore
    // the original browser's saved operation identity at its current test origin.
    // This is browser-local state, never a new authorization or fixture-time POST.
    await context.addInitScript(
      ({ id, key, revision }) => {
        localStorage.setItem(
          `yams:approval:v1:${id}`,
          JSON.stringify({ key, expected_revision: revision }),
        );
      },
      {
        id: record.accepted.recommendation_id,
        key: record.approval_requests[0].key,
        revision: record.approval_requests[0].body.expected_revision,
      },
    );
    const page = await context.newPage();
    const posts = [],
      errors = [],
      external = [];
    page.on("request", (request) => {
      if (request.method() === "POST") posts.push(request.url());
    });
    page.on("pageerror", (e) => errors.push(e.message));
    await page.route("**/*", async (route) => {
      if (new URL(route.request().url()).origin !== origin) {
        external.push(route.request().url());
        await route.abort();
      } else await route.continue();
    });
    async function get(resource, headers) {
      const response = await page.request.get(`${origin}/api/v1/${resource}`, {
        headers,
      });
      assert.equal(
        response.status(),
        200,
        `${resource}: ${await response.text()}`,
      );
      return response.json();
    }
    async function completed(id) {
      let value;
      await expect
        .poll(
          async () => {
            value = await get(`recommendations/${id}`);
            return value.forecast_job.status;
          },
          { timeout: 60000 },
        )
        .toBe("completed");
      return value;
    }
    const account = await get(`portfolios/${record.account_id}`);
    assert.equal(account.cash_usd, "404.98");
    const ledger = await get(`portfolios/${record.account_id}/transactions`);
    const original = await completed(record.accepted.recommendation_id);
    assert.equal(original.status, "applied");
    assert.deepEqual(original.actions, record.original.actions);
    assert.deepEqual(original.forecast, record.original.forecast);
    const dismissed = await completed(
      record.dismissed_review.accepted.recommendation_id,
    );
    assert.equal(dismissed.status, "dismissed");
    assert.equal(dismissed.summary_action, "HOLD");
    const approval = await get(`recommendations/${original.id}/apply-result`, {
      "Idempotency-Key": record.approval_requests[0].key,
    });
    assert.deepEqual(approval, record.recovered);
    const batch = await get(`order-batches/${approval.batch_id}`);
    assert.equal(batch.status, "filled");
    assert.equal(batch.terminal, true);
    const schedule = await get(`portfolios/${record.account_id}/schedule`);
    const retained = {
      account: economic(account),
      ledger,
      original: immutable(original),
      dismissed: immutable(dismissed),
      approval,
      batch,
      clock_at: schedule.clock_at,
      last_explicit_review_cutoff: schedule.last_explicit_review_cutoff,
    };
    if (baseline)
      assert.deepEqual(
        retained,
        baseline.records.find((r) => r.width === record.width).retained,
      );
    await page.goto(`${origin}/portfolios/${record.account_id}/decisions`);
    const select = page.getByRole("combobox", { name: "Review", exact: true });
    await expect(select.locator(`option[value="${original.id}"]`)).toHaveCount(
      1,
    );
    await select.selectOption(original.id);
    await expect(
      page.getByText("Decision applied;", { exact: false }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Closed paper batch", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("region", { name: "Scenario comparison", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("region", { name: "Posted holdings", exact: true }),
    ).toContainText("2.985074");
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      true,
    );
    const axe = await new AxeBuilder({ page }).analyze();
    assert.deepEqual(axe.violations, []);
    await page.screenshot({
      path: path.join(
        destination,
        `core-retained-${stage}-${record.width}.png`,
      ),
      fullPage: true,
    });
    const aux = negative.find((r) => r.width === record.width);
    assert(aux);
    const auxiliary = {
      account: economic(await get(`portfolios/${aux.account_id}`)),
      ledger: await get(`portfolios/${aux.account_id}/transactions`),
      decisions: [],
    };
    assert.equal(auxiliary.account.cash_usd, "1000.00");
    assert.deepEqual(auxiliary.account.holdings, []);
    assert.deepEqual(auxiliary.ledger, aux.ledger);
    for (const d of aux.decisions) {
      const saved = await completed(d.accepted.recommendation_id);
      assert.equal(saved.forecast.status, d.detail.forecast.status);
      assert.deepEqual(saved.forecast, d.detail.forecast);
      auxiliary.decisions.push(immutable(saved));
    }
    if (baseline)
      assert.deepEqual(
        auxiliary,
        baseline.records.find((r) => r.width === record.width).auxiliary,
      );
    assert.deepEqual(posts, []);
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    records.push({
      width: record.width,
      retained,
      auxiliary,
      readonly_post_count: posts.length,
      axe_violations: axe.violations,
      viewport_bounded: true,
    });
    await context.close();
  }
} finally {
  await browser.close();
}
const evidence = {
  classification: "RECORDED_APPLICATION_OUTPUT_NOT_INDEPENDENT_ORACLE",
  data_label: "SYNTHETIC_DATA_ONLY",
  stage,
  records,
};
if (stage === "initial")
  fs.writeFileSync(baselineFile, JSON.stringify(evidence, null, 2));
fs.writeFileSync(
  path.join(destination, `core-retained-${stage}.json`),
  JSON.stringify(evidence, null, 2),
);
console.log(
  `Readonly core ${stage}: original approval keys, complete fills/ledger, exact cash, original scenarios, HOLD/dismissal, unavailable/cash-only results and logical clocks retained at360/1280; zero POSTs`,
);
