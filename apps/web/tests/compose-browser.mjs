import assert from "node:assert/strict";
import path from "node:path";
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
