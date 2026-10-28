import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { chromium } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
const origin = process.env.YAMS_SMOKE_URL;
const destination = process.env.YAMS_SMOKE_EVIDENCE;
assert(origin && destination);
const preceding = JSON.parse(
  fs.readFileSync(path.join(destination, "experiment-ui.json"), "utf8"),
);
const browser = await chromium.launch();
const records = [];
async function read(page, id) {
  return page.evaluate(async (identity) => {
    const response = await fetch(`/api/v1/experiments/${identity}`);
    if (!response.ok) throw new Error(`Report read ${response.status}`);
    const raw = await response.text();
    return { raw, view: JSON.parse(raw) };
  }, id);
}
async function completed(page, id) {
  for (let index = 0; index < 300; index++) {
    const report = await read(page, id);
    if (report.view.status === "completed") return report;
    assert(
      !["failed", "cancelled"].includes(report.view.status),
      JSON.stringify(report.view.error),
    );
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error("Comparison job exceeded bounded wait");
}
try {
  for (const width of [360, 1280]) {
    const existing = preceding.records.find(
      (row) => row.width === width && row.original_raw_json,
    );
    assert(existing);
    const original = JSON.parse(existing.original_raw_json);
    const rerun = JSON.parse(existing.rerun_raw_json);
    const context = await browser.newContext({
      viewport: { width, height: 900 },
    });
    const page = await context.newPage();
    const errors = [],
      external = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.route("**/*", async (route) => {
      if (new URL(route.request().url()).origin !== origin) {
        external.push(route.request().url());
        await route.abort();
      } else await route.continue();
    });
    await page.goto(`${origin}/lab/compare?ids=${original.id},${rerun.id}`);
    await page
      .getByRole("heading", {
        name: "Aligned experiment comparison",
        exact: true,
      })
      .waitFor();
    await page.locator(".comparison-chart .main-svg").first().waitFor();
    assert.equal(
      await page
        .locator(".comparison-chart")
        .evaluate((node) => node._fullLayout.yaxis.type),
      "linear",
    );
    const region = page.getByRole("region", {
      name: "Exact comparison session values",
      exact: true,
    });
    await region.focus();
    assert(await region.evaluate((node) => node === document.activeElement));
    await page
      .getByRole("combobox", { name: "Sort by metric", exact: true })
      .selectOption("max_drawdown_fraction");
    assert(
      (await page
        .getByText("Sorted by maximum drawdown", { exact: false })
        .count()) === 1,
    );
    assert.deepEqual((await new AxeBuilder({ page }).analyze()).violations, []);
    assert(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    );
    await page.evaluate(() => scrollTo(0, 0));
    await page.screenshot({
      path: path.join(destination, `comparison-aligned-${width}.png`),
      fullPage: true,
    });
    await page
      .getByLabel("New maximum position weight", { exact: true })
      .fill("0.10");
    await page
      .getByLabel("Challenge strategy name", { exact: true })
      .fill(`Synthetic cap challenge ${width} ${original.id.slice(0, 8)}`);
    await page
      .getByRole("button", { name: "Publish challenge version", exact: true })
      .focus();
    await page.keyboard.press("Enter");
    await page
      .getByRole("button", {
        name: "Run challenge with source settings",
        exact: true,
      })
      .waitFor();
    await page
      .getByRole("button", {
        name: "Run challenge with source settings",
        exact: true,
      })
      .click();
    const comparison = page.getByRole("link", {
      name: "Open source and challenge comparison",
      exact: true,
    });
    await comparison.waitFor();
    const href = await comparison.getAttribute("href");
    const ids = new URL(href, origin).searchParams.get("ids").split(",");
    assert.equal(ids[0], original.id);
    assert.notEqual(ids[1], original.id);
    const challenged = await completed(page, ids[1]);
    assert.equal(
      challenged.view.report.comparison_sha256,
      original.report.comparison_sha256,
    );
    const expectedConfig = structuredClone(original.strategy_config);
    expectedConfig.portfolio.max_position_weight = "0.1";
    assert.deepEqual(challenged.view.strategy_config, expectedConfig);
    assert.equal(
      challenged.view.inputs_canonical_json,
      original.inputs_canonical_json.replace(
        original.inputs.strategy_version_id,
        challenged.view.inputs.strategy_version_id,
      ),
    );
    assert.equal(
      (await read(page, original.id)).raw,
      existing.original_raw_json,
    );
    await comparison.click();
    await page
      .getByRole("heading", {
        name: "Aligned experiment comparison",
        exact: true,
      })
      .waitFor();
    await page.getByRole("heading", { name: /One-rule comparison/ }).waitFor();
    await page.locator(".comparison-chart .main-svg").first().waitFor();
    assert.equal(
      await page
        .getByText("portfolio.max_position_weight", { exact: true })
        .count(),
      1,
    );
    assert.deepEqual((await new AxeBuilder({ page }).analyze()).violations, []);
    assert(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    );
    await page.evaluate(() => scrollTo(0, 0));
    await page.screenshot({
      path: path.join(destination, `comparison-challenge-${width}.png`),
      fullPage: true,
    });
    // Actual mismatched run, followed by the UI's explicit shared-setting reruns.
    const mismatch = await page.evaluate(async (source) => {
      const text = source.inputs_canonical_json.replace(
        '"initial_capital_usd":"1000.00"',
        '"initial_capital_usd":"2000.00"',
      );
      const response = await fetch("/api/v1/experiments", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: text,
      });
      if (response.status !== 202)
        throw new Error(`Mismatched admission ${response.status}`);
      return response.json();
    }, original);
    const mismatched = await completed(page, mismatch.experiment_id);
    await page.goto(
      `${origin}/lab/compare?ids=${original.id},${mismatched.view.id}`,
    );
    await page
      .getByRole("heading", {
        name: "Incompatible experiment settings",
        exact: true,
      })
      .waitFor();
    assert.equal(await page.locator(".comparison-chart").count(), 0);
    assert.equal(
      await page
        .getByRole("combobox", { name: "Sort by metric", exact: true })
        .count(),
      0,
    );
    assert.equal(
      await page.getByText("initial_capital_usd", { exact: true }).count(),
      1,
    );
    assert.deepEqual((await new AxeBuilder({ page }).analyze()).violations, []);
    await page.screenshot({
      path: path.join(destination, `comparison-misaligned-${width}.png`),
      fullPage: true,
    });
    await page
      .getByRole("button", {
        name: "Rerun all with reference settings",
        exact: true,
      })
      .click();
    const rerunLink = page.getByRole("link", {
      name: "Open rerun comparison",
      exact: true,
    });
    await rerunLink.waitFor();
    const commonIds = new URL(
      await rerunLink.getAttribute("href"),
      origin,
    ).searchParams
      .get("ids")
      .split(",");
    const common = [];
    for (const id of commonIds) {
      const result = await completed(page, id);
      assert.equal(
        result.view.inputs_canonical_json,
        original.inputs_canonical_json,
      );
      assert.equal(
        result.view.report.comparison_sha256,
        original.report.comparison_sha256,
      );
      assert.equal(
        result.view.curve_artifact.sha256,
        original.curve_artifact.sha256,
      );
      common.push(result.raw);
    }
    await rerunLink.click();
    await page
      .getByRole("heading", {
        name: "Aligned experiment comparison",
        exact: true,
      })
      .waitFor();
    assert.equal(
      (await read(page, original.id)).raw,
      existing.original_raw_json,
    );
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    records.push({
      width,
      source_raw_json: existing.original_raw_json,
      challenge_raw_json: challenged.raw,
      mismatched_raw_json: mismatched.raw,
      common_raw_json: common,
      comparison_path: href,
    });
    await context.close();
  }
  fs.writeFileSync(
    path.join(destination, "comparison-ui.json"),
    JSON.stringify({ label: "SYNTHETIC_DATA_ONLY", records }, null, 2) + "\n",
  );
} finally {
  await browser.close();
}
