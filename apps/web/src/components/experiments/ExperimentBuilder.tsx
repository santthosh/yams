"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { createApiClient } from "../../api/generated/client";
import type { components } from "../../api/generated/schema";
import {
  Card,
  DataProvenanceBadge,
  EmptyState,
  WarningsPanel,
} from "../evidence";
import { Button } from "../ui/button";
import {
  coveredWindow,
  experimentError,
  positiveMoney,
  serializeExperiment,
  validSeed,
} from "./inputs";

type S = components["schemas"];
export function ExperimentBuilder() {
  const router = useRouter();
  const [roots, setRoots] = useState<S["StrategyV1"][]>([]);
  const [rootId, setRootId] = useState("");
  const [versions, setVersions] = useState<S["StrategyVersionV1"][]>([]);
  const [versionId, setVersionId] = useState("");
  const [snapshots, setSnapshots] = useState<S["SnapshotV1"][]>([]);
  const [snapshotId, setSnapshotId] = useState("");
  const [history, setHistory] = useState<S["ExperimentSummaryV1"][]>([]);
  const [historyCursor, setHistoryCursor] = useState<string | null>(null);
  const [rootCursor, setRootCursor] = useState<string | null>(null);
  const [snapshotCursor, setSnapshotCursor] = useState<string | null>(null);
  const [versionCursor, setVersionCursor] = useState<string | null>(null);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [capital, setCapital] = useState("1000.00");
  const [split, setSplit] = useState("0.25");
  const [seed, setSeed] = useState("42");
  const [benchmark, setBenchmark] = useState("");
  const [loading, setLoading] = useState(true);
  const [versionLoading, setVersionLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [moreBusy, setMoreBusy] = useState(false);
  const [error, setError] = useState("");
  const [historyError, setHistoryError] = useState("");
  const [revision, setRevision] = useState(0);
  const selected = snapshots.find((row) => row.id === snapshotId) ?? null;
  const version = versions.find((row) => row.id === versionId);
  const allowedBenchmarks =
    selected?.coverage.asset_ids.filter((id) => id.endsWith(":SPY")) ?? [];
  const supported =
    selected?.mode === "synthetic_fixture" && selected.quality !== "blocked";
  const valid = Boolean(
    version?.strategy_id === rootId &&
    roots.some((row) => row.id === rootId) &&
    supported &&
    coveredWindow(selected, start, end) &&
    positiveMoney(capital) &&
    validSeed(seed) &&
    Number(split) > 0 &&
    Number(split) < 1 &&
    allowedBenchmarks.includes(benchmark),
  );

  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      const api = createApiClient(window.location.origin);
      try {
        const [strategies, data, runs] = await Promise.all([
          api.GET("/api/v1/strategies", {
            params: { query: { limit: 25 } },
            signal: controller.signal,
          }),
          api.GET("/api/v1/data/snapshots", {
            params: { query: { mode: "synthetic_fixture", limit: 25 } },
            signal: controller.signal,
          }),
          api.GET("/api/v1/experiments", {
            params: { query: { limit: 25 } },
            signal: controller.signal,
          }),
        ]);
        if (controller.signal.aborted) return;
        if (!strategies.data || !data.data) throw new Error("choices");
        const query = new URL(window.location.href).searchParams;
        setRoots(strategies.data.items);
        setRootCursor(strategies.data.next_cursor);
        setSnapshots(data.data.items);
        setSnapshotCursor(data.data.next_cursor);
        setRootId(query.get("strategy") || strategies.data.items[0]?.id || "");
        const snapshot = data.data.items[0];
        if (snapshot) {
          setSnapshotId(snapshot.id);
          setStart(snapshot.coverage.first_session ?? "");
          setEnd(snapshot.coverage.last_session ?? "");
          setBenchmark(
            snapshot.coverage.asset_ids.find((id) => id.endsWith(":SPY")) ?? "",
          );
        }
        if (runs.data) {
          setHistory(runs.data.items);
          setHistoryError("");
          setHistoryCursor(runs.data.next_cursor);
        } else
          setHistoryError(
            "Experiment history could not be loaded. Reload to try again.",
          );
      } catch {
        if (!controller.signal.aborted) {
          setError(
            "Published versions and snapshots could not be loaded. Check local services and retry.",
          );
          setHistoryError(
            "Experiment history could not be verified. Reload to retry.",
          );
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    })();
    return () => controller.abort();
  }, [revision]);

  useEffect(() => {
    if (!rootId) return;
    const controller = new AbortController();
    void (async () => {
      try {
        const response = await createApiClient(window.location.origin).GET(
          "/api/v1/strategies/{strategy_id}/versions",
          {
            params: { path: { strategy_id: rootId }, query: { limit: 25 } },
            signal: controller.signal,
          },
        );
        if (controller.signal.aborted) return;
        if (!response.data) throw new Error("versions");
        setVersions(response.data.items);
        setVersionCursor(response.data.next_cursor);
        const query = new URL(window.location.href).searchParams;
        const requested =
          !query.get("strategy") || query.get("strategy") === rootId
            ? query.get("version")
            : null;
        setVersionId(
          requested
            ? response.data.items.find((row) => row.id === requested)?.id || ""
            : response.data.items[0]?.id || "",
        );
      } catch {
        if (!controller.signal.aborted)
          setError(
            "Version history is unavailable. Reload choices before running.",
          );
      } finally {
        if (!controller.signal.aborted) setVersionLoading(false);
      }
    })();
    return () => controller.abort();
  }, [rootId, revision]);

  async function more(
    kind: "strategies" | "snapshots" | "versions" | "history",
  ) {
    const api = createApiClient(window.location.origin);
    setMoreBusy(true);
    try {
      if (kind === "strategies" && rootCursor) {
        const r = await api.GET("/api/v1/strategies", {
          params: { query: { limit: 25, cursor: rootCursor } },
        });
        if (!r.data) throw new Error();
        setRoots((old) => [...old, ...r.data!.items]);
        setRootCursor(r.data.next_cursor);
      } else if (kind === "snapshots" && snapshotCursor) {
        const r = await api.GET("/api/v1/data/snapshots", {
          params: {
            query: {
              mode: "synthetic_fixture",
              limit: 25,
              cursor: snapshotCursor,
            },
          },
        });
        if (!r.data) throw new Error();
        setSnapshots((old) => [...old, ...r.data!.items]);
        setSnapshotCursor(r.data.next_cursor);
      } else if (kind === "versions" && versionCursor) {
        const r = await api.GET("/api/v1/strategies/{strategy_id}/versions", {
          params: {
            path: { strategy_id: rootId },
            query: { limit: 25, cursor: versionCursor },
          },
        });
        if (!r.data) throw new Error();
        setVersions((old) => [...old, ...r.data!.items]);
        setVersionCursor(r.data.next_cursor);
      } else if (kind === "history" && historyCursor) {
        const r = await api.GET("/api/v1/experiments", {
          params: { query: { limit: 25, cursor: historyCursor } },
        });
        if (!r.data) throw new Error();
        setHistory((old) => [...old, ...r.data!.items]);
        setHistoryCursor(r.data.next_cursor);
      }
    } catch {
      setError(
        "The next page could not be loaded. Existing choices and results are kept.",
      );
    } finally {
      setMoreBusy(false);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!valid || busy) return;
    setBusy(true);
    setError("");
    const inputs: S["ExperimentRequest"] = {
      strategy_version_id: versionId,
      snapshot_id: snapshotId,
      start_session: start,
      end_session_exclusive: end,
      initial_capital_usd: capital,
      benchmark_asset_id: benchmark,
      execution_policy_id: "us_eod_next_open_v1",
      random_seed: 0,
      evaluation_split: {
        kind: "chronological",
        holdout_fraction: Number(split),
      },
    };
    let navigated = false;
    try {
      const response = await createApiClient(window.location.origin).POST(
        "/api/v1/experiments",
        {
          body: inputs,
          bodySerializer: () => serializeExperiment(inputs, seed),
        },
      );
      if (!response.data) {
        setError(experimentError(response.error?.error.code));
        return;
      }
      router.push(`/lab/experiments/${response.data.experiment_id}`);
      navigated = true;
    } catch {
      setError(experimentError());
    } finally {
      if (!navigated) setBusy(false);
    }
  }

  function chooseSnapshot(id: string) {
    setSnapshotId(id);
    const row = snapshots.find((item) => item.id === id);
    setStart(row?.coverage.first_session ?? "");
    setEnd(row?.coverage.last_session ?? "");
    setBenchmark(
      row?.coverage.asset_ids.find((asset) => asset.endsWith(":SPY")) ?? "",
    );
  }

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">STRATEGY LAB</p>
          <h1>Historical experiments</h1>
          <p>
            Pin published rules and a snapshot. Inspect what the shared engine
            simulated, including costs and limitations.
          </p>
        </div>
      </div>
      {error && (
        <p className="notice notice-error" role="alert">
          {error}
        </p>
      )}
      <Button
        variant="outline"
        disabled={loading || busy || moreBusy}
        onClick={() => {
          setLoading(true);
          setError("");
          setRevision((old) => old + 1);
        }}
      >
        Reload choices and history
      </Button>
      <Card title="Create an experiment">
        {loading ? (
          <p role="status">Loading published versions and snapshots…</p>
        ) : !roots.length || !snapshots.length ? (
          error ? (
            <p>
              Experiment inputs are unavailable. Reload choices after checking
              local services.
            </p>
          ) : (
            <EmptyState title="No usable experiment inputs">
              Publish a strategy and load a synthetic snapshot in{" "}
              <Link href="/settings/data">Data settings</Link>.
            </EmptyState>
          )
        ) : (
          <form onSubmit={submit} className="experiment-form">
            <div className="form-grid">
              <label>
                Strategy
                <select
                  value={rootId}
                  disabled={busy || moreBusy}
                  onChange={(event) => {
                    setError("");
                    setVersionLoading(true);
                    setVersions([]);
                    setVersionId("");
                    setRootId(event.target.value);
                  }}
                >
                  {rootId && !roots.some((row) => row.id === rootId) && (
                    <option value={rootId}>
                      Requested strategy not loaded · load more or choose
                      another
                    </option>
                  )}
                  {roots.map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Published version
                <select
                  value={versionId}
                  disabled={
                    busy ||
                    versionLoading ||
                    moreBusy ||
                    versions.some((row) => row.strategy_id !== rootId)
                  }
                  onChange={(event) => {
                    setError("");
                    setVersionId(event.target.value);
                  }}
                >
                  <option value="" disabled>
                    Select a published version
                  </option>
                  {versions.map((row) => (
                    <option key={row.id} value={row.id}>
                      Version {row.version} · {row.id}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Snapshot
                <select
                  value={snapshotId}
                  disabled={busy || moreBusy}
                  onChange={(event) => chooseSnapshot(event.target.value)}
                >
                  {snapshots.map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.provider} · {row.coverage.first_session} to{" "}
                      {row.coverage.last_session} · {row.id}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Benchmark
                <select
                  value={benchmark}
                  disabled={busy}
                  onChange={(event) => setBenchmark(event.target.value)}
                >
                  {allowedBenchmarks.map((id) => (
                    <option key={id}>{id}</option>
                  ))}
                </select>
              </label>
              <label>
                Start session
                <input
                  type="date"
                  value={start}
                  required
                  disabled={busy}
                  onChange={(event) => setStart(event.target.value)}
                />
              </label>
              <label>
                End session (exclusive)
                <input
                  type="date"
                  value={end}
                  required
                  disabled={busy}
                  onChange={(event) => setEnd(event.target.value)}
                />
              </label>
              <label>
                Initial synthetic capital (USD)
                <input
                  inputMode="decimal"
                  value={capital}
                  required
                  disabled={busy}
                  onChange={(event) => setCapital(event.target.value)}
                />
              </label>
              <label>
                Holdout fraction
                <input
                  type="number"
                  min="0.01"
                  max="0.99"
                  step="0.01"
                  value={split}
                  required
                  disabled={busy}
                  onChange={(event) => setSplit(event.target.value)}
                />
              </label>
              <label>
                Random seed
                <input
                  inputMode="numeric"
                  value={seed}
                  required
                  disabled={busy}
                  onChange={(event) => setSeed(event.target.value)}
                />
              </label>
            </div>
            {selected && (
              <>
                <DataProvenanceBadge
                  mode={selected.mode}
                  provider={selected.provider}
                  asOf={selected.latest_completed_session}
                  freshness="fixture"
                />
                <p>
                  Snapshot quality: {selected.quality.replaceAll("_", " ")}.{" "}
                  {selected.quality === "blocked" &&
                    "This snapshot is blocked for experiments. Load another usable snapshot."}
                </p>
                <WarningsPanel warnings={selected.warnings} />
                <p>
                  Covered dates:{" "}
                  {selected.coverage.first_session ?? "unavailable"} through{" "}
                  {selected.coverage.last_session ?? "unavailable"}. End is
                  exclusive and reserves the last covered session for
                  decision-clock lookahead. Calendar gaps and warmup are checked
                  by the engine; coverage alone does not establish sufficient
                  history.
                </p>
              </>
            )}
            <p>
              Execution: next eligible open · 10 bps adverse slippage per side ·
              $0 commission · USD. Costs are pinned by us_eod_next_open_v1.
            </p>
            <p>
              Historical experiments currently use authored synthetic snapshots.
              Current Tiingo/Yahoo feeds support diagnostics; historical
              accounting evidence is unavailable. Short histories and repeated
              holdout selection do not establish future performance.
            </p>
            {!valid && (
              <p className="notice" role="status">
                Choose a published version and covered positive window, positive
                USD capital, SPY benchmark, holdout fraction between 0 and 1,
                and an unsigned 64-bit integer seed.
              </p>
            )}
            <Button
              type="submit"
              disabled={!valid || busy || versionLoading || moreBusy}
            >
              {busy ? "Submitting pinned inputs…" : "Run historical experiment"}
            </Button>
            {version && (
              <details>
                <summary>Inspect selected immutable rules</summary>
                <p>
                  Configuration SHA-256: <code>{version.config_sha256}</code>
                </p>
                <pre className="evidence-json" tabIndex={0}>
                  {JSON.stringify(version.config, null, 2)}
                </pre>
              </details>
            )}
          </form>
        )}
        <div className="button-row">
          {rootCursor && (
            <Button
              variant="outline"
              disabled={moreBusy || busy || loading || versionLoading}
              onClick={() => void more("strategies")}
            >
              More strategies
            </Button>
          )}
          {versionCursor && (
            <Button
              variant="outline"
              disabled={moreBusy || busy || loading || versionLoading}
              onClick={() => void more("versions")}
            >
              More versions
            </Button>
          )}
          {snapshotCursor && (
            <Button
              variant="outline"
              disabled={moreBusy || busy || loading || versionLoading}
              onClick={() => void more("snapshots")}
            >
              More snapshots
            </Button>
          )}
        </div>
      </Card>
      <Card title="Saved experiments">
        {loading ? (
          <p role="status">Loading experiment history…</p>
        ) : historyError ? (
          <p role="alert">{historyError}</p>
        ) : !history.length ? (
          <EmptyState title="No experiments yet">
            Run a pinned experiment to keep its inputs and result here.
          </EmptyState>
        ) : (
          <ul className="record-list">
            {history.map((row) => (
              <li key={row.id}>
                <Link href={`/lab/experiments/${row.id}`}>
                  {row.inputs.start_session} to{" "}
                  {row.inputs.end_session_exclusive} ·{" "}
                  {row.status.replaceAll("_", " ")}
                </Link>
                <p>
                  <code>{row.id}</code> ·{" "}
                  {row.data_status === "synthetic_fixture"
                    ? "SYNTHETIC_DATA_ONLY"
                    : "Market research data"}
                </p>
              </li>
            ))}
          </ul>
        )}
        {historyCursor && (
          <Button
            variant="outline"
            disabled={moreBusy || busy || loading || versionLoading}
            onClick={() => void more("history")}
          >
            More experiments
          </Button>
        )}
      </Card>
    </>
  );
}
