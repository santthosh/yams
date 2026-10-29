import { createElement } from "react";
import { randomUUID } from "node:crypto";
import fs from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import type { components } from "../../src/api/generated/schema";
import { OrderBatchState } from "../../src/components/portfolios/OrderBatchState";
import fixtures from "../portfolio-transport.json" with { type: "json" };

type S = components["schemas"];
const cash = fixtures.cash as S["PaperPortfolioV1"];
const posted = fixtures.posted as S["PaperPortfolioV1"];
const events = fixtures.events as Record<string, S["PortfolioTransactionV1"]>;
// Explicit SYNTHETIC_DATA_ONLY service fixtures, not product fallback values.
async function transport(page: Page, initial: S["PaperPortfolioV1"][] = []) {
  const records = new Map(initial.map((row) => [row.id, structuredClone(row)]));
  const posts: { key: string; body: S["PortfolioCreateRequest"] }[] = [];
  const accepted = new Map<string, S["PaperPortfolioV1"]>();
  let reject = 0;
  let failList = false;
  let historyPaged = false;
  await page.route("**/api/v1/strategies**", (route) =>
    route.fulfill({ json: { items: [fixtures.strategy], next_cursor: null } }),
  );
  await page.route("**/api/v1/portfolios**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const parts = url.pathname.split("/").filter(Boolean).slice(3);
    if (request.method() === "POST") {
      const body = request.postDataJSON() as S["PortfolioCreateRequest"];
      posts.push({ key: request.headers()["idempotency-key"], body });
      if (reject > 0) {
        const status = reject;
        reject = 0;
        await route.fulfill({
          status,
          json: {
            error: {
              code: "VALIDATION_ERROR",
              message: "Invalid synthetic test input",
            },
          },
        });
        return;
      }
      const row: S["PaperPortfolioV1"] = accepted.get(
        request.headers()["idempotency-key"],
      ) ?? {
        ...structuredClone(cash),
        id: records.size ? randomUUID() : cash.id,
        name: body.name,
        opening_cash_usd: body.opening_cash_usd,
        cash_usd: body.opening_cash_usd,
        total_value_usd: body.opening_cash_usd,
        strategy_version_id: body.strategy_version_id,
        valuation_mode: body.mode,
        valuation: {
          ...cash.valuation,
          total_value_usd: body.opening_cash_usd,
        },
      };
      accepted.set(request.headers()["idempotency-key"], row);
      records.set(row.id, row);
      if (reject === -1) {
        reject = 0;
        await route.abort("connectionreset");
        return;
      }
      await route.fulfill({ status: 201, json: row });
      return;
    }
    if (!parts.length) {
      if (failList) {
        await route.fulfill({
          status: 503,
          json: {
            error: { message: "RAW_STACK_TRACE secret_database_password" },
          },
        });
        return;
      }
      const mode = url.searchParams.get("mode");
      await route.fulfill({
        json: {
          items: [...records.values()].filter(
            (row) => !mode || row.valuation_mode === mode,
          ),
          next_cursor: null,
        },
      });
      return;
    }
    const row = records.get(parts[0]);
    if (!row) {
      await route.fulfill({
        status: 404,
        json: { error: { code: "NOT_FOUND" } },
      });
      return;
    }
    if (parts.length === 1) {
      await route.fulfill({ json: row });
      return;
    }
    const full =
      row.last_sequence === 3
        ? [events.fill, events.approval, events.funding]
        : [events.funding];
    const cursor = url.searchParams.get("cursor");
    await route.fulfill({
      json: {
        portfolio_id: row.id,
        mode: row.valuation_mode,
        paper_only: true,
        warnings: [fixtures.label],
        items:
          historyPaged && !cursor
            ? full.slice(0, 1)
            : cursor
              ? full.slice(1)
              : full,
        next_cursor:
          historyPaged && !cursor && full.length > 1 ? full[0].id : null,
      },
    });
  });
  return {
    posts,
    records,
    reject: (status: number) => {
      reject = status;
    },
    failList: () => {
      failList = true;
    },
    pageHistory: () => {
      historyPaged = true;
    },
  };
}

test("empty account list and keyboard creation show confirmed100%cash", async ({
  page,
}) => {
  const api = await transport(page);
  await page.goto("/portfolios");
  await expect(page.getByText("No paper accounts yet")).toBeVisible();
  await expect(page.getByLabel("Published strategy version")).toBeEnabled();
  await page.getByLabel("Account name", { exact: true }).focus();
  await page.keyboard.type("Keyboard paper");
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Starting capital (USD)")).toBeFocused();
  await expect(page.getByLabel("Starting capital (USD)")).toHaveValue(
    "1000.00",
  );
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Published strategy version")).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Account data source")).toBeFocused();
  await page.keyboard.press("Tab");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(`/portfolios/${cash.id}`);
  await expect(
    page.getByRole("heading", { name: "Keyboard paper" }),
  ).toBeVisible();
  await expect(page.getByText("Cash weight 100%")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "No posted holdings" }),
  ).toBeVisible();
  expect(api.posts).toHaveLength(1);
  expect(api.posts[0].body.opening_cash_usd).toBe("1000.00");
  expect(api.posts[0].key).toMatch(/^[0-9a-f-]{36}$/);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});

test("uncertain creation freezes original body and retries its original key", async ({
  page,
}) => {
  const api = await transport(page);
  api.reject(-1);
  await page.goto("/portfolios");
  await page.getByLabel("Account name", { exact: true }).fill("Recover me");
  await page
    .getByRole("button", { name: "Create paper account", exact: true })
    .click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    "Connection lost",
  );
  await expect(page.getByLabel("Starting capital (USD)")).toBeDisabled();
  await page
    .getByRole("button", { name: "Retry same account creation" })
    .click();
  await expect(page).toHaveURL(`/portfolios/${cash.id}`);
  expect(api.posts).toHaveLength(2);
  expect(api.posts[0]).toEqual(api.posts[1]);
  expect(api.records.size).toBe(1);
});

test("server validation returns to editable form without inventing an account", async ({
  page,
}) => {
  const api = await transport(page);
  api.reject(422);
  await page.goto("/portfolios");
  await page
    .getByLabel("Account name", { exact: true })
    .fill("Invalid capital");
  await page.getByLabel("Starting capital (USD)").fill("0");
  await page
    .getByRole("button", { name: "Create paper account", exact: true })
    .click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    "positive starting capital",
  );
  await expect(page.getByLabel("Starting capital (USD)")).toBeEnabled();
  expect(api.records.size).toBe(0);
  await page.getByLabel("Starting capital (USD)").fill("1000.00");
  await page
    .getByRole("button", { name: "Create paper account", exact: true })
    .click();
  await expect(page).toHaveURL(`/portfolios/${cash.id}`);
  expect(api.posts[0].key).not.toBe(api.posts[1].key);
});

test("posted holdings and paginated ledger use exact backend values", async ({
  page,
}, info) => {
  const api = await transport(page, [posted]);
  api.pageHistory();
  await page.goto(`/portfolios/${posted.id}`);
  await expect(page.getByRole("heading", { name: posted.name })).toBeVisible();
  const value = page
    .getByRole("heading", { name: "Account value", exact: true })
    .locator("..");
  await expect(value).toContainText("$1,001.80");
  await expect(
    page.getByRole("region", { name: "Posted holdings" }),
  ).toContainText("$202.00");
  await expect(
    page.getByRole("region", { name: "Posted holdings" }),
  ).toContainText("2");
  await expect(
    page.getByText("Commission $0.00 · Slippage $0.20"),
  ).toBeVisible();
  await expect(
    page.getByText("Order batch inspection comes in 0.0.5"),
  ).toBeVisible();
  await page.getByRole("button", { name: "Load older transactions" }).click();
  await expect(
    page.getByRole("heading", { name: "opening funding" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.screenshot({
    path: info.outputPath(`portfolio-${info.project.name}.png`),
    fullPage: true,
  });
});

for (const kind of ["missing", "stale"] as const) {
  test(`${kind} marks keep known cash/shares separate from unavailable value`, async ({
    page,
  }) => {
    const row = fixtures[kind] as S["PaperPortfolioV1"];
    await transport(page, [row]);
    await page.goto(`/portfolios/${row.id}`);
    await expect(
      page.getByText(`Valuation ${row.valuation.status}`, { exact: false }),
    ).toBeVisible();
    await expect(
      page
        .getByRole("heading", { name: "Posted cash", exact: true })
        .locator(".."),
    ).toContainText("$799.80");
    await expect(
      page.getByRole("region", { name: "Posted holdings" }),
    ).toContainText("Unavailable");
    await expect(
      page
        .getByRole("heading", { name: "Account value", exact: true })
        .locator(".."),
    ).toContainText("Unavailable");
  });
}

test("independent source accounts and read errors stay distinct", async ({
  page,
}) => {
  const research: S["PaperPortfolioV1"] = {
    ...structuredClone(cash),
    id: "77777777-7777-4777-8777-777777777777",
    name: "Independent research",
    valuation_mode: "research_market_data",
    cash_usd: "2000.00",
    opening_cash_usd: "2000.00",
    total_value_usd: "2000.00",
    valuation: { ...cash.valuation, total_value_usd: "2000.00", warnings: [] },
  };
  const api = await transport(page, [cash, research]);
  await page.goto("/portfolios");
  await expect(
    page.getByRole("link", { name: cash.name, exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: research.name, exact: true }),
  ).toBeVisible();
  await page.getByLabel("Source filter").selectOption("research_market_data");
  await expect(
    page.getByRole("link", { name: cash.name, exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("link", { name: research.name, exact: true }),
  ).toBeVisible();
  api.failList();
  await page.getByRole("button", { name: "Reload accounts" }).click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    "Paper accounts are unavailable",
  );
  await expect(page.getByText("No paper accounts yet")).toHaveCount(0);
  await expect(page.getByText("secret_database_password")).toHaveCount(0);
});

test("service-fixture pending and terminal shortfall components never imply a fill", async ({
  page,
}, info) => {
  for (const name of ["pending", "partial", "cancelled"] as const) {
    const batch = fixtures.batches[name] as S["PaperOrderBatchV1"];
    const markup = renderToStaticMarkup(
      createElement(OrderBatchState, { batch }),
    );
    await page.setContent(
      `<html lang="en"><head><title>Synthetic service fixture</title></head><body><main><h1>SYNTHETIC_DATA_ONLY</h1><h2>Authorized intent</h2>${markup}</main></body></html>`,
    );
    const styles = fs
      .readdirSync(".next/static/chunks")
      .filter((name) => name.endsWith(".css"))
      .map((name) => fs.readFileSync(`.next/static/chunks/${name}`, "utf8"))
      .join("\n");
    await page.addStyleTag({ content: styles });
    await expect(
      page.getByRole("heading", {
        name:
          name === "pending"
            ? "Approved · execution pending"
            : "Closed paper batch",
      }),
    ).toBeVisible();
    await expect(
      page.getByRole("columnheader", { name: "Pending", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText(
        name === "pending"
          ? "Not all orders have posted"
          : "No remaining intent",
        { exact: false },
      ),
    ).toBeVisible();
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    if (info.project.name === "mobile") {
      const region = page.getByRole("region", {
        name: "Approved order quantities",
      });
      await region.focus();
      await page.keyboard.press("ArrowRight");
      await expect
        .poll(() => region.evaluate((node) => node.scrollLeft))
        .toBeGreaterThan(0);
    }
    if (name === "pending")
      await page.screenshot({
        path: info.outputPath(`pending-${info.project.name}.png`),
        fullPage: true,
      });
  }
});

test("long account names wrap and unknown accounts stay errors", async ({
  page,
}) => {
  const row: S["PaperPortfolioV1"] = {
    ...structuredClone(cash),
    name: "A".repeat(120),
  };
  await transport(page, [row]);
  await page.goto(`/portfolios/${row.id}`);
  await expect(
    page.getByRole("heading", { name: row.name, exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.goto("/portfolios/99999999-9999-4999-8999-999999999999");
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    "Paper account not found",
  );
  await expect(
    page.getByRole("heading", { name: "Posted cash", exact: true }),
  ).toHaveCount(0);
});
