"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { createApiClient } from "../../api/generated/client";
import type { components } from "../../api/generated/schema";
import {
  Card,
  DataProvenanceBadge,
  EmptyState,
  Money,
  Quantity,
  ReturnPercent,
} from "../evidence";
import { Button } from "../ui/button";
import { UUID_PATTERN } from "../../lib/validation";
import { experimentError, storedSeed } from "./inputs";
import { ExperimentWarnings } from "./ExperimentWarnings";

const Charts = dynamic(() => import("./ExperimentCharts"), {
  ssr: false,
  loading: () => (
    <p role="status">
      Loading charts. Exact values are available in the table.
    </p>
  ),
});
type S = components["schemas"];
type Run = S["ExperimentDetailV1"];
type Point = S["ExperimentCurvePointV1"];
const terminal = (status: string) =>
  ["completed", "failed", "cancelled"].includes(status);
function Statistic({
  value,
  percent = false,
}: {
  value: S["MetricValue"];
  percent?: boolean;
}) {
  return value.value == null ? (
    <span>Unavailable · {value.unavailable_reason}</span>
  ) : (
    <span className="tabular-nums">
      {new Intl.NumberFormat(
        "en-US",
        percent
          ? { style: "percent", maximumFractionDigits: 3 }
          : { maximumFractionDigits: 4 },
      ).format(value.value)}
    </span>
  );
}
function Metrics({
  periods,
  title = "Net simulated performance",
}: {
  periods: NonNullable<Run["report"]>["portfolio"];
  title?: string;
}) {
  return (
    <div
      className="table-scroll"
      tabIndex={0}
      role="region"
      aria-label={`${title} table`}
    >
      <table>
        <caption>
          {title} · fractions displayed as percentages · zero risk-free rate ·
          252 sessions/year
        </caption>
        <thead>
          <tr>
            <th scope="col">Metric</th>
            <th scope="col">All sessions</th>
            <th scope="col">Development</th>
            <th scope="col">Holdout</th>
          </tr>
        </thead>
        <tbody>
          {(
            [
              ["cumulative_return_fraction", "Cumulative return"],
              ["annualized_return_fraction", "Annualized return"],
              ["annualized_volatility_fraction", "Annualized volatility"],
              ["max_drawdown_fraction", "Maximum drawdown"],
              ["turnover_fraction", "Turnover"],
              ["sharpe_ratio", "Sharpe ratio"],
            ] as const
          ).map(([key, label]) => (
            <tr key={key}>
              <th scope="row">{label}</th>
              {(["total", "development", "holdout"] as const).map((period) => (
                <td key={period}>
                  <Statistic
                    value={periods[period].metrics[key]}
                    percent={key !== "sharpe_ratio"}
                  />
                </td>
              ))}
            </tr>
          ))}
          {(
            [
              ["fees_usd", "Fees (USD)"],
              ["slippage_usd", "Slippage (USD)"],
            ] as const
          ).map(([key, label]) => (
            <tr key={key}>
              <th scope="row">{label}</th>
              {(["total", "development", "holdout"] as const).map((period) => (
                <td key={period}>
                  <Money value={periods[period].metrics[key]} />
                </td>
              ))}
            </tr>
          ))}
          <tr>
            <th scope="row">Trades</th>
            {(["total", "development", "holdout"] as const).map((period) => (
              <td key={period}>{periods[period].metrics.trade_count}</td>
            ))}
          </tr>
          <tr>
            <th scope="row">Daily NAV observations</th>
            {(["total", "development", "holdout"] as const).map((period) => (
              <td key={period}>{periods[period].daily_nav_observations}</td>
            ))}
          </tr>
          <tr>
            <th scope="row">Adjacent returns</th>
            {(["total", "development", "holdout"] as const).map((period) => (
              <td key={period}>{periods[period].return_observations}</td>
            ))}
          </tr>
        </tbody>
      </table>
    </div>
  );
}
function Completed({ run }: { run: Run }) {
  const [points, setPoints] = useState<Point[]>([]);
  const [trades, setTrades] = useState<S["ExperimentTradeV1"][]>([]);
  const [seriesCursor, setSeriesCursor] = useState<string | null>(null);
  const [tradeCursor, setTradeCursor] = useState<string | null>(null);
  const [start, setStart] = useState(run.inputs.start_session);
  const [end, setEnd] = useState(run.inputs.end_session_exclusive);
  const [window, setWindow] = useState({
    start: run.inputs.start_session,
    end: run.inputs.end_session_exclusive,
  });
  const [selectedSession, setSelectedSession] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const active = useRef<AbortController | null>(null);
  const report = run.report;
  const validWindow =
    start >= run.inputs.start_session &&
    end <= run.inputs.end_session_exclusive &&
    start < end;
  const holding =
    points.find((point) => point.session_date === selectedSession) ??
    points.at(-1);
  useEffect(() => {
    const controller = new AbortController();
    active.current = controller;
    void (async () => {
      try {
        const api = createApiClient(windowOrigin());
        const query = {
          limit: 25,
          start_session: window.start,
          end_session_exclusive: window.end,
        };
        const [series, executions] = await Promise.all([
          api.GET("/api/v1/experiments/{experiment_id}/series", {
            params: { path: { experiment_id: run.id }, query },
            signal: controller.signal,
          }),
          api.GET("/api/v1/experiments/{experiment_id}/trades", {
            params: { path: { experiment_id: run.id }, query },
            signal: controller.signal,
          }),
        ]);
        if (controller.signal.aborted) return;
        if (!series.data || !executions.data) throw new Error("artifacts");
        setPoints(series.data.items);
        setSeriesCursor(series.data.next_cursor);
        setTrades(executions.data.items);
        setTradeCursor(executions.data.next_cursor);
      } catch {
        if (!controller.signal.aborted)
          setError(
            "Sealed samples could not be verified or loaded. Retry this window; no missing value has been replaced.",
          );
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    })();
    return () => controller.abort();
  }, [run.id, window, revision]);
  async function more(role: "series" | "trades") {
    const cursor = role === "series" ? seriesCursor : tradeCursor;
    if (!cursor || busy) return;
    const signal = active.current?.signal;
    setBusy(true);
    setError("");
    try {
      const api = createApiClient(windowOrigin());
      const options = {
        params: {
          path: { experiment_id: run.id },
          query: {
            limit: 25,
            cursor,
            start_session: window.start,
            end_session_exclusive: window.end,
          },
        },
        signal,
      };
      if (role === "series") {
        const r = await api.GET(
          "/api/v1/experiments/{experiment_id}/series",
          options,
        );
        if (signal?.aborted) return;
        if (!r.data) throw new Error();
        setPoints((old) => [...old, ...r.data!.items]);
        setSeriesCursor(r.data.next_cursor);
      } else {
        const r = await api.GET(
          "/api/v1/experiments/{experiment_id}/trades",
          options,
        );
        if (signal?.aborted) return;
        if (!r.data) throw new Error();
        setTrades((old) => [...old, ...r.data!.items]);
        setTradeCursor(r.data.next_cursor);
      }
    } catch {
      if (!signal?.aborted)
        setError(
          "The next page is unavailable. Loaded rows are kept; retry without changing the window.",
        );
    } finally {
      if (!signal?.aborted) setBusy(false);
    }
  }
  if (!report) return null;
  return (
    <>
      <Card title="Performance and holdout">
        <Metrics periods={report.portfolio} />
        <p>
          Holdout begins{" "}
          {report.comparison.holdout_start_session ?? "unavailable"}.
          Development and holdout share the same evolving portfolio; the holdout
          does not reset cash or retune rules. Repeatedly choosing a strategy
          after viewing holdout results weakens its independence.
        </p>
        <p>
          SPY proxy:{" "}
          {report.benchmark.available
            ? "Available"
            : `Unavailable · ${report.benchmark.unavailable_reason}`}
          .{" "}
          {report.benchmark.periods && (
            <>
              SPY cumulative return:{" "}
              <Statistic
                value={
                  report.benchmark.periods.total.metrics
                    .cumulative_return_fraction
                }
                percent
              />
              .{" "}
            </>
          )}
          Zero-yield cash cumulative return:{" "}
          <Statistic
            value={report.cash.total.metrics.cumulative_return_fraction}
            percent
          />
          .
        </p>
        <p>
          SPY is an adjusted-close, fully invested, friction-free reference. Its
          initial-close and dividend conventions differ from the strategy’s
          raw-price next-open execution. Backtest performance does not establish
          future returns.
        </p>
        <ExperimentWarnings warnings={report.benchmark.warnings} />
        <p>
          Annualized values extrapolate the observed period using the
          trading-day convention. A very short sample can produce extreme
          annualized figures; these are not forecasts.
        </p>
        <details>
          <summary>SPY and cash period statistics</summary>
          {report.benchmark.periods ? (
            <Metrics
              periods={report.benchmark.periods}
              title="SPY friction-free proxy statistics"
            />
          ) : (
            <p>
              SPY statistics unavailable: {report.benchmark.unavailable_reason}
            </p>
          )}
          <Metrics periods={report.cash} title="Zero-yield cash statistics" />
        </details>
      </Card>
      <Card title="Equity, drawdown and exposure">
        <form
          className="experiment-window"
          onSubmit={(event) => {
            event.preventDefault();
            if (!validWindow || busy) return;
            setLoading(true);
            setError("");
            setPoints([]);
            setTrades([]);
            setSeriesCursor(null);
            setTradeCursor(null);
            setSelectedSession("");
            setWindow({ start, end });
          }}
        >
          <label>
            Window start
            <input
              type="date"
              value={start}
              onChange={(event) => setStart(event.target.value)}
              disabled={busy}
            />
          </label>
          <label>
            Window end (exclusive)
            <input
              type="date"
              value={end}
              onChange={(event) => setEnd(event.target.value)}
              disabled={busy}
            />
          </label>
          <Button type="submit" disabled={!validWindow || busy}>
            Apply sample window
          </Button>
        </form>
        {!validWindow && (
          <p role="status">
            Use a positive half-open window contained in the original
            experiment.
          </p>
        )}
        {error && (
          <div role="alert" className="notice notice-error">
            {error}{" "}
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => {
                setLoading(true);
                setError("");
                setPoints([]);
                setTrades([]);
                setSeriesCursor(null);
                setTradeCursor(null);
                setRevision((old) => old + 1);
              }}
            >
              Retry samples
            </Button>
          </div>
        )}
        {loading ? (
          <p role="status">Loading sealed session samples…</p>
        ) : !points.length ? (
          error ? (
            <p>Session samples are unavailable for this window.</p>
          ) : (
            <EmptyState title="No sessions in this window">
              Choose a window containing pinned trading sessions. No values have
              been invented.
            </EmptyState>
          )
        ) : (
          <>
            <p>
              Showing {points.length} loaded session samples from {window.start}{" "}
              to {window.end} (exclusive).{" "}
              {seriesCursor
                ? "More sessions are available; charts are partial until loaded."
                : "All sessions in this window are loaded."}
            </p>
            <Charts points={points} />
            <div
              className="table-scroll"
              tabIndex={0}
              role="region"
              aria-label="Exact session series table"
            >
              <table>
                <caption>
                  Exact stored session samples · USD and fractions displayed as
                  percentages
                </caption>
                <thead>
                  <tr>
                    {[
                      "Session",
                      "Phase",
                      "Portfolio (USD)",
                      "SPY (USD)",
                      "Cash baseline (USD)",
                      "Cash held (USD)",
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
                  {points.map((point) => (
                    <tr key={point.session_date}>
                      <th scope="row">{point.session_date}</th>
                      <td>{point.phase}</td>
                      <td>
                        <Money value={point.portfolio_nav_usd} />
                      </td>
                      <td>
                        {point.benchmark_nav_usd == null ? (
                          `Unavailable · ${point.benchmark_unavailable_reason}`
                        ) : (
                          <Money value={point.benchmark_nav_usd} />
                        )}
                      </td>
                      <td>
                        <Money value={point.cash_baseline_nav_usd} />
                      </td>
                      <td>
                        <Money value={point.cash_usd} />
                      </td>
                      <td>
                        <Statistic value={point.drawdown_fraction} percent />
                      </td>
                      <td>
                        {point.cash_weight.value == null ? (
                          `Unavailable · ${point.cash_weight.unavailable_reason}`
                        ) : (
                          <ReturnPercent value={point.cash_weight.value} />
                        )}
                      </td>
                      <td>
                        {point.max_position_weight.value == null ? (
                          `Unavailable · ${point.max_position_weight.unavailable_reason}`
                        ) : (
                          <ReturnPercent
                            value={point.max_position_weight.value}
                          />
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {seriesCursor && (
              <Button
                disabled={busy || loading}
                onClick={() => void more("series")}
              >
                Load more session samples
              </Button>
            )}
            <label>
              Holdings session
              <select
                value={holding?.session_date ?? ""}
                onChange={(event) => setSelectedSession(event.target.value)}
              >
                {points.map((point) => (
                  <option key={point.session_date}>{point.session_date}</option>
                ))}
              </select>
            </label>
            {holding && (
              <>
                <p>
                  Stored cash: <Money value={holding.cash_usd} />. Cost basis is
                  not current market value.
                </p>
                {!holding.positions.length ? (
                  <p>No held stocks at this close.</p>
                ) : (
                  <div
                    className="table-scroll"
                    tabIndex={0}
                    role="region"
                    aria-label="Held positions table"
                  >
                    <table>
                      <caption>
                        Held positions at {holding.session_date}
                      </caption>
                      <thead>
                        <tr>
                          <th scope="col">Asset</th>
                          <th scope="col">Sector</th>
                          <th scope="col">Shares</th>
                          <th scope="col">Total cost basis (USD)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {holding.positions.map((position) => (
                          <tr key={position.asset_id}>
                            <th scope="row">{position.asset_id}</th>
                            <td>{position.sector}</td>
                            <td>
                              <Quantity value={position.quantity} />
                            </td>
                            <td>
                              <Money value={position.total_basis_usd} />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )}
          </>
        )}
      </Card>
      <Card title="Simulated execution log">
        <p>
          Historical simulation only. These records do not post durable paper
          fills.
        </p>
        {loading ? (
          <p role="status">Loading execution records…</p>
        ) : !trades.length ? (
          error ? (
            <p>Execution samples are unavailable for this window.</p>
          ) : (
            <EmptyState title="No simulated executions in this window">
              Cash-only periods and windows without orders have no execution
              rows.
            </EmptyState>
          )
        ) : (
          <>
            <p>
              {trades.length} loaded records
              {tradeCursor
                ? " · more available"
                : " · complete for this window"}
              .
            </p>
            <ul className="experiment-trades">
              {trades.map((trade) => (
                <li key={trade.id}>
                  <details>
                    <summary>
                      {trade.eligible_session.session_date} · {trade.order.side}{" "}
                      {trade.order.asset_id} ·{" "}
                      {trade.status.replaceAll("_", " ")}
                    </summary>
                    <dl className="data-facts">
                      <div>
                        <dt>Filled shares</dt>
                        <dd>
                          <Quantity value={trade.filled_quantity} />
                        </dd>
                      </div>
                      <div>
                        <dt>Skipped shares</dt>
                        <dd>
                          <Quantity value={trade.skipped_quantity} />
                        </dd>
                      </div>
                      <div>
                        <dt>Reason</dt>
                        <dd>{trade.reason ?? "No execution restriction"}</dd>
                      </div>
                      <div>
                        <dt>Decision cutoff</dt>
                        <dd>{trade.context.decision_cutoff}</dd>
                      </div>
                      <div>
                        <dt>Approval</dt>
                        <dd>{trade.context.approved_at}</dd>
                      </div>
                      <div>
                        <dt>Eligible open</dt>
                        <dd>{trade.eligible_session.open_at}</dd>
                      </div>
                      {trade.fill && (
                        <>
                          <div>
                            <dt>Execution price (USD)</dt>
                            <dd>{trade.fill.executed_price}</dd>
                          </div>
                          <div>
                            <dt>Gross (USD)</dt>
                            <dd>
                              <Money value={trade.fill.gross_usd} />
                            </dd>
                          </div>
                          <div>
                            <dt>Commission (USD)</dt>
                            <dd>
                              <Money value={trade.fill.commission_usd} />
                            </dd>
                          </div>
                          <div>
                            <dt>Slippage (USD)</dt>
                            <dd>
                              <Money value={trade.fill.slippage_usd} />
                            </dd>
                          </div>
                        </>
                      )}
                    </dl>
                    <p>
                      Terminal execution: {trade.terminal ? "yes" : "no"}.
                      Pending shares:{" "}
                      <Quantity value={trade.pending_quantity} />.
                    </p>
                    <details>
                      <summary>Complete execution evidence</summary>
                      <pre className="evidence-json" tabIndex={0}>
                        {JSON.stringify(trade, null, 2)}
                      </pre>
                    </details>
                  </details>
                </li>
              ))}
            </ul>
          </>
        )}
        {tradeCursor && (
          <Button
            disabled={busy || loading}
            onClick={() => void more("trades")}
          >
            Load more executions
          </Button>
        )}
      </Card>
    </>
  );
}
function windowOrigin() {
  return globalThis.window.location.origin;
}

export function ExperimentReport({ id }: { id: string }) {
  const router = useRouter();
  const [run, setRun] = useState<Run | null>(null);
  const [job, setJob] = useState<S["JobV1"] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const lifetime = useRef<AbortController | null>(null);
  useEffect(() => {
    if (!UUID_PATTERN.test(id)) return;
    const controller = new AbortController();
    lifetime.current = controller;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function poll() {
      try {
        const api = createApiClient(windowOrigin());
        const result = await api.GET("/api/v1/experiments/{experiment_id}", {
          params: { path: { experiment_id: id } },
          signal: controller.signal,
        });
        if (controller.signal.aborted) return;
        if (!result.data) {
          setRun(null);
          setJob(null);
          setError(experimentError(result.error?.error.code));
          return;
        }
        setRun(result.data);
        if (!terminal(result.data.status)) {
          const status = await api.GET("/api/v1/jobs/{job_id}", {
            params: { path: { job_id: result.data.job_id } },
            signal: controller.signal,
          });
          if (controller.signal.aborted) return;
          if (!status.data) {
            setError(
              "Job progress is unavailable. Refresh the report to retry.",
            );
            return;
          }
          setJob(status.data);
          timer = setTimeout(() => void poll(), 750);
        }
      } catch {
        if (!controller.signal.aborted) setError(experimentError());
      }
    }
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [id, revision]);
  async function cancel() {
    if (!run || busy || terminal(run.status)) return;
    setBusy(true);
    setError("");
    try {
      const result = await createApiClient(windowOrigin()).POST(
        "/api/v1/jobs/{job_id}/cancel",
        {
          params: { path: { job_id: run.job_id } },
          body: {},
          signal: lifetime.current?.signal,
        },
      );
      if (!result.data && result.error?.error.code !== "STATE_CONFLICT")
        setError(experimentError(result.error?.error.code));
      setRevision((old) => old + 1);
    } catch {
      if (!lifetime.current?.signal.aborted) setError(experimentError());
    } finally {
      setBusy(false);
    }
  }
  async function rerun() {
    if (!run || busy) return;
    setBusy(true);
    setError("");
    let navigated = false;
    try {
      const result = await createApiClient(windowOrigin()).POST(
        "/api/v1/experiments",
        {
          body: run.inputs,
          bodySerializer: () => run.inputs_canonical_json,
          signal: lifetime.current?.signal,
        },
      );
      if (!result.data) {
        setError(experimentError(result.error?.error.code));
        return;
      }
      router.push(`/lab/experiments/${result.data.experiment_id}`);
      navigated = true;
    } catch {
      if (!lifetime.current?.signal.aborted) setError(experimentError());
    } finally {
      if (!navigated) setBusy(false);
    }
  }
  if (!UUID_PATTERN.test(id))
    return (
      <>
        <h1>Invalid experiment ID</h1>
        <p role="alert">Open an experiment from the saved history.</p>
        <Link href="/lab/experiments">Experiment history</Link>
      </>
    );
  return (
    <div className="experiment-report">
      <div className="page-heading">
        <div>
          <p className="eyebrow">IMMUTABLE EXPERIMENT</p>
          <h1>Experiment report</h1>
          <p>
            <code>{id}</code>
          </p>
        </div>
        <Link href="/lab/experiments">Create or browse experiments</Link>
      </div>
      {error && (
        <p role="alert" className="notice notice-error">
          {error}
        </p>
      )}
      <Button
        variant="outline"
        disabled={busy}
        onClick={() => {
          setError("");
          setRevision((old) => old + 1);
        }}
      >
        Refresh report
      </Button>
      {!run ? (
        !error && <p role="status">Loading experiment…</p>
      ) : (
        <>
          <Card title={run.status.replaceAll("_", " ")}>
            <DataProvenanceBadge
              mode={run.data_status}
              provider={run.provider}
              asOf={run.report?.comparison.sessions.at(-1) ?? null}
              freshness={
                run.data_status === "synthetic_fixture"
                  ? "fixture"
                  : "unavailable"
              }
            />
            <p>
              Status:{" "}
              <strong aria-live="polite">
                {run.status.replaceAll("_", " ")}
              </strong>{" "}
              · USD · Paper only
            </p>
            {!terminal(run.status) && (
              <>
                <p>
                  Work runs in the bounded local worker. Partial financial
                  results stay unpublished.
                </p>
                {job && (
                  <>
                    <label>
                      Job progress
                      <progress max={100} value={job.progress}>
                        {job.progress}%
                      </progress>
                    </label>
                    <p>
                      {job.progress}% · Job <code>{job.id}</code>
                    </p>
                  </>
                )}
                <Button
                  disabled={busy || run.status === "cancel_requested"}
                  onClick={() => void cancel()}
                >
                  {run.status === "cancel_requested"
                    ? "Cancellation requested"
                    : "Cancel experiment"}
                </Button>
              </>
            )}
            {run.status === "cancelled" && (
              <p>Cancelled. No completed financial report was published.</p>
            )}
            {run.status === "failed" && (
              <p role="alert">
                The experiment failed: {run.error?.code}. {run.error?.message}{" "}
                No partial report is presented as complete.
              </p>
            )}
            <ExperimentWarnings warnings={run.warnings} />
            {terminal(run.status) && (
              <Button disabled={busy} onClick={() => void rerun()}>
                {busy
                  ? "Submitting same pinned inputs…"
                  : "Rerun with same inputs"}
              </Button>
            )}
          </Card>
          {run.status === "completed" && <Completed key={run.id} run={run} />}
          <Card title="Rules, inputs and provenance">
            <p>
              Strategy: {run.strategy_config.display_name}. Family:{" "}
              {run.strategy_config.signals.kind.replaceAll("_", " ")}. The
              engine applies eligibility, ranking, inverse-volatility allocation
              and risk caps from these immutable rules; historical results do
              not establish profitability.
            </p>
            <dl className="data-facts">
              <div>
                <dt>Strategy version</dt>
                <dd>
                  <code>{run.inputs.strategy_version_id}</code>
                </dd>
              </div>
              <div>
                <dt>Snapshot</dt>
                <dd>
                  <code>{run.inputs.snapshot_id}</code>
                </dd>
              </div>
              <div>
                <dt>Config SHA-256</dt>
                <dd>
                  <code>{run.config_sha256}</code>
                </dd>
              </div>
              <div>
                <dt>Snapshot SHA-256</dt>
                <dd>
                  <code>{run.snapshot_sha256}</code>
                </dd>
              </div>
              <div>
                <dt>Core engine</dt>
                <dd>
                  <code>{run.engine_version}</code>
                </dd>
              </div>
              <div>
                <dt>Random seed</dt>
                <dd>{storedSeed(run)}</dd>
              </div>
              <div>
                <dt>Window (end exclusive)</dt>
                <dd>
                  {run.inputs.start_session} to{" "}
                  {run.inputs.end_session_exclusive}
                </dd>
              </div>
              <div>
                <dt>Initial capital</dt>
                <dd>
                  <Money value={run.inputs.initial_capital_usd} />
                </dd>
              </div>
            </dl>
            <details>
              <summary>Exact immutable inputs and strategy rules</summary>
              <pre className="evidence-json" tabIndex={0}>
                {run.inputs_canonical_json}
              </pre>
              <pre className="evidence-json" tabIndex={0}>
                {JSON.stringify(run.strategy_config, null, 2)}
              </pre>
            </details>
            {run.report && (
              <details>
                <summary>
                  Execution, reporting and managed artifact evidence
                </summary>
                <p>
                  Execution costs:{" "}
                  <ReturnPercent
                    value={
                      run.report.comparison.execution_policy.slippage_fraction
                    }
                  />
                  adverse slippage per side; commission{" "}
                  <Money
                    value={
                      run.report.comparison.execution_policy.commission_usd
                    }
                  />
                  . {run.report.comparison.execution_policy.id}.
                </p>
                <p>
                  Reporting engine:{" "}
                  <code>{run.report.reporting_engine_version}</code>. Calendar
                  SHA-256: <code>{run.report.comparison.calendar_sha256}</code>.
                </p>
                <pre className="evidence-json" tabIndex={0}>
                  {JSON.stringify(
                    {
                      core_manifest_sha256: run.report.core_manifest_sha256,
                      comparison_sha256: run.report.comparison_sha256,
                      curve: run.curve_artifact,
                      trades: run.trade_artifact,
                      reproducibility: run.reproducibility_manifest,
                    },
                    null,
                    2,
                  )}
                </pre>
              </details>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
