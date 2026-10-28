import { createHash } from "node:crypto";
import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import type { components } from "../../src/api/generated/schema";
import sample from "../candidate-transport.json" with { type: "json" };

// SYNTHETIC_DATA_ONLY transport scenarios. Actual persistence is exercised by
// the independent Docker browser journey, never inferred from these mocks.
async function registry(page: Page) {
  const original = structuredClone(
    sample.strategy,
  ) as components["schemas"]["StrategyV1"];
  const roots = new Map([[original.id, original]]);
  const other = {
    ...original,
    id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
    name: "Additional synthetic copy",
    is_template: false,
    template_key: null,
    published_version: {
      ...original.published_version,
      id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
      strategy_id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
    },
  };
  roots.set(other.id, other);
  const history = new Map([
    [original.id, [original.published_version]],
    [other.id, [other.published_version]],
  ]);
  const posts: { path: string; body: unknown }[] = [];
  let reject = 0;
  await page.route("**/api/v1/strategies**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const parts = url.pathname.split("/").filter(Boolean).slice(3);
    if (request.method() === "POST") {
      const body = request.postDataJSON();
      posts.push({ path: url.pathname, body });
      if (reject) {
        const status = reject;
        reject = 0;
        await route.fulfill({
          status,
          json: {
            error: {
              code:
                status === 409
                  ? "STATE_CONFLICT"
                  : status === 422
                    ? "VALIDATION_ERROR"
                    : "NOT_READY",
            },
          },
        });
        return;
      }
      const root = parts.length ? roots.get(parts[0]) : undefined;
      const config = structuredClone(parts.length ? body : body.config);
      const id = parts.length
        ? root!.id
        : "88888888-8888-4888-8888-888888888888";
      const prior = history.get(id) ?? [];
      const version = {
        ...original.published_version,
        id: prior.length
          ? "99999999-9999-4999-8999-999999999999"
          : "77777777-7777-4777-8777-777777777777",
        strategy_id: id,
        version: prior.length + 1,
        config,
        config_sha256: createHash("sha256")
          .update(JSON.stringify(config))
          .digest("hex"),
      };
      const created = {
        ...(root ?? original),
        id,
        name: root?.name ?? body.name,
        is_template: root?.is_template ?? false,
        template_key: root?.template_key ?? null,
        published_version: version,
      };
      roots.set(id, created);
      history.set(id, [...prior, version]);
      await route.fulfill({
        status: 201,
        json: parts.length ? version : created,
      });
      return;
    }
    if (!parts.length) {
      const ordered = [...roots.values()].sort((a, b) =>
        a.id.localeCompare(b.id),
      );
      const cursor = url.searchParams.get("cursor");
      const start = cursor
        ? ordered.findIndex((row) => row.id === cursor) + 1
        : 0;
      const items = ordered.slice(start, start + 1);
      await route.fulfill({
        json: {
          items,
          next_cursor: start + 1 < ordered.length ? items[0].id : null,
        },
      });
      return;
    }
    const root = roots.get(parts[0]);
    if (!root) {
      await route.fulfill({
        status: 404,
        json: { error: { code: "NOT_FOUND" } },
      });
      return;
    }
    if (parts[1] === "versions") {
      const versions = history.get(root.id)!;
      const following = url.searchParams.has("cursor");
      await route.fulfill({
        json: {
          items: following ? versions.slice(1) : versions.slice(0, 1),
          next_cursor:
            !following && versions.length > 1 ? versions[0].id : null,
        },
      });
      return;
    }
    await route.fulfill({ json: root });
  });
  return {
    original,
    roots,
    history,
    posts,
    rejectNext: (status: number) => {
      reject = status;
    },
  };
}

test("named fork and immutable append preserve source, typed inputs and accessible editing", async ({
  page,
}, info) => {
  const state = await registry(page);
  await page.goto("/lab");
  await expect(page).toHaveURL(/\/lab\/strategies$/);
  await expect(
    page.getByRole("heading", { name: "Strategy Lab", exact: true }),
  ).toBeVisible();
  const cap = page.getByLabel("Position cap (fraction)", { exact: true });
  await expect(cap).toHaveValue("0.2");
  await page
    .getByRole("button", { name: "Load more strategies", exact: true })
    .click();
  await expect(
    page.getByRole("button", {
      name: "Inspect Additional synthetic copy",
      exact: true,
    }),
  ).toBeVisible();
  // Re-inspecting the selected root must not leave loading stuck.
  await page
    .getByRole("button", {
      name: `Inspect ${state.original.name}`,
      exact: true,
    })
    .click();
  await expect(cap).toBeEnabled();
  await cap.fill("1.5");
  await page
    .getByRole("button", { name: "Publish new version", exact: true })
    .click();
  expect(state.posts).toHaveLength(0);
  await expect(cap).toBeFocused();
  await cap.fill("0.15");
  await expect(
    page.getByRole("region", { name: "Rule changes" }),
  ).toContainText("Position cap (fraction)");
  await page
    .getByLabel("New strategy name", { exact: true })
    .fill("Synthetic fork");
  await page.getByLabel("New strategy name", { exact: true }).press("Enter");
  await expect(
    page.getByRole("status").filter({ hasText: "Published version" }),
  ).toContainText("Published version 1 of Synthetic fork");
  expect(state.posts[0].body).toEqual({
    name: "Synthetic fork",
    config: {
      ...state.original.published_version.config,
      portfolio: {
        ...state.original.published_version.config.portfolio,
        max_position_weight: "0.15",
      },
    },
  });
  await expect(cap).toHaveValue("0.15");
  await page.getByLabel("Cash floor (fraction)", { exact: true }).fill("0.10");
  await page
    .getByRole("button", { name: "Publish new version", exact: true })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "Published version" }),
  ).toContainText("Published version 2 of Synthetic fork");
  expect(state.posts[1].body).not.toHaveProperty("config");
  expect(state.posts[1].body).toHaveProperty(
    "portfolio.min_cash_weight",
    "0.10",
  );
  await page
    .getByRole("button", { name: "Load more versions", exact: true })
    .click();
  await page
    .getByLabel(/Source version/)
    .selectOption("77777777-7777-4777-8777-777777777777");
  await expect(
    page.getByLabel("Cash floor (fraction)", { exact: true }),
  ).toHaveValue("0.05");
  await page
    .getByRole("button", {
      name: `Inspect ${state.original.name}`,
      exact: true,
    })
    .click();
  await expect(cap).toHaveValue("0.2");
  expect(state.history.get(state.original.id)).toEqual([
    state.original.published_version,
  ]);
  await page
    .getByText("See published rules and identity", { exact: true })
    .click();
  await expect(
    page.getByText(state.original.published_version.config_sha256, {
      exact: true,
    }),
  ).toBeVisible();
  await cap.focus();
  await page.keyboard.press("Tab");
  expect(await page.evaluate(() => document.activeElement?.tagName)).toBe(
    "INPUT",
  );
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: info.outputPath("strategy-editor.png"),
    fullPage: true,
  });
});

test("validation/conflict/uncertain publication keep drafts, including history reload", async ({
  page,
}) => {
  const state = await registry(page);
  await page.goto("/lab/strategies");
  const cap = page.getByLabel("Position cap (fraction)", { exact: true });
  await expect(cap).toHaveValue("0.2");
  await cap.fill("0.15");
  state.rejectNext(503);
  await page
    .getByRole("button", { name: "Publish new version", exact: true })
    .click();
  await expect(page.locator("main").getByRole("alert")).toContainText(
    "Inspect or reload version history",
  );
  await expect(cap).toHaveValue("0.15");
  await page
    .getByRole("button", { name: "Reload history", exact: true })
    .click();
  await expect(cap).toBeEnabled();
  await expect(cap).toHaveValue("0.15");
  expect(state.posts).toHaveLength(1);
  state.rejectNext(422);
  await page
    .getByRole("button", { name: "Publish new version", exact: true })
    .click();
  await expect(page.locator("main").getByRole("alert")).toContainText(
    "rules were rejected",
  );
  await expect(cap).toHaveValue("0.15");
  state.rejectNext(409);
  await page.getByLabel("New strategy name", { exact: true }).fill("Duplicate");
  await page
    .getByRole("button", { name: "Create named fork", exact: true })
    .click();
  await expect(page.locator("main").getByRole("alert")).toContainText(
    "name is already in use",
  );
  await expect(cap).toHaveValue("0.15");
  state.rejectNext(503);
  await page
    .getByLabel("New strategy name", { exact: true })
    .fill("Unconfirmed fork");
  await page
    .getByRole("button", { name: "Create named fork", exact: true })
    .click();
  await expect(page.locator("main").getByRole("alert")).toContainText(
    "Reload strategies and inspect the fork",
  );
  await expect(cap).toHaveValue("0.15");
  expect(state.history.get(state.original.id)).toHaveLength(1);
});

test("empty registry and unavailable history are explicit and recoverable", async ({
  page,
}) => {
  await page.route("**/api/v1/strategies**", (route) =>
    route.fulfill({ json: { items: [], next_cursor: null } }),
  );
  await page.goto("/lab/strategies");
  await expect(
    page.getByRole("heading", { name: "No saved strategies" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Publish new version" }),
  ).toHaveCount(0);
  await page.unroute("**/api/v1/strategies**");
  const state = await registry(page);
  await page.route(
    `**/api/v1/strategies/${state.original.id}/versions*`,
    (route) =>
      route.fulfill({ status: 404, json: { error: { code: "NOT_FOUND" } } }),
  );
  await page
    .getByRole("button", { name: "Reload strategies", exact: true })
    .click();
  await expect(page.locator("main").getByRole("alert")).toContainText(
    "history is unavailable",
  );
  await expect(
    page.getByRole("button", { name: "Publish new version" }),
  ).toHaveCount(0);
  await page.unroute(`**/api/v1/strategies/${state.original.id}/versions*`);
  await page
    .getByRole("button", { name: "Reload history", exact: true })
    .click();
  await expect(
    page.getByLabel("Position cap (fraction)", { exact: true }),
  ).toBeEnabled();
});
