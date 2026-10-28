import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { chromium } from "@playwright/test";

const origin = process.env.YAMS_SMOKE_URL;
const destination = process.env.YAMS_SMOKE_EVIDENCE;
assert(origin && destination);
const browser = await chromium.launch();
try {
  const page = await browser.newPage();
  await page.goto(origin);
  const evidence = await page.evaluate(async () => {
    const request = async (route, body) => {
      const response = await fetch(
        `/api/v1/${route}`,
        body === undefined
          ? {}
          : {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(body),
            },
      );
      return { status: response.status, body: await response.json() };
    };
    const get = async (route) => {
      const response = await request(route);
      if (response.status !== 200)
        throw new Error(`Read ${route}: ${response.status}`);
      return response.body;
    };
    const strategies = await get("strategies");
    const template = strategies.items.find(
      (row) =>
        row.is_template &&
        row.published_version.config.signals.kind === "mean_reversion",
    );
    if (!template) throw new Error("Missing mean-reversion template");
    const snapshots = await get("data/snapshots?mode=synthetic_fixture");
    const inputs = {
      strategy_version_id: template.published_version.id,
      snapshot_id: snapshots.items[0].id,
      start_session: "2028-07-18",
      end_session_exclusive: "2028-07-24",
      initial_capital_usd: "1000.00",
      benchmark_asset_id: "SYN:SPY",
      execution_policy_id: "us_eod_next_open_v1",
      random_seed: 42,
      evaluation_split: { kind: "chronological", holdout_fraction: 0.25 },
    };
    const wait = async (id) => {
      const deadline = Date.now() + 60000;
      while (Date.now() < deadline) {
        const run = await get(`experiments/${id}`);
        if (["completed", "failed", "cancelled"].includes(run.status))
          return run;
        await new Promise((resolve) => setTimeout(resolve, 100));
      }
      throw new Error("Experiment did not terminate in time");
    };
    const runs = [];
    for (let index = 0; index < 2; index++) {
      const created = await request("experiments", inputs);
      if (created.status !== 202)
        throw new Error(`Creation: ${created.status}`);
      const id = created.body.experiment_id;
      const run = await wait(id);
      if (run.status !== "completed")
        throw new Error(`Experiment: ${run.status}`);
      const url = `experiments/${id}`;
      const first = await get(`${url}/series?limit=2`);
      const next = await get(
        `${url}/series?limit=2&cursor=${first.next_cursor}`,
      );
      const crossCursor = await request(
        `${url}/trades?limit=2&cursor=${first.next_cursor}`,
      );
      const trades = await get(`${url}/trades`);
      const terminalCancel = await request(
        `jobs/${created.body.job_id}/cancel`,
        {},
      );
      runs.push({ run, first, next, trades, crossCursor, terminalCancel });
    }
    const accepted = await request("experiments", inputs);
    const cancel = await request(`jobs/${accepted.body.job_id}/cancel`, {});
    const cancelled = await wait(accepted.body.experiment_id);
    return { runs, cancel, cancelled, history: await get("experiments") };
  });
  for (const run of evidence.runs) {
    assert.equal(run.crossCursor.status, 422);
    assert.equal(run.terminalCancel.status, 409);
    assert.deepEqual(
      [...run.first.items, ...run.next.items].map(
        (row) => row.portfolio_nav_usd,
      ),
      ["1000.00", "999.40", "993.66", "1000.22"],
    );
    assert.equal(run.trades.items.length, 3);
    assert.equal(run.run.metrics.trade_count, 3);
    assert(run.run.warnings.includes("SYNTHETIC_DATA_ONLY"));
  }
  assert.notEqual(evidence.runs[0].run.id, evidence.runs[1].run.id);
  assert.equal(
    evidence.runs[0].run.curve_artifact.sha256,
    evidence.runs[1].run.curve_artifact.sha256,
  );
  assert.equal(
    evidence.runs[0].run.trade_artifact.sha256,
    evidence.runs[1].run.trade_artifact.sha256,
  );
  assert.equal(
    evidence.runs[0].run.reproducibility_manifest.sha256,
    evidence.runs[1].run.reproducibility_manifest.sha256,
  );
  assert.equal(evidence.cancel.status, 202);
  assert.equal(evidence.cancelled.status, "cancelled");
  assert.equal(evidence.cancelled.report, null);
  fs.writeFileSync(
    path.join(destination, "experiment-public.json"),
    JSON.stringify(evidence, null, 2) + "\n",
  );
} finally {
  await browser.close();
}
