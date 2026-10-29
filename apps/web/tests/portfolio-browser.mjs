// Actual disposable Docker application. No mocked API responses or market data.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { chromium, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const origin = process.env.YAMS_SMOKE_URL;
const destination = process.env.YAMS_SMOKE_EVIDENCE;
const phase = process.env.YAMS_SMOKE_PORTFOLIO_PHASE;
const stage = process.env.YAMS_SMOKE_PORTFOLIO_STAGE || "initial";
assert(origin && destination && ["create", "inspect"].includes(phase));
const savedFile = path.join(destination, "portfolio-browser-accounts.json");
const saved =
  phase === "inspect"
    ? JSON.parse(fs.readFileSync(savedFile, "utf8")).accounts
    : [];
const browser = await chromium.launch();
const inspected = [];
try {
  for (const width of [360, 1280]) {
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
    if (phase === "create") {
      await page.goto(`${origin}/portfolios`);
      await page
        .getByRole("heading", { name: "Paper portfolios", exact: true })
        .waitFor();
      await expect(page.getByLabel("Published strategy version")).toBeEnabled();
      await page.getByLabel("Account name", { exact: true }).focus();
      await page.keyboard.type(`Browser paper ${width}`);
      await page.keyboard.press("Tab");
      await expect(page.getByLabel("Starting capital (USD)")).toBeFocused();
      await expect(page.getByLabel("Starting capital (USD)")).toHaveValue(
        "1000.00",
      );
      const created = page.waitForResponse(
        (response) =>
          response.url() === `${origin}/api/v1/portfolios` &&
          response.request().method() === "POST",
      );
      await page
        .getByRole("button", { name: "Create paper account", exact: true })
        .click();
      const response = await created;
      assert.equal(response.status(), 201);
      const account = await response.json();
      const key = response.request().headers()["idempotency-key"];
      const body = response.request().postDataJSON();
      assert.match(key, /^[0-9a-f-]{36}$/);
      await page.waitForURL(`${origin}/portfolios/${account.id}`);
      await expect(
        page.getByText("Cash weight 100%", { exact: true }),
      ).toBeVisible();
      await expect(
        page.getByRole("heading", { name: "No posted holdings", exact: true }),
      ).toBeVisible();
      assert.equal(account.cash_usd, "1000.00");
      assert.deepEqual(account.holdings, []);
      const retry = await page.request.post(`${origin}/api/v1/portfolios`, {
        data: body,
        headers: { "Idempotency-Key": key, Origin: origin },
      });
      assert.equal(retry.status(), 201);
      assert.equal((await retry.json()).id, account.id);
      const history = await (
        await page.request.get(
          `${origin}/api/v1/portfolios/${account.id}/transactions`,
        )
      ).json();
      assert.deepEqual(
        history.items.map((row) => row.kind),
        ["opening_funding"],
      );
      assert.equal(history.items[0].cash_delta_usd, "1000.00");
      saved.push({ width, account, key, body, history });
      await page.screenshot({
        path: path.join(destination, `portfolio-cash-${width}.png`),
        fullPage: true,
      });
    } else {
      const record = saved.find((row) => row.width === width);
      assert(record);
      await page.goto(`${origin}/portfolios/${record.account.id}`);
      await expect(
        page.getByText("Cash weight 100%", { exact: true }),
      ).toBeVisible();
      const current = await (
        await page.request.get(
          `${origin}/api/v1/portfolios/${record.account.id}`,
        )
      ).json();
      assert.equal(current.created_at, record.account.created_at);
      assert.equal(current.cash_usd, "1000.00");
      assert.equal(current.revision, 1);
      assert.deepEqual(current.holdings, []);
      const history = await (
        await page.request.get(
          `${origin}/api/v1/portfolios/${record.account.id}/transactions`,
        )
      ).json();
      assert.deepEqual(history, record.history);
      const retry = await page.request.post(`${origin}/api/v1/portfolios`, {
        data: record.body,
        headers: { "Idempotency-Key": record.key, Origin: origin },
      });
      assert.equal(retry.status(), 201);
      assert.equal((await retry.json()).id, record.account.id);
      const postedId = process.env.YAMS_SMOKE_POSTED_PORTFOLIO;
      assert(postedId);
      await page.goto(`${origin}/portfolios/${postedId}`);
      await page
        .getByRole("region", { name: "Posted holdings", exact: true })
        .waitFor();
      await expect(
        page
          .getByRole("heading", { name: "Posted cash", exact: true })
          .locator(".."),
      ).toContainText("$859.76");
      await expect(
        page
          .getByRole("heading", { name: "Account value", exact: true })
          .locator(".."),
      ).toContainText("$1,063.36");
      await expect(
        page.getByRole("region", { name: "Posted holdings", exact: true }),
      ).toContainText("SYN:AAA");
      await expect(
        page.getByText("Gross $140.24 · Commission $0.00 · Slippage $0.14", {
          exact: true,
        }),
      ).toBeVisible();
      await expect(
        page.getByText("Order batch inspection comes in 0.0.5", {
          exact: true,
        }),
      ).toBeVisible();
      await page
        .getByText("Inspect event lineage", { exact: true })
        .first()
        .click();
      const posted = await (
        await page.request.get(`${origin}/api/v1/portfolios/${postedId}`)
      ).json();
      assert.equal(posted.cash_usd, "859.76");
      assert.equal(posted.holdings[0].quantity, "2.000000");
      assert.equal(posted.holdings[0].total_basis_usd, "140.24");
      inspected.push({
        width,
        stage,
        id: posted.id,
        cash_usd: posted.cash_usd,
        quantity: posted.holdings[0].quantity,
        revision: posted.revision,
      });
      await page.screenshot({
        path: path.join(destination, `portfolio-posted-${stage}-${width}.png`),
        fullPage: true,
      });
    }
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      true,
    );
    assert.deepEqual((await new AxeBuilder({ page }).analyze()).violations, []);
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    await context.close();
  }
  if (phase === "create") {
    assert.notEqual(saved[0].account.id, saved[1].account.id);
    fs.writeFileSync(
      savedFile,
      JSON.stringify(
        { label: "SYNTHETIC_DATA_ONLY", accounts: saved },
        null,
        2,
      ) + "\n",
    );
  } else
    fs.writeFileSync(
      path.join(destination, `portfolio-browser-${stage}.json`),
      JSON.stringify({ label: "SYNTHETIC_DATA_ONLY", inspected }, null, 2) +
        "\n",
    );
} finally {
  await browser.close();
}
