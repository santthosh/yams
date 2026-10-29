// Actual disposable Docker API/worker. No invented recommendations or forecast values.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { chromium, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
const origin = process.env.YAMS_SMOKE_URL;
const destination = process.env.YAMS_SMOKE_EVIDENCE;
assert(origin && destination);
const browser = await chromium.launch();
const evidence = [];
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
    // Create using the real existing account screen. The smoke harness has
    // explicitly loaded the canonical offline snapshot before this journey.
    await page.goto(`${origin}/portfolios`);
    await expect(page.getByLabel("Published strategy version")).toBeEnabled();
    await page
      .getByLabel("Account name", { exact: true })
      .fill(`Decision browser ${width}`);
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
    await expect(
      page.getByRole("heading", { name: "Decision Center", exact: true }),
    ).toBeVisible();
    await expect(page.getByLabel("As-of pinned session")).not.toHaveValue("");
    await page.getByLabel("As-of pinned session").fill("2028-07-17");
    const reviewResponse = page.waitForResponse(
      (r) =>
        r.url().endsWith(`/portfolios/${account.id}/recommendations`) &&
        r.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "Generate paper review", exact: true })
      .click();
    const response = await reviewResponse;
    assert.equal(response.status(), 202);
    const accepted = await response.json();
    await expect(
      page.getByRole("region", { name: "Scenario comparison", exact: true }),
    ).toBeVisible({ timeout: 120000 });
    const original = await (
      await page.request.get(
        `${origin}/api/v1/recommendations/${accepted.recommendation_id}`,
      )
    ).json();
    assert.equal(original.forecast.status, "available");
    await expect(
      page
        .getByRole("combobox", { name: "Review", exact: true })
        .locator("option:checked"),
    ).toContainText("completed");
    assert.deepEqual(
      original.actions.map((a) => [a.asset_id, a.estimated_quantity]),
      [
        ["SYN:AAA", "2.857142"],
        ["SYN:BBB", "2.857142"],
        ["SYN:CCC", "2.985074"],
      ],
    );
    await expect(
      page.getByRole("region", { name: "Scenario comparison", exact: true }),
    ).toContainText("$1,000.00");
    await expect(
      page.getByRole("region", { name: "Proposed actions", exact: true }),
    ).toContainText("2.857142");
    await expect(
      page.getByText("SYNTHETIC_DATA_ONLY", { exact: true }).first(),
    ).toBeVisible();
    const reviewButton = page.getByRole("button", {
      name: "Review paper approval",
      exact: true,
    });
    await expect(reviewButton).toBeEnabled();
    await reviewButton.focus();
    await page.keyboard.press("Enter");
    await expect(
      page.getByRole("dialog", { name: "Confirm paper authorization" }),
    ).toBeVisible();
    const preview = await (
      await page.request.get(
        `${origin}/api/v1/recommendations/${accepted.recommendation_id}/approval-preview`,
      )
    ).json();
    await expect(page.getByRole("dialog")).toContainText(
      preview.indicative_eligible_open_at,
    );
    await page.screenshot({
      path: path.join(destination, `decision-confirm-${width}.png`),
      fullPage: true,
    });
    await page.keyboard.press("Escape");
    await expect(reviewButton).toBeFocused();
    const approvalRequests = [];
    let loseResponse = width === 360;
    await page.route(
      `**/recommendations/${accepted.recommendation_id}/apply`,
      async (route) => {
        approvalRequests.push({
          key: route.request().headers()["idempotency-key"],
          body: route.request().postDataJSON(),
        });
        if (loseResponse) {
          loseResponse = false;
          await route.fetch();
          await route.abort("failed");
        } else await route.continue();
      },
    );
    await reviewButton.click();
    if (width === 360) {
      await page
        .getByRole("button", { name: "Authorize paper orders", exact: true })
        .click();
      await expect(page.getByRole("alert")).toContainText(
        "Approval outcome unconfirmed",
      );
      // Reload simulates losing all transient React state after the mutation.
      await page.reload();
    } else {
      await page
        .getByRole("button", { name: "Authorize paper orders", exact: true })
        .dblclick();
    }
    await expect(
      page.getByRole("heading", {
        name: "Approved · execution pending",
        exact: true,
      }),
    ).toBeVisible({ timeout: 30000 });
    assert.equal(approvalRequests.length, 1);
    const savedKey = approvalRequests[0].key;
    const recovered = await (
      await page.request.get(
        `${origin}/api/v1/recommendations/${accepted.recommendation_id}/apply-result`,
        { headers: { "Idempotency-Key": savedKey } },
      )
    ).json();
    assert.equal(
      recovered.eligible_open_at,
      preview.indicative_eligible_open_at,
    );
    const before = await (
      await page.request.get(`${origin}/api/v1/portfolios/${account.id}`)
    ).json();
    assert.equal(before.cash_usd, "1000.00");
    assert.deepEqual(before.holdings, []);
    await page.screenshot({
      path: path.join(destination, `decision-pending-${width}.png`),
      fullPage: true,
    });
    let batch;
    for (let step = 0; step < 2; step++) {
      batch = await (
        await page.request.get(
          `${origin}/api/v1/order-batches/${recovered.batch_id}`,
        )
      ).json();
      if (batch.terminal) break;
      const advancing = page.waitForResponse(
        (r) =>
          r
            .url()
            .endsWith(`/order-batches/${recovered.batch_id}/advance-fixture`) &&
          r.request().method() === "POST",
      );
      await page
        .getByRole("button", {
          name: "Observe next fixture close explicitly",
          exact: true,
        })
        .click();
      const stepResponse = await advancing;
      assert.equal(stepResponse.status(), 202);
      const stepAccepted = await stepResponse.json();
      await expect
        .poll(
          async () => {
            const stepJob = await (
              await page.request.get(
                `${origin}/api/v1/jobs/${stepAccepted.job_id}`,
              )
            ).json();
            return stepJob.status;
          },
          { timeout: 60000 },
        )
        .toBe("completed");
      batch = await (
        await page.request.get(
          `${origin}/api/v1/order-batches/${recovered.batch_id}`,
        )
      ).json();
      if (!batch.terminal)
        await page
          .getByRole("button", {
            name: "Refresh authorization and posted state",
            exact: true,
          })
          .click();
    }
    await expect
      .poll(
        async () => {
          batch = await (
            await page.request.get(
              `${origin}/api/v1/order-batches/${recovered.batch_id}`,
            )
          ).json();
          fs.writeFileSync(
            path.join(destination, `decision-batch-checkpoint-${width}.json`),
            JSON.stringify({ account, original, recovered, batch }, null, 2),
          );
          return batch.terminal;
        },
        { timeout: 60000 },
      )
      .toBe(true);
    assert.equal(batch.status, "filled");
    assert.deepEqual(
      batch.orders.map((o) => [
        o.asset_id,
        o.filled_quantity,
        o.pending_quantity,
        o.cancelled_or_skipped_quantity,
      ]),
      original.actions
        .filter((a) => a.side !== "HOLD")
        .map((a) => [a.asset_id, a.estimated_quantity, "0.000000", "0.000000"]),
    );
    await page
      .getByRole("button", {
        name: "Refresh authorization and posted state",
        exact: true,
      })
      .click();
    await expect(
      page.getByRole("region", { name: "Posted holdings", exact: true }),
    ).toContainText("SYN:AAA");
    const posted = await (
      await page.request.get(`${origin}/api/v1/portfolios/${account.id}`)
    ).json();
    assert.equal(posted.cash_usd, "404.98");
    assert.equal(posted.holdings.length, 3);
    const finalDecision = await (
      await page.request.get(
        `${origin}/api/v1/recommendations/${accepted.recommendation_id}`,
      )
    ).json();
    assert.deepEqual(finalDecision.actions, original.actions);
    assert.deepEqual(finalDecision.forecast, original.forecast);
    assert.equal(finalDecision.status, "applied");
    await expect(
      page.getByText("Decision applied;", { exact: false }),
    ).toBeVisible();
    await page.screenshot({
      path: path.join(destination, `decision-layout-${width}.png`),
      fullPage: true,
    });
    const layout = await page.evaluate(() => ({
      viewport: innerWidth,
      document: document.documentElement.scrollWidth,
      elements: [...document.querySelectorAll("main *")]
        .map((e) => ({
          tag: e.tagName,
          class: e.className,
          text: e.textContent?.slice(0, 120),
          left: e.getBoundingClientRect().left,
          right: e.getBoundingClientRect().right,
          width: e.getBoundingClientRect().width,
        }))
        .filter((e) => e.right > innerWidth || e.left < 0),
    }));
    layout.textOverflow = await page.evaluate(() => {
      const out = [];
      const walker = document.createTreeWalker(
        document.body,
        NodeFilter.SHOW_TEXT,
      );
      while (walker.nextNode()) {
        const n = walker.currentNode;
        const p = n.parentElement;
        if (!p || !n.textContent?.trim()) continue;
        let clipped = false;
        for (let e = p; e; e = e.parentElement) {
          if (
            ["auto", "scroll", "hidden", "clip"].includes(
              getComputedStyle(e).overflowX,
            )
          ) {
            clipped = true;
            break;
          }
        }
        if (clipped) continue;
        const r = document.createRange();
        r.selectNodeContents(n);
        for (const box of r.getClientRects())
          if (box.right > innerWidth)
            out.push({
              tag: p.tagName,
              class: p.className,
              text: n.textContent.slice(0, 160),
              right: box.right,
              parentWidth: p.getBoundingClientRect().width,
            });
      }
      return out;
    });
    fs.writeFileSync(
      path.join(destination, `decision-layout-${width}.json`),
      JSON.stringify(layout, null, 2),
    );
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      true,
    );
    const axe = await new AxeBuilder({ page }).analyze();
    assert.deepEqual(axe.violations, []);
    await page.screenshot({
      path: path.join(destination, `decision-filled-${width}.png`),
      fullPage: true,
    });
    const ledgerBeforeDismiss = await (
      await page.request.get(
        `${origin}/api/v1/portfolios/${account.id}/transactions`,
      )
    ).json();
    await page.getByLabel("As-of pinned session").fill("2028-07-19");
    const nextReview = page.waitForResponse(
      (r) =>
        r.url().endsWith(`/portfolios/${account.id}/recommendations`) &&
        r.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "Generate paper review", exact: true })
      .click();
    const nextAccepted = await (await nextReview).json();
    await expect(
      page.getByRole("combobox", { name: "Review", exact: true }),
    ).toHaveValue(nextAccepted.recommendation_id);
    const dismissButton = page.getByRole("button", {
      name: "Dismiss decision",
      exact: true,
    });
    await expect(dismissButton).toBeEnabled({ timeout: 60000 });
    const dismissOriginal = await (
      await page.request.get(
        `${origin}/api/v1/recommendations/${nextAccepted.recommendation_id}`,
      )
    ).json();
    await dismissButton.click();
    await expect
      .poll(
        async () =>
          (
            await (
              await page.request.get(
                `${origin}/api/v1/recommendations/${nextAccepted.recommendation_id}`,
              )
            ).json()
          ).status,
      )
      .toBe("dismissed");
    const dismissFinal = await (
      await page.request.get(
        `${origin}/api/v1/recommendations/${nextAccepted.recommendation_id}`,
      )
    ).json();
    assert.deepEqual(dismissFinal.actions, dismissOriginal.actions);
    assert.deepEqual(
      await (
        await page.request.get(
          `${origin}/api/v1/portfolios/${account.id}/transactions`,
        )
      ).json(),
      ledgerBeforeDismiss,
    );
    await page.goto(origin);
    await expect(
      page.getByRole("link", {
        name: `Decision browser ${width}`,
        exact: true,
      }),
    ).toBeVisible();
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    evidence.push({
      width,
      account_id: account.id,
      accepted,
      original,
      recovered,
      before,
      posted,
      batch,
      approval_requests: approvalRequests,
      dismissed_review: {
        accepted: nextAccepted,
        summary_action: dismissOriginal.summary_action,
        disposition: dismissFinal.status,
        ledger_unchanged: true,
      },
      axe_violations: axe.violations,
      keyboard_confirmation: true,
      no_horizontal_overflow: true,
      lost_response_recovered_after_reload: width === 360,
    });
    await context.close();
  }
} finally {
  await browser.close();
}
fs.writeFileSync(
  path.join(destination, "decision-browser.json"),
  JSON.stringify(
    {
      classification: "RECORDED_APPLICATION_OUTPUT_NOT_INDEPENDENT_ORACLE",
      source: "SYNTHETIC_DATA_ONLY",
      evidence,
    },
    null,
    2,
  ),
);
console.log(
  "Real Decision Center: two viewport reviews/scenarios, keyboard confirmation, duplicate/response-loss recovery, pending unchanged cash, explicit replay, actual fills, dashboard and Axe passed",
);
