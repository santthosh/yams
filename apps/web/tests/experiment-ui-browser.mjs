import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { chromium } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const origin = process.env.YAMS_SMOKE_URL;
const destination = process.env.YAMS_SMOKE_EVIDENCE;
assert(origin && destination);
const browser = await chromium.launch();
const records = [];
async function readReport(page, id) {
  return page.evaluate(async (identity) => {
    const response = await fetch(`/api/v1/experiments/${identity}`);
    if (!response.ok) throw new Error(`Report read failed: ${response.status}`);
    const raw = await response.text();
    return { raw, view: JSON.parse(raw) };
  }, id);
}
try {
  for (const width of [360, 1280]) {
    const context = await browser.newContext({
      viewport: { width, height: 900 },
    });
    const page = await context.newPage();
    const errors = [];
    const external = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.route("**/*", async (route) => {
      if (new URL(route.request().url()).origin !== origin) {
        external.push(route.request().url());
        await route.abort();
      } else await route.continue();
    });
    // Consume the immutable fork/version actually published by the preceding
    // editor UI journey; prove the two child flows are connected without math
    // or financial outputs authored in the browser.
    const edited = JSON.parse(
      fs.readFileSync(
        path.join(destination, `strategy-editor-${width}.json`),
        "utf8",
      ),
    );
    await page.goto(`${origin}/lab/strategies`);
    await page
      .getByRole("button", { name: `Inspect ${edited.fork.name}`, exact: true })
      .click();
    await page.getByLabel(/Source version/).selectOption(edited.version.id);
    const launch = page.getByRole("link", {
      name: "Run selected version",
      exact: true,
    });
    await launch.waitFor();
    assert.equal(
      await launch.getAttribute("href"),
      `/lab/experiments?strategy=${edited.fork.id}&version=${edited.version.id}`,
    );
    await launch.click();
    await page.waitForFunction(
      (expected) =>
        [...document.querySelectorAll("select")].some(
          (node) => node.value === expected,
        ),
      edited.version.id,
    );
    await page.getByLabel("Start session", { exact: true }).fill("2028-07-18");
    await page
      .getByLabel("End session (exclusive)", { exact: true })
      .fill("2028-07-24");
    await page
      .getByRole("button", { name: "Run historical experiment", exact: true })
      .click();
    await page.waitForURL(/\/lab\/experiments\/[0-9a-f-]{36}$/);
    await page
      .getByRole("heading", { name: "completed", exact: true })
      .waitFor({ timeout: 60000 });
    await page
      .getByRole("table", { name: /Exact stored session samples/ })
      .waitFor();
    const forkId = page.url().split("/").at(-1);
    const forkRunSnapshot = await readReport(page, forkId);
    const forkRun = forkRunSnapshot.view;
    assert.equal(forkRun.inputs.strategy_version_id, edited.version.id);
    assert.equal(forkRun.config_sha256, edited.version.config_sha256);
    const preservedVersions = await page.evaluate(
      async (id) => (await fetch(`/api/v1/strategies/${id}/versions`)).json(),
      edited.fork.id,
    );
    assert.deepEqual(preservedVersions, edited.history);
    records.push({
      width,
      fork_run_raw_json: forkRunSnapshot.raw,
      source_version_id: edited.version.id,
    });
    await page.screenshot({
      path: path.join(destination, `experiment-fork-report-${width}.png`),
      fullPage: true,
    });
    await page.goto(`${origin}/lab/experiments`);
    await page
      .getByRole("combobox", { name: "Strategy", exact: true })
      .selectOption({ label: "Mean Reversion" });
    const submit = page.getByRole("button", {
      name: "Run historical experiment",
      exact: true,
    });
    await page.waitForFunction(() =>
      [...document.querySelectorAll("button")].some(
        (node) =>
          node.textContent === "Run historical experiment" && !node.disabled,
      ),
    );
    await page.getByLabel("Start session", { exact: true }).fill("2028-07-18");
    await page
      .getByLabel("End session (exclusive)", { exact: true })
      .fill("2028-07-24");
    const seed = width === 1280 ? "18446744073709551615" : "42";
    await page.getByLabel("Random seed", { exact: true }).fill(seed);
    await page.screenshot({
      path: path.join(destination, `experiment-builder-${width}.png`),
      fullPage: true,
    });
    await submit.focus();
    assert(
      await submit.evaluate((element) => element === document.activeElement),
    );
    await page.keyboard.press("Enter");
    await page.waitForURL(/\/lab\/experiments\/[0-9a-f-]{36}$/);
    const originalId = page.url().split("/").at(-1);
    await page
      .getByRole("heading", { name: "completed", exact: true })
      .waitFor({ timeout: 60000 });
    const series = page.getByRole("table", {
      name: /Exact stored session samples/,
    });
    await series.waitFor();
    assert.deepEqual(
      await series
        .locator("tbody tr")
        .evaluateAll((rows) => rows.map((row) => row.cells[2].textContent)),
      ["$1,000.00", "$999.40", "$993.66", "$1,000.22"],
    );
    await page.locator(".experiment-chart .main-svg").first().waitFor();
    assert.deepEqual(
      await page
        .locator(".experiment-chart")
        .evaluateAll((nodes) =>
          nodes.map((node) => node._fullLayout.yaxis.type),
        ),
      ["linear", "linear", "linear"],
    );
    assert.equal(
      await page
        .getByRole("columnheader", { name: "Holdout", exact: true })
        .count(),
      1,
    );
    assert.equal(await page.getByText(seed, { exact: true }).count(), 1);
    const region = page.getByLabel("Exact session series table", {
      exact: true,
    });
    await region.focus();
    assert(
      await region.evaluate((element) => element === document.activeElement),
    );
    assert(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    );
    assert.deepEqual((await new AxeBuilder({ page }).analyze()).violations, []);
    await page.evaluate(() => scrollTo(0, 0));
    await page.screenshot({
      path: path.join(destination, `experiment-report-${width}.png`),
      fullPage: true,
    });
    await page.screenshot({
      path: path.join(destination, `experiment-report-top-${width}.png`),
    });
    const originalSnapshot = await readReport(page, originalId);
    const original = originalSnapshot.view;
    assert(original.inputs_canonical_json.includes(`"random_seed":${seed}`));
    assert(originalSnapshot.raw.includes(`"random_seed":${seed}`));
    await page
      .getByRole("button", { name: "Rerun with same inputs", exact: true })
      .click();
    await page.waitForURL(
      (url) => url.pathname !== `/lab/experiments/${originalId}`,
    );
    const rerunId = page.url().split("/").at(-1);
    await page
      .getByRole("heading", { name: "completed", exact: true })
      .waitFor({ timeout: 60000 });
    const rerunSnapshot = await readReport(page, rerunId);
    const rerun = rerunSnapshot.view;
    assert.notEqual(originalId, rerunId);
    assert.equal(original.inputs_canonical_json, rerun.inputs_canonical_json);
    for (const role of [
      "curve_artifact",
      "trade_artifact",
      "reproducibility_manifest",
    ])
      assert.equal(original[role].sha256, rerun[role].sha256);
    const preservedSnapshot = await readReport(page, originalId);
    const preserved = preservedSnapshot.view;
    assert.deepEqual(preserved, original);
    assert.equal(preservedSnapshot.raw, originalSnapshot.raw);
    records.push({
      width,
      seed,
      original_raw_json: originalSnapshot.raw,
      rerun_raw_json: rerunSnapshot.raw,
    });
    if (width === 360) {
      await page.goto(`${origin}/lab/experiments`);
      await page
        .getByRole("combobox", { name: "Strategy", exact: true })
        .selectOption({ label: "Mean Reversion" });
      await page.waitForFunction(() =>
        [...document.querySelectorAll("button")].some(
          (node) =>
            node.textContent === "Run historical experiment" && !node.disabled,
        ),
      );
      await page
        .getByRole("button", { name: "Run historical experiment", exact: true })
        .click();
      await page.waitForURL(/\/lab\/experiments\/[0-9a-f-]{36}$/);
      const cancelledId = page.url().split("/").at(-1);
      await page
        .getByRole("button", { name: "Cancel experiment", exact: true })
        .click();
      await page
        .getByRole("heading", { name: "cancelled", exact: true })
        .waitFor({ timeout: 10000 });
      assert.equal(await page.getByRole("table").count(), 0);
      await page.screenshot({
        path: path.join(destination, "experiment-cancelled-360.png"),
        fullPage: true,
      });
      const cancelledSnapshot = await readReport(page, cancelledId);
      const cancelled = cancelledSnapshot.view;
      assert.equal(cancelled.status, "cancelled");
      assert.equal(cancelled.report, null);
      records.push({ width, cancelled_raw_json: cancelledSnapshot.raw });
    }
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    await context.close();
  }
  fs.writeFileSync(
    path.join(destination, "experiment-ui.json"),
    JSON.stringify({ label: "SYNTHETIC_DATA_ONLY", records }, null, 2) + "\n",
  );
} finally {
  await browser.close();
}
