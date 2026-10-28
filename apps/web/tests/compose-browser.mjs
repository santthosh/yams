import assert from "node:assert/strict";
import path from "node:path";
import fs from "node:fs";
import { chromium } from "@playwright/test";

const origin = process.env.YAMS_SMOKE_URL;
const destination = process.env.YAMS_SMOKE_EVIDENCE;
assert(origin && destination && process.env.YAMS_SMOKE_JOB);
const browser = await chromium.launch();
try {
  for (const width of [360, 1280]) {
    const page = await browser.newPage({ viewport: { width, height: 900 } });
    const errors = [];
    const external = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.route("**/*", async (route) => {
      if (new URL(route.request().url()).origin !== origin) {
        external.push(route.request().url());
        await route.abort();
      } else await route.continue();
    });
    await page.goto(origin);
    await page.getByText("Ready to explore", { exact: true }).waitFor();
    await page.getByText("SYNTHETIC_DATA_ONLY", { exact: true }).waitFor();
    assert(
      (await page
        .getByText("Paper only", { exact: true })
        .first()
        .isVisible()) ||
        (await page
          .getByText("Paper only", { exact: true })
          .last()
          .isVisible()),
    );
    await page.screenshot({
      path: path.join(destination, `dashboard-${width}.png`),
      fullPage: true,
    });
    await page.getByRole("link", { name: "Explore your workspace" }).click();
    await page.getByText("en-US", { exact: true }).waitFor();
    await page
      .getByLabel("Job ID", { exact: true })
      .fill(process.env.YAMS_SMOKE_JOB);
    await page.getByRole("button", { name: "Check status" }).click();
    await page
      .getByRole("heading", { name: "Completed", exact: true })
      .waitFor();
    await page.screenshot({
      path: path.join(destination, `settings-${width}.png`),
      fullPage: true,
    });
    await page.goto(`${origin}/settings/data`);
    await page
      .getByRole("heading", { name: "Market data", exact: true })
      .waitFor();
    await page.getByRole("button", { name: "Refresh selected source" }).click();
    await page
      .getByRole("heading", { name: "Completed", exact: true })
      .waitFor({ timeout: 60000 });
    await page.getByLabel("Symbol or asset ID").fill("AAA");
    await page.getByRole("button", { name: "Search assets" }).click();
    await page.getByText("AAA · XNYS", { exact: false }).waitFor();
    await page.screenshot({
      path: path.join(destination, `data-${width}.png`),
      fullPage: true,
    });
    await page.goto(`${origin}/lab/candidates`);
    const evaluate = page.getByRole("button", {
      name: "Evaluate pinned inputs",
    });
    await evaluate.waitFor();
    await page.waitForFunction(() =>
      [...document.querySelectorAll("button")].some(
        (button) =>
          button.textContent === "Evaluate pinned inputs" && !button.disabled,
      ),
    );
    const runs = [];
    for (const session of ["2028-07-17", "2028-07-17", "2027-01-04"]) {
      await page.getByLabel("As-of session").fill(session);
      const accepted = page.waitForResponse(
        (response) =>
          response.url() === `${origin}/api/v1/strategy-evaluations` &&
          response.request().method() === "POST",
      );
      await evaluate.click();
      const admission = await accepted;
      assert.equal(admission.status(), 202);
      const { evaluation_id } = await admission.json();
      await page.waitForURL(`**evaluation=${evaluation_id}*`);
      await page
        .getByRole("heading", { name: "Target allocation", exact: true })
        .waitFor({ timeout: 60000 });
      let sealed;
      const deadline = Date.now() + 60000;
      do {
        const response = await page.request.get(
          `${origin}/api/v1/strategy-evaluations/${evaluation_id}`,
        );
        assert.equal(response.status(), 200);
        sealed = await response.json();
        if (!["queued", "running"].includes(sealed.status)) break;
        await new Promise((resolve) => setTimeout(resolve, 200));
      } while (Date.now() < deadline);
      assert.equal(sealed.status, "completed");
      assert.equal(sealed.result.as_of_session, session);
      assert.equal(sealed.mode, "synthetic_fixture");
      assert.match(sealed.result_sha256, /^[0-9a-f]{64}$/);
      if (session === "2028-07-17") {
        assert.equal(sealed.result.decision_cutoff_utc, "2028-07-18T12:30:00Z");
        assert.deepEqual(sealed.result.selected_ids, [
          "SYN:AAA",
          "SYN:BBB",
          "SYN:CCC",
        ]);
        assert.equal(sealed.result.cash_target_weight, "0.4");
        assert.deepEqual(
          sealed.result.target_weights.map((target) => target.weight),
          ["0.2", "0.2", "0.2"],
        );
      } else {
        assert.equal(sealed.result.decision_cutoff_utc, "2027-01-05T13:30:00Z");
        assert.equal(sealed.result.cash_target_weight, "1");
        assert.deepEqual(sealed.result.target_weights, []);
        await page.getByRole("heading", { name: "Cash-only target" }).waitFor();
      }
      runs.push(sealed);
    }
    assert.equal(runs[0].result_sha256, runs[1].result_sha256);
    assert.notEqual(runs[0].id, runs[1].id);
    await page.reload();
    await page.getByRole("heading", { name: "Cash-only target" }).waitFor();
    await page.screenshot({
      path: path.join(destination, `candidates-empty-${width}.png`),
      fullPage: true,
    });
    await page.getByLabel("Evaluation ID").fill(runs[0].id);
    await page.getByRole("button", { name: "Load saved evaluation" }).click();
    await page
      .getByRole("heading", { name: "Target allocation", exact: true })
      .waitFor();
    await page.screenshot({
      path: path.join(destination, `candidates-${width}.png`),
      fullPage: true,
    });
    fs.writeFileSync(
      path.join(destination, `candidate-runs-${width}.json`),
      JSON.stringify(runs, null, 2) + "\n",
    );
    await page.goto(`${origin}/settings/data`);
    await page.getByLabel("Source mode").selectOption("research_market_data");
    await page
      .getByRole("heading", { name: "No registered snapshot" })
      .waitFor();
    await page.screenshot({
      path: path.join(destination, `data-research-${width}.png`),
      fullPage: true,
    });
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    await page.close();
  }
} finally {
  await browser.close();
}
