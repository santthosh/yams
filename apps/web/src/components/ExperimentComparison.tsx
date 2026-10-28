"use client";
import Link from "next/link";
import dynamic from "next/dynamic";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { createApiClient } from "../api/generated/client";
import type { components } from "../api/generated/schema";
import { Card, DataProvenanceBadge, EmptyState, Money } from "./evidence";
import { Button } from "./ui/button";
import { formatDecimal } from "../lib/format";
import {
  comparisonDifferences,
  configDifferences,
  fairRerunBody,
  sortMetrics,
  sortRuns,
  type Period,
  type Point,
  type Run,
  type SortMetric,
} from "./experiments/comparison";
import { RuleChallenge } from "./experiments/RuleChallenge";
import { storedSeed } from "./experiments/inputs";
const Chart = dynamic(() => import("./experiments/ComparisonChart"), {
  ssr: false,
  loading: () => (
    <p role="status">
      Loading comparison chart. Exact tables remain available.
    </p>
  ),
});
type S = components["schemas"];
type Samples = {
  points: Point[];
  cursor: string | null;
  trades: S["ExperimentTradeV1"][];
  tradeCursor: string | null;
};
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function Statistic({
  metric,
  percent = false,
}: {
  metric: S["MetricValue"];
  percent?: boolean;
}) {
  return metric.value === null ? (
    <span>Unavailable · {metric.unavailable_reason}</span>
  ) : (
    <span>
      {new Intl.NumberFormat(
        "en-US",
        percent
          ? { style: "percent", maximumFractionDigits: 3 }
          : { maximumFractionDigits: 4 },
      ).format(metric.value)}
    </span>
  );
}
export function ExperimentComparison({
  initialIds = [],
}: {
  initialIds?: string[];
}) {
  const [history, setHistory] = useState<S["ExperimentSummaryV1"][]>([]);
  const [historyCursor, setHistoryCursor] = useState<string | null>(null);
  const [historyError, setHistoryError] = useState("");
  const [chosen, setChosen] = useState<string[]>(initialIds);
  const [ids, setIds] = useState<string[]>(initialIds);
  const [runs, setRuns] = useState<Run[]>([]);
  const [samples, setSamples] = useState<Record<string, Samples>>({});
  const [error, setError] = useState("");
  const [sampleError, setSampleError] = useState("");
  const [loading, setLoading] = useState(initialIds.length > 0);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [moreBusy, setMoreBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const [period, setPeriod] = useState<Period>("total");
  const [metric, setMetric] = useState<SortMetric>(
    "cumulative_return_fraction",
  );
  const [referenceId, setReferenceId] = useState("");
  const [reruns, setReruns] = useState<S["ExperimentAccepted"][]>([]);
  const [rerunError, setRerunError] = useState("");
  const [rerunBusy, setRerunBusy] = useState(false);
  const [challengeBusy, setChallengeBusy] = useState(false);
  const writesBusy = rerunBusy || challengeBusy;
  const [rerunUncertain, setRerunUncertain] = useState(false);
  const writeLock = useRef(false);
  const generation = useRef(0);
  const loadedIds = ids.join(",");
  const selectionError =
    ids.length > 0 &&
    (ids.length < 2 ||
      ids.length > 4 ||
      new Set(ids).size !== ids.length ||
      ids.some((id) => !uuid.test(id)));

  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        const response = await createApiClient(window.location.origin).GET(
          "/api/v1/experiments",
          { params: { query: { limit: 25 } }, signal: controller.signal },
        );
        if (controller.signal.aborted) return;
        if (!response.data) throw new Error();
        setHistory(response.data.items);
        setHistoryCursor(response.data.next_cursor);
        setHistoryError("");
      } catch {
        if (!controller.signal.aborted)
          setHistoryError(
            "Experiment history is unavailable. Reload to retry.",
          );
      } finally {
        if (!controller.signal.aborted) setHistoryLoading(false);
      }
    })();
    return () => controller.abort();
  }, [revision]);
  useEffect(() => {
    const controller = new AbortController();
    generation.current++;
    const selected = loadedIds ? loadedIds.split(",") : [];
    if (
      selected.length < 2 ||
      selected.length > 4 ||
      new Set(selected).size !== selected.length ||
      selected.some((id) => !uuid.test(id))
    )
      return () => controller.abort();
    void (async () => {
      try {
        const api = createApiClient(window.location.origin);
        const responses = await Promise.all(
          selected.map((id) =>
            api.GET("/api/v1/experiments/{experiment_id}", {
              params: { path: { experiment_id: id } },
              signal: controller.signal,
            }),
          ),
        );
        if (controller.signal.aborted) return;
        if (responses.some((response) => !response.data)) throw new Error();
        const loaded = responses.map((response) => response.data!);
        setRuns(loaded);
        setReferenceId(loaded[0].id);
        if (loaded.every((run) => run.status === "completed" && run.report)) {
          try {
            const pages = await Promise.all(
              loaded.map(async (run) => {
                const params = {
                  path: { experiment_id: run.id },
                  query: { limit: 25 },
                };
                const [series, trades] = await Promise.all([
                  api.GET("/api/v1/experiments/{experiment_id}/series", {
                    params,
                    signal: controller.signal,
                  }),
                  api.GET("/api/v1/experiments/{experiment_id}/trades", {
                    params,
                    signal: controller.signal,
                  }),
                ]);
                if (!series.data || !trades.data) throw new Error();
                return [
                  run.id,
                  {
                    points: series.data.items,
                    cursor: series.data.next_cursor,
                    trades: trades.data.items,
                    tradeCursor: trades.data.next_cursor,
                  },
                ] as const;
              }),
            );
            if (!controller.signal.aborted)
              setSamples(Object.fromEntries(pages));
          } catch {
            if (!controller.signal.aborted)
              setSampleError(
                "Sealed samples are unavailable. Refresh selected reports to retry; empty data is not assumed.",
              );
          }
        }
      } catch {
        if (!controller.signal.aborted)
          setError(
            "One or more selected experiments are unavailable. Check the identities and refresh selected reports.",
          );
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    })();
    return () => controller.abort();
  }, [loadedIds, revision]);
  async function moreHistory() {
    if (!historyCursor || moreBusy) return;
    setMoreBusy(true);
    try {
      const response = await createApiClient(window.location.origin).GET(
        "/api/v1/experiments",
        { params: { query: { limit: 25, cursor: historyCursor } } },
      );
      if (!response.data) throw new Error();
      setHistory((old) => [
        ...new Map(
          [...old, ...response.data!.items].map((row) => [row.id, row]),
        ).values(),
      ]);
      setHistoryCursor(response.data.next_cursor);
      setHistoryError("");
    } catch {
      setHistoryError(
        "More history is unavailable. Existing choices are retained.",
      );
    } finally {
      setMoreBusy(false);
    }
  }
  function resetReports(selected: string[] = ids) {
    setRuns([]);
    setSamples({});
    setError("");
    setSampleError("");
    setReruns([]);
    setRerunError("");
    setRerunUncertain(false);
    setLoading(selected.length >= 2 && selected.length <= 4);
  }
  function select(event: FormEvent) {
    event.preventDefault();
    if (writesBusy || chosen.length < 2 || chosen.length > 4) return;
    resetReports(chosen);
    setIds([...chosen]);
    window.history.replaceState(
      null,
      "",
      `/lab/compare?ids=${chosen.join(",")}`,
    );
    setRevision((value) => value + 1);
  }
  async function moreSamples(id: string, kind: "series" | "trades") {
    const prior = samples[id],
      cursor = kind === "series" ? prior?.cursor : prior?.tradeCursor;
    if (!cursor || moreBusy) return;
    const active = generation.current;
    setMoreBusy(true);
    setSampleError("");
    try {
      const api = createApiClient(window.location.origin);
      const params = {
        path: { experiment_id: id },
        query: { limit: 25, cursor },
      };
      if (kind === "series") {
        const response = await api.GET(
          "/api/v1/experiments/{experiment_id}/series",
          { params },
        );
        if (!response.data) throw new Error();
        if (active === generation.current)
          setSamples((old) => ({
            ...old,
            [id]: {
              ...old[id],
              points: [...old[id].points, ...response.data!.items],
              cursor: response.data!.next_cursor,
            },
          }));
      } else {
        const response = await api.GET(
          "/api/v1/experiments/{experiment_id}/trades",
          { params },
        );
        if (!response.data) throw new Error();
        if (active === generation.current)
          setSamples((old) => ({
            ...old,
            [id]: {
              ...old[id],
              trades: [...old[id].trades, ...response.data!.items],
              tradeCursor: response.data!.next_cursor,
            },
          }));
      }
    } catch {
      if (active === generation.current)
        setSampleError(
          "Additional sealed samples are unavailable. Existing rows are retained; retry their load button.",
        );
    } finally {
      setMoreBusy(false);
    }
  }
  const complete =
    runs.length >= 2 &&
    runs.every((run) => run.status === "completed" && run.report);
  const differences = complete ? comparisonDifferences(runs) : [];
  const aligned = complete && differences.length === 0;
  const reference = runs.find((run) => run.id === referenceId) ?? runs[0];
  const sorted = aligned ? sortRuns(runs, period, metric) : [];
  const points = Object.fromEntries(
    runs.map((run) => [run.id, samples[run.id]?.points ?? []]),
  );
  const hasSamples = runs.length > 0 && runs.every((run) => samples[run.id]);
  async function rerunAll() {
    if (!complete || !reference || writeLock.current || rerunUncertain) return;
    writeLock.current = true;
    setRerunBusy(true);
    setRerunError("");
    try {
      const api = createApiClient(window.location.origin);
      for (const target of runs.slice(reruns.length)) {
        const response = await api.POST("/api/v1/experiments", {
          body: {
            ...reference.inputs,
            strategy_version_id: target.inputs.strategy_version_id,
          },
          bodySerializer: () =>
            fairRerunBody(reference, target.inputs.strategy_version_id),
        });
        if (!response.data) {
          if (![404, 422].includes(response.response.status))
            setRerunUncertain(true);
          setRerunError(
            "A rerun could not be confirmed. Accepted jobs below are retained. Inspect history before resubmitting an uncertain request.",
          );
          return;
        }
        setReruns((old) => [...old, response.data!]);
      }
    } catch {
      setRerunUncertain(true);
      setRerunError(
        "A rerun could not be confirmed. Inspect history before resubmitting; accepted jobs below are retained.",
      );
    } finally {
      writeLock.current = false;
      setRerunBusy(false);
    }
  }
  return (
    <div className="page-stack comparison-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Strategy Lab · Paper only</p>
          <h1>Compare historical experiments</h1>
          <p>
            Inspect two to four immutable reports under the same assumptions.
            Historical results are research evidence, not investment advice or
            forecasts.
          </p>
        </div>
        <Link href="/lab/experiments">Create or inspect experiments</Link>
      </div>
      <div className="notice notice-warning" role="note">
        Repeated parameter tuning and holdout selection weaken independent
        validation. Short synthetic demonstrations do not establish prospective
        performance.
      </div>
      <Card title="Select completed experiments">
        {historyLoading && <p role="status">Loading experiment history…</p>}
        {historyError && <p role="alert">{historyError}</p>}
        {!historyLoading && !historyError && !history.length && (
          <EmptyState title="No experiments yet">
            Run an experiment first; only completed reports can be compared.
          </EmptyState>
        )}
        <form onSubmit={select}>
          <fieldset
            disabled={writesBusy || moreBusy}
            className="strategy-fieldset"
          >
            <legend>Choose two to four completed reports</legend>
            {history.map((run) => (
              <label className="strategy-check" key={run.id}>
                <input
                  type="checkbox"
                  checked={chosen.includes(run.id)}
                  disabled={
                    run.status !== "completed" ||
                    (!chosen.includes(run.id) && chosen.length >= 4)
                  }
                  onChange={(event) =>
                    setChosen((old) =>
                      event.target.checked
                        ? [...old, run.id]
                        : old.filter((id) => id !== run.id),
                    )
                  }
                />
                {run.id} · {run.status} · {run.inputs.start_session}–
                {run.inputs.end_session_exclusive} · {run.data_status}
              </label>
            ))}
            <Button
              type="submit"
              disabled={chosen.length < 2 || chosen.length > 4}
            >
              Compare selected experiments
            </Button>
          </fieldset>
        </form>
        {historyCursor && (
          <Button
            variant="outline"
            disabled={moreBusy || writesBusy}
            onClick={() => void moreHistory()}
          >
            Load more experiment history
          </Button>
        )}
        <Button
          variant="outline"
          disabled={loading || writesBusy || moreBusy}
          onClick={() => {
            resetReports();
            setRevision((value) => value + 1);
          }}
        >
          Refresh selected reports
        </Button>
      </Card>
      {loading && !selectionError && (
        <p role="status">Loading immutable reports and sealed samples…</p>
      )}
      {selectionError && (
        <p role="alert">
          Select two to four distinct valid experiment identities.
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      {runs.length > 0 && !complete && (
        <Card title="Reports are not ready for comparison">
          <p>
            Only completed experiments can be compared. Refresh when queued or
            running reports finish; failed or cancelled reports have no
            completed financial output.
          </p>
          {runs.map((run) => (
            <p key={run.id}>
              <Link href={`/lab/experiments/${run.id}`}>{run.id}</Link> ·{" "}
              {run.status}
            </p>
          ))}
        </Card>
      )}
      {complete && (
        <>
          <Card title="Pinned settings and immutable evidence">
            <p>
              Reference settings come from the selected immutable report. A
              shared request cannot change a strategy’s universe or older engine
              build: inspect those differences and create compatible versions
              when needed. Newly completed fingerprints must match before fair
              comparison.
            </p>
            <dl className="comparison-settings">
              <div>
                <dt>Dates (end exclusive)</dt>
                <dd>
                  {reference.inputs.start_session} →{" "}
                  {reference.inputs.end_session_exclusive}
                </dd>
              </div>
              <div>
                <dt>Initial synthetic capital</dt>
                <dd>
                  <Money value={reference.inputs.initial_capital_usd} />
                </dd>
              </div>
              <div>
                <dt>Benchmark</dt>
                <dd>{reference.inputs.benchmark_asset_id}</dd>
              </div>
              <div>
                <dt>Universe assumptions</dt>
                <dd>
                  <code>
                    {reference.report!.comparison.universe_canonical_json}
                  </code>
                </dd>
              </div>
              <div>
                <dt>Execution costs</dt>
                <dd>
                  {formatDecimal(
                    reference.report!.comparison.execution_policy
                      .slippage_fraction,
                    "percent",
                  )}{" "}
                  adverse slippage per side;{" "}
                  <Money
                    value={
                      reference.report!.comparison.execution_policy
                        .commission_usd
                    }
                  />{" "}
                  commission · {reference.inputs.execution_policy_id}
                </dd>
              </div>
              <div>
                <dt>Chronological holdout fraction</dt>
                <dd>
                  {reference.inputs.evaluation_split.holdout_fraction} · starts{" "}
                  {reference.report!.comparison.holdout_start_session ??
                    "unavailable"}
                </dd>
              </div>
              <div>
                <dt>Seed and source</dt>
                <dd>
                  {storedSeed(reference)} · {reference.data_status} ·{" "}
                  {reference.provider}
                </dd>
              </div>
            </dl>
            <label>
              Reference experiment
              <select
                value={reference.id}
                disabled={writesBusy || reruns.length > 0 || rerunUncertain}
                onChange={(event) => setReferenceId(event.target.value)}
              >
                {runs.map((run) => (
                  <option key={run.id} value={run.id}>
                    {run.id}
                  </option>
                ))}
              </select>
            </label>
            {runs.map((run) => (
              <details key={run.id}>
                <summary>
                  {run.strategy_config.display_name} · {run.id}
                </summary>
                <DataProvenanceBadge
                  mode={run.data_status}
                  provider={run.provider}
                  asOf={run.report!.comparison.sessions.at(-1) ?? null}
                  freshness={
                    run.data_status === "synthetic_fixture"
                      ? "fixture"
                      : "unavailable"
                  }
                />
                <p>
                  {run.data_status === "synthetic_fixture"
                    ? "SYNTHETIC_DATA_ONLY"
                    : "Market research data"}
                </p>
                <p>
                  Original{" "}
                  <Link href={`/lab/experiments/${run.id}`}>
                    report and full trade evidence
                  </Link>{" "}
                  · strategy version{" "}
                  <code>{run.inputs.strategy_version_id}</code> · config{" "}
                  <code>{run.config_sha256}</code>
                </p>
                <pre>{JSON.stringify(run.report!.comparison, null, 2)}</pre>
                <p>
                  Comparison fingerprint{" "}
                  <code>{run.report!.comparison_sha256}</code>
                </p>
              </details>
            ))}
            <Button
              disabled={
                writesBusy || rerunUncertain || reruns.length === runs.length
              }
              onClick={() => void rerunAll()}
            >
              {reruns.length
                ? "Continue remaining reruns"
                : "Rerun all with reference settings"}
            </Button>
            <p>
              Creates a fresh run for each selected strategy version using the
              reference snapshot, dates, capital, benchmark, split, seed and
              execution policy. Originals remain unchanged. No parameter search
              is performed.
            </p>
            {rerunError && (
              <p role="alert">
                {rerunError}{" "}
                <Link href="/lab/experiments">Inspect history</Link>
              </p>
            )}
            {reruns.length > 0 && (
              <div role="status">
                <p>Accepted reruns:</p>
                <ul>
                  {reruns.map((run, index) => (
                    <li key={run.experiment_id}>
                      Source {runs[index].id} →{" "}
                      <Link href={`/lab/experiments/${run.experiment_id}`}>
                        {run.experiment_id}
                      </Link>
                    </li>
                  ))}
                </ul>
                {reruns.length === runs.length && (
                  <Link
                    href={`/lab/compare?ids=${reruns.map((run) => run.experiment_id).join(",")}`}
                  >
                    Open rerun comparison
                  </Link>
                )}
              </div>
            )}
          </Card>
          {!aligned ? (
            <Card title="Incompatible experiment settings">
              <p>
                Compare fairly by rerunning under shared settings. Curves and
                metric ranking are withheld while pinned comparison terms
                differ.
              </p>
              <div
                role="region"
                aria-label="Incompatible settings table"
                tabIndex={0}
                className="table-scroll"
              >
                <table>
                  <caption>
                    Exact incompatible settings, in selection order
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">Setting</th>
                      {runs.map((run) => (
                        <th scope="col" key={run.id}>
                          {run.id.slice(0, 8)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {differences.map((row) => (
                      <tr key={row.field}>
                        <th scope="row">{row.field}</th>
                        {row.values.map((value, index) => (
                          <td key={index}>
                            <code>{value}</code>
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          ) : (
            <Card title="Aligned experiment comparison">
              <p>
                Matching backend comparison fingerprints verify dates, session
                sequence, capital, snapshot/universe, costs, benchmark, split,
                source and engine policies. Strategy rules may differ.
              </p>
              <div className="inspection-form">
                <label>
                  Result period
                  <select
                    value={period}
                    onChange={(event) =>
                      setPeriod(event.target.value as Period)
                    }
                  >
                    <option value="total">Full experiment</option>
                    <option value="development">Development</option>
                    <option value="holdout">Holdout</option>
                  </select>
                </label>
                <label>
                  Sort by metric
                  <select
                    value={metric}
                    onChange={(event) =>
                      setMetric(event.target.value as SortMetric)
                    }
                  >
                    {Object.entries(sortMetrics).map(([key, value]) => (
                      <option value={key} key={key}>
                        {value.label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <p>
                Sorted by {sortMetrics[metric].label} (
                {sortMetrics[metric].ascending ? "ascending" : "descending"});
                unavailable values last. This ranks the selected historical
                metric only.
              </p>
              <div
                role="region"
                aria-label="Historical metric comparison"
                tabIndex={0}
                className="table-scroll"
              >
                <table>
                  <caption>
                    {period} net portfolio metrics · fees/slippage already
                    included in NAV
                  </caption>
                  <thead>
                    <tr>
                      {[
                        "Experiment",
                        "Cumulative return",
                        "Maximum drawdown",
                        "Sharpe",
                        "Turnover",
                        "Fees (USD)",
                        "Slippage (USD)",
                        "Cash at loaded close",
                      ].map((label) => (
                        <th scope="col" key={label}>
                          {label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {sorted.map((run) => {
                      const stats = run.report!.portfolio[period].metrics;
                      const last = samples[run.id]?.points.at(-1);
                      return (
                        <tr key={run.id}>
                          <th scope="row">
                            <Link href={`/lab/experiments/${run.id}`}>
                              {run.id.slice(0, 8)}
                            </Link>
                          </th>
                          <td>
                            <Statistic
                              metric={stats.cumulative_return_fraction}
                              percent
                            />
                          </td>
                          <td>
                            <Statistic
                              metric={stats.max_drawdown_fraction}
                              percent
                            />
                          </td>
                          <td>
                            <Statistic metric={stats.sharpe_ratio} />
                          </td>
                          <td>
                            <Statistic
                              metric={stats.turnover_fraction}
                              percent
                            />
                          </td>
                          <td>
                            <Money value={stats.fees_usd} />
                          </td>
                          <td>
                            <Money value={stats.slippage_usd} />
                          </td>
                          <td>
                            {last ? (
                              <>
                                {formatDecimal(
                                  last.cash_weight.value,
                                  "percent",
                                )}{" "}
                                · {last.session_date}
                              </>
                            ) : (
                              "Unavailable"
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <p>
                Cash at the loaded close describes its labeled original session,
                not a period average. SPY is an adjusted-close, fully invested
                friction-free proxy with different initial-close/dividend
                timing; cash earns zero. Benchmark gaps remain gaps and
                unavailable statistics retain their reasons. Period selection
                changes stored summary metrics; the original full-session curves
                below do not change.
              </p>
              {runs.map((run) => (
                <details key={run.id}>
                  <summary>
                    Benchmark and cash metrics · {run.id.slice(0, 8)}
                  </summary>
                  <p>
                    Daily NAV observations{" "}
                    {run.report!.portfolio[period].daily_nav_observations};
                    return observations{" "}
                    {run.report!.portfolio[period].return_observations}; holdout
                    starts{" "}
                    {run.report!.comparison.holdout_start_session ??
                      "unavailable"}
                    .
                  </p>
                  <p>
                    SPY cumulative return:{" "}
                    {run.report!.benchmark.periods ? (
                      <Statistic
                        metric={
                          run.report!.benchmark.periods[period].metrics
                            .cumulative_return_fraction
                        }
                        percent
                      />
                    ) : (
                      `Unavailable · ${run.report!.benchmark.unavailable_reason}`
                    )}
                    . Zero-yield cash cumulative return:{" "}
                    <Statistic
                      metric={
                        run.report!.cash[period].metrics
                          .cumulative_return_fraction
                      }
                      percent
                    />
                    .
                  </p>
                  <pre>
                    {JSON.stringify(
                      {
                        warnings: [...run.warnings, ...run.report!.warnings],
                        benchmark: run.report!.benchmark,
                        cash: run.report!.cash[period],
                      },
                      null,
                      2,
                    )}
                  </pre>
                </details>
              ))}
              {runs.some((run) => !run.report!.benchmark.available) && (
                <p role="note">
                  Benchmark comparison is unavailable for at least one run.
                  Missing points remain gaps; inspect the stored benchmark
                  reason below.
                </p>
              )}
              {sampleError && <p role="alert">{sampleError}</p>}
              {hasSamples && (
                <>
                  <p>
                    {runs.some((run) => samples[run.id].cursor)
                      ? "Partial session pages: curves and close cash show only loaded rows; load all pages to inspect the complete window."
                      : "All original session pages are loaded."}
                  </p>
                  {runs.some((run) => samples[run.id].points.length > 0) ? (
                    <Chart runs={runs} points={points} />
                  ) : (
                    <EmptyState title="No stored session samples">
                      This window contains no loaded session values. Summary
                      metrics are unchanged.
                    </EmptyState>
                  )}
                  <div
                    role="region"
                    aria-label="Exact comparison session values"
                    tabIndex={0}
                    className="table-scroll"
                  >
                    <table>
                      <caption>
                        Exact stored session values · full experiment window, no
                        resampling
                      </caption>
                      <thead>
                        <tr>
                          {[
                            "Experiment",
                            "Session",
                            "Phase",
                            "Portfolio NAV (USD)",
                            "SPY NAV (USD)",
                            "Cash baseline (USD)",
                            "Drawdown",
                            "Cash weight",
                            "Largest position",
                          ].map((label) => (
                            <th scope="col" key={label}>
                              {label}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {runs.flatMap((run) =>
                          samples[run.id].points.map((point) => (
                            <tr key={`${run.id}/${point.session_date}`}>
                              <th scope="row">
                                {run.id.slice(0, 8)} · {point.session_date}
                              </th>
                              <td>{point.session_date}</td>
                              <td>{point.phase}</td>
                              <td>{point.portfolio_nav_usd}</td>
                              <td>
                                {point.benchmark_nav_usd ??
                                  `Unavailable · ${point.benchmark_unavailable_reason}`}
                              </td>
                              <td>{point.cash_baseline_nav_usd}</td>
                              <td>
                                <Statistic
                                  metric={point.drawdown_fraction}
                                  percent
                                />
                              </td>
                              <td>
                                {point.cash_weight.value ??
                                  `Unavailable · ${point.cash_weight.unavailable_reason}`}
                              </td>
                              <td>
                                {point.max_position_weight.value ??
                                  `Unavailable · ${point.max_position_weight.unavailable_reason}`}
                              </td>
                            </tr>
                          )),
                        )}
                      </tbody>
                    </table>
                  </div>
                  {runs.map((run) => (
                    <div key={run.id}>
                      {samples[run.id].cursor && (
                        <Button
                          variant="outline"
                          disabled={moreBusy}
                          onClick={() => void moreSamples(run.id, "series")}
                        >
                          Load more sessions · {run.id.slice(0, 8)}
                        </Button>
                      )}
                      <details>
                        <summary>
                          Stored executions · {run.id.slice(0, 8)}
                        </summary>
                        <p>
                          Loaded {samples[run.id].trades.length} executions
                          {samples[run.id].tradeCursor
                            ? "; more pages remain"
                            : "; complete loaded window"}
                          .{" "}
                          <Link href={`/lab/experiments/${run.id}`}>
                            Inspect full trade evidence
                          </Link>
                        </p>
                        <pre>
                          {JSON.stringify(samples[run.id].trades, null, 2)}
                        </pre>
                        {samples[run.id].tradeCursor && (
                          <Button
                            disabled={moreBusy}
                            onClick={() => void moreSamples(run.id, "trades")}
                          >
                            Load more executions · {run.id.slice(0, 8)}
                          </Button>
                        )}
                      </details>
                    </div>
                  ))}
                </>
              )}
            </Card>
          )}
          <Card title="Stored rule differences">
            <p>
              The reference is{" "}
              <Link href={`/lab/experiments/${reference.id}`}>
                {reference.id}
              </Link>
              . Source and target identities in this comparison URL remain
              inspectable across restarts. Differences are read from their
              immutable stored configurations.
            </p>
            {runs
              .filter((run) => run.id !== reference.id)
              .map((run) => {
                const diff = configDifferences(
                  reference.strategy_config,
                  run.strategy_config,
                );
                return (
                  <section key={run.id}>
                    <h3>
                      {run.id.slice(0, 8)} ·{" "}
                      {diff.length === 1
                        ? "One-rule comparison"
                        : diff.length === 0
                          ? "Same rules"
                          : "Full fork with multiple rule changes"}
                    </h3>
                    {diff.length > 0 ? (
                      <ul>
                        {diff.map((row) => (
                          <li key={row.field}>
                            <code>{row.field}</code>: {row.before} → {row.after}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p>No stored configuration fields differ.</p>
                    )}
                  </section>
                );
              })}
          </Card>
          <RuleChallenge
            key={reference.id}
            source={reference}
            onBusy={setChallengeBusy}
          />
        </>
      )}
    </div>
  );
}
