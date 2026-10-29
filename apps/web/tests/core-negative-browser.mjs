// Actual offline fixture API/worker, including real unavailable outcomes.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { chromium, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
const origin = process.env.YAMS_SMOKE_URL;
const destination = process.env.YAMS_SMOKE_EVIDENCE;
assert(origin && destination);
const browser = await chromium.launch();
const records = [];
try {
  for (const width of [360, 1280]) {
    const context = await browser.newContext({
      viewport: { width, height: 900 },
    });
    const page = await context.newPage();
    const errors = [],
      external = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.route("**/*", async (route) => {
      if (new URL(route.request().url()).origin !== origin) {
        external.push(route.request().url());
        await route.abort();
      } else await route.continue();
    });
    await page.goto(`${origin}/portfolios`);
    await expect(page.getByLabel("Published strategy version")).toBeEnabled();
    await page
      .getByLabel("Account name", { exact: true })
      .fill(`Core negative fixtures ${width}`);
    const created = page.waitForResponse(
      (r) =>
        r.url() === `${origin}/api/v1/portfolios` &&
        r.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "Create paper account", exact: true })
      .click();
    const creation = await created;
    assert.equal(creation.status(), 201);
    const account = await creation.json();
    await page.waitForURL(`${origin}/portfolios/${account.id}`);
    await page
      .getByRole("link", { name: "Decision Center →", exact: true })
      .click();
    await expect(page.getByLabel("As-of pinned session")).not.toHaveValue("");
    const baseLedger = await (
      await page.request.get(
        `${origin}/api/v1/portfolios/${account.id}/transactions`,
      )
    ).json();
    const decisions = [];
    for (const [session, kind] of [
      ["2027-01-04", "empty"],
      ["2030-12-30", "unavailable"],
    ]) {
      await page.getByLabel("As-of pinned session").fill(session);
      const admitted = page.waitForResponse(
        (r) =>
          r.url().endsWith(`/portfolios/${account.id}/recommendations`) &&
          r.request().method() === "POST",
      );
      await page
        .getByRole("button", { name: "Generate paper review", exact: true })
        .click();
      const admission = await admitted;
      assert.equal(admission.status(), 202);
      const accepted = await admission.json();
      let detail;
      await expect
        .poll(
          async () => {
            const response = await page.request.get(
              `${origin}/api/v1/recommendations/${accepted.recommendation_id}`,
            );
            if (!response.ok()) return "pending";
            detail = await response.json();
            return detail.forecast_job.status;
          },
          { timeout: 60000 },
        )
        .toBe("completed");
      await page
        .getByRole("button", {
          name: "Refresh decision and posted state",
          exact: true,
        })
        .click();
      await expect(
        page.getByRole("combobox", { name: "Review", exact: true }),
      ).toHaveValue(accepted.recommendation_id);
      if (kind === "empty") {
        assert.equal(detail.summary_action, "ALLOCATE_TO_CASH");
        assert.deepEqual(detail.target_weights, []);
        assert.match(detail.cash_target_weight, /^1(?:\.0+)?$/);
        assert.deepEqual(detail.actions, []);
        assert(detail.candidates.every((c) => c.exclusion_reasons.length > 0));
        assert(
          detail.candidates.some((c) =>
            c.exclusion_reasons.includes("MISSING_HISTORY"),
          ),
        );
        assert.equal(detail.forecast.status, "available");
        for (const outcome of [
          detail.forecast.proposed,
          detail.forecast.hold_unchanged,
        ]) {
          assert.equal(outcome.median_ending_value_usd, "1000.00");
          assert.equal(outcome.p10_return_fraction, 0);
          assert.equal(outcome.median_return_fraction, 0);
          assert.equal(outcome.p90_return_fraction, 0);
          assert.equal(outcome.probability_of_loss, 0);
        }
        await expect(
          page.getByText("ALLOCATE TO CASH", { exact: true }),
        ).toBeVisible();
        await expect(
          page.getByText("Approval unavailable: NO EXECUTABLE ORDERS", {
            exact: true,
          }),
        ).toBeVisible();
        await expect(
          page.getByRole("button", {
            name: "Review paper approval",
            exact: true,
          }),
        ).toBeDisabled();
        // Zero is the engine's declared zero-yield cash-only result, not a
        // substitute for missing asset history or a generated security return.
        await expect(
          page.getByRole("region", {
            name: "Scenario comparison",
            exact: true,
          }),
        ).toBeVisible();
      } else {
        assert.equal(detail.forecast.status, "unavailable");
        assert.equal(
          detail.forecast.unavailable_reason,
          "CALENDAR_UNAVAILABLE",
        );
        assert.equal(detail.forecast.proposed, null);
        assert.equal(detail.forecast.hold_unchanged, null);
        assert.equal(detail.forecast.median_return_delta_fraction, null);
        await expect(
          page.getByText(/Forecast unavailable: CALENDAR UNAVAILABLE/),
        ).toBeVisible();
        await expect(
          page.getByRole("region", {
            name: "Scenario comparison",
            exact: true,
          }),
        ).toHaveCount(0);
      }
      const posted = await (
        await page.request.get(`${origin}/api/v1/portfolios/${account.id}`)
      ).json();
      assert.equal(posted.cash_usd, "1000.00");
      assert.equal(posted.revision, 1);
      assert.deepEqual(posted.holdings, []);
      assert.deepEqual(
        await (
          await page.request.get(
            `${origin}/api/v1/portfolios/${account.id}/transactions`,
          )
        ).json(),
        baseLedger,
      );
      const axe = await new AxeBuilder({ page }).analyze();
      assert.deepEqual(axe.violations, []);
      assert.equal(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        true,
      );
      await page.screenshot({
        path: path.join(destination, `core-${kind}-${width}.png`),
        fullPage: true,
      });
      decisions.push({
        kind,
        accepted,
        detail,
        posted,
        axe_violations: axe.violations,
      });
    }
    // An actual browser connection failure must expose an error, never a fake
    // successful review or zero-valued portfolio. It creates no backend work.
    const blocked = `${origin}/api/v1/portfolios/${account.id}`;
    const abortAccount = (route) => route.abort("failed");
    await page.route(blocked, abortAccount);
    await page.reload();
    await expect(page.getByRole("main").getByRole("alert")).toBeVisible();
    await expect(
      page.getByRole("heading", {
        name: "2. Target allocation and risk",
        exact: true,
      }),
    ).toHaveCount(0);
    await page.screenshot({
      path: path.join(destination, `core-connection-error-${width}.png`),
      fullPage: true,
    });
    await page.unroute(blocked, abortAccount);
    await page
      .getByRole("button", {
        name: "Refresh decision and posted state",
        exact: true,
      })
      .click();
    await expect(
      page.getByText(/Forecast unavailable: CALENDAR UNAVAILABLE/),
    ).toBeVisible();
    assert.deepEqual(
      await (
        await page.request.get(
          `${origin}/api/v1/portfolios/${account.id}/transactions`,
        )
      ).json(),
      baseLedger,
    );
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    records.push({
      width,
      account_id: account.id,
      decisions,
      ledger: baseLedger,
      connection_error_recovered_without_mutation: true,
    });
    await context.close();
  }
} finally {
  await browser.close();
}
fs.writeFileSync(
  path.join(destination, "core-negative-browser.json"),
  JSON.stringify(
    {
      classification: "RECORDED_APPLICATION_OUTPUT_NOT_INDEPENDENT_ORACLE",
      data_label: "SYNTHETIC_DATA_ONLY",
      records,
    },
    null,
    2,
  ),
);
console.log(
  "Real core negative cases: empty universe/cash-only, unavailable pinned horizon, connection-error recovery, unchanged ledger, Axe/viewport at360/1280 passed",
);
