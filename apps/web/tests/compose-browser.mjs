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
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    await page.close();
  }
} finally {
  await browser.close();
}
