"use client";

import Link from "next/link";
import {
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type FormEvent,
} from "react";
import { createApiClient } from "../api/generated/client";
import type { components } from "../api/generated/schema";
import { UUID_PATTERN } from "../lib/validation";
import {
  Card,
  DataProvenanceBadge,
  EmptyState,
  ReturnPercent,
  WarningsPanel,
} from "./evidence";
import { Button } from "./ui/button";
import { useWorkspace } from "./workspace-provider";

type S = components["schemas"];
type Mode = S["SnapshotV1"]["mode"];
const storageKey = "yams.lastStrategyEvaluation";
function readSavedEvaluation() {
  let saved = new URL(window.location.href).searchParams.get("evaluation");
  if (!saved) {
    try {
      saved = localStorage.getItem(storageKey);
    } catch {
      /* Optional storage. */
    }
  }
  return saved && UUID_PATTERN.test(saved) ? saved : "";
}
function subscribeSavedEvaluation(notify: () => void) {
  window.addEventListener("popstate", notify);
  window.addEventListener("storage", notify);
  return () => {
    window.removeEventListener("popstate", notify);
    window.removeEventListener("storage", notify);
  };
}
const serverSavedEvaluation = () => "";
const client = () => createApiClient(window.location.origin);
const number = (value: number | null | undefined) =>
  value == null ? "Unavailable" : value.toPrecision(6);

function Result({ evaluation }: { evaluation: S["StrategyEvaluationV1"] }) {
  const [query, setQuery] = useState("");
  const [limit, setLimit] = useState(50);
  const result = evaluation.result;
  if (!result) return null;
  const candidates = result.candidates.filter((row) =>
    row.asset_id.toLowerCase().includes(query.toLowerCase()),
  );
  const risk = result.constraint_evidence;
  return (
    <>
      <Card title="Pinned evaluation">
        <DataProvenanceBadge
          mode={result.mode}
          provider={evaluation.provider}
          asOf={result.as_of_session}
          freshness={
            result.mode === "synthetic_fixture" ? "fixture" : "unavailable"
          }
        />
        <p>
          Decision cutoff:{" "}
          <time dateTime={result.decision_cutoff_utc}>
            {result.decision_cutoff_utc}
          </time>
          . These are research targets; no paper holdings or orders changed.
        </p>
        <WarningsPanel warnings={result.warnings} />
        <details>
          <summary>Strategy rules and reproducibility</summary>
          <dl className="data-facts">
            <div>
              <dt>Evaluation</dt>
              <dd>
                <code>{evaluation.id}</code>
              </dd>
            </div>
            <div>
              <dt>Strategy version</dt>
              <dd>
                <code>{evaluation.inputs.strategy_version_id}</code>
              </dd>
            </div>
            <div>
              <dt>Snapshot</dt>
              <dd>
                <code>{evaluation.inputs.snapshot_id}</code>
              </dd>
            </div>
            <div>
              <dt>Calendar SHA-256</dt>
              <dd>
                <code>{result.reproducibility.calendar_sha256}</code>
              </dd>
            </div>
            <div>
              <dt>Snapshot SHA-256</dt>
              <dd>
                <code>{evaluation.snapshot_sha256}</code>
              </dd>
            </div>
            <div>
              <dt>Configuration SHA-256</dt>
              <dd>
                <code>{evaluation.config_sha256}</code>
              </dd>
            </div>
            <div>
              <dt>Engine source fingerprint</dt>
              <dd>
                <code>{evaluation.engine_version}</code>
              </dd>
            </div>
            <div>
              <dt>Result SHA-256</dt>
              <dd>
                <code>{evaluation.result_sha256}</code>
              </dd>
            </div>
          </dl>
          <pre className="evidence-json" tabIndex={0}>
            {JSON.stringify(evaluation.strategy_config, null, 2)}
          </pre>
        </details>
      </Card>
      <Card title="Target allocation">
        <p className="target-cash">
          Cash target{" "}
          <strong>
            <ReturnPercent value={result.cash_target_weight} />
          </strong>
        </p>
        {result.target_weights.length ? (
          <div
            className="table-scroll"
            role="region"
            aria-label="Target allocation table"
            tabIndex={0}
          >
            <table>
              <caption>
                Complete engine targets; any residual remains cash.
              </caption>
              <thead>
                <tr>
                  <th scope="col">Asset</th>
                  <th scope="col">Sector</th>
                  <th scope="col">Target weight</th>
                </tr>
              </thead>
              <tbody>
                {result.target_weights.map((row) => (
                  <tr key={row.asset_id}>
                    <th scope="row">{row.asset_id}</th>
                    <td>{row.sector}</td>
                    <td>
                      <ReturnPercent value={row.weight} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title="Cash-only target">
            The engine allocated all capital to cash. Inspect the allocation
            reasons and exclusions below.
          </EmptyState>
        )}
        <WarningsPanel warnings={result.allocation_reasons} />
        <dl className="data-facts">
          <div>
            <dt>Position limit</dt>
            <dd>
              <ReturnPercent value={risk.position_limit} />
            </dd>
          </div>
          <div>
            <dt>Sector limit</dt>
            <dd>
              <ReturnPercent value={risk.sector_limit} />
            </dd>
          </div>
          <div>
            <dt>Cash floor</dt>
            <dd>
              <ReturnPercent value={risk.cash_floor} />
            </dd>
          </div>
          <div>
            <dt>Unallocated investable capacity</dt>
            <dd>
              <ReturnPercent value={risk.unmet_investable_weight} />
            </dd>
          </div>
        </dl>
        <details>
          <summary>Full constraint evidence</summary>
          <pre className="evidence-json" tabIndex={0}>
            {JSON.stringify(risk, null, 2)}
          </pre>
        </details>
      </Card>
      <Card title="Candidates and exclusions">
        <p>
          {evaluation.strategy_config.signals.kind ===
          "risk_adjusted_momentum" ? (
            <>
              Long/short momentum use{" "}
              {evaluation.strategy_config.signals.momentum_long_sessions}/
              {evaluation.strategy_config.signals.momentum_short_sessions}{" "}
              sessions;{" "}
            </>
          ) : evaluation.strategy_config.signals.kind === "mean_reversion" ? (
            <>
              Mean reversion ranks distance below the{" "}
              {evaluation.strategy_config.signals.mean_reversion_sessions}
              -session moving average. Weakness can continue; the trend and
              allocation controls still apply.{" "}
            </>
          ) : (
            <>
              Low volatility ranks lower historical volatility first. Historical
              stability does not guarantee smaller future losses.{" "}
            </>
          )}
          Volatility uses{" "}
          {evaluation.strategy_config.signals.volatility_sessions} returns.
          Scores and ranks come from the shared engine. Values are fractional
          units (0.10 = 10%); scores are dimensionless.
        </p>
        <label className="field-label" htmlFor="candidate-search">
          Find an asset ID
        </label>
        <input
          id="candidate-search"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setLimit(50);
          }}
        />
        <p>
          Showing {Math.min(limit, candidates.length)} of {candidates.length}{" "}
          matching candidates ({result.candidates.length} total). Full stored
          evidence is preserved.
        </p>
        {candidates.length ? (
          <div
            className="table-scroll"
            role="region"
            aria-label="Candidate evidence table"
            tabIndex={0}
          >
            <table>
              <caption>
                Eligible and rejected candidates, including diagnostic
                zero-volatility ranks.
              </caption>
              <thead>
                <tr>
                  <th scope="col">Asset</th>
                  <th scope="col">Rank</th>
                  <th scope="col">Score</th>
                  {evaluation.strategy_config.signals.kind ===
                  "risk_adjusted_momentum" ? (
                    <>
                      <th scope="col">Long momentum</th>
                      <th scope="col">Short momentum</th>
                    </>
                  ) : evaluation.strategy_config.signals.kind ===
                    "mean_reversion" ? (
                    <th scope="col">Distance below moving average</th>
                  ) : null}
                  <th scope="col">Annualized volatility</th>
                  <th scope="col">Status / evidence</th>
                </tr>
              </thead>
              <tbody>
                {candidates.slice(0, limit).map((row) => (
                  <tr key={row.asset_id}>
                    <th scope="row">{row.asset_id}</th>
                    <td>{row.rank ?? "Unranked"}</td>
                    <td>{number(row.scoring?.score)}</td>
                    {evaluation.strategy_config.signals.kind ===
                    "risk_adjusted_momentum" ? (
                      <>
                        <td>
                          {number(
                            row.features && "momentum_long" in row.features
                              ? row.features.momentum_long
                              : null,
                          )}
                        </td>
                        <td>
                          {number(
                            row.features && "momentum_short" in row.features
                              ? row.features.momentum_short
                              : null,
                          )}
                        </td>
                      </>
                    ) : evaluation.strategy_config.signals.kind ===
                      "mean_reversion" ? (
                      <td>
                        {number(
                          row.features &&
                            "mean_reversion_distance" in row.features
                            ? row.features.mean_reversion_distance
                            : null,
                        )}
                      </td>
                    ) : null}
                    <td>{number(row.features?.volatility)}</td>
                    <td>
                      {row.allocation_eligible
                        ? "Allocation eligible"
                        : "Excluded from allocation"}
                      {row.reasons.length > 0 && (
                        <ul>
                          {row.reasons.map((reason) => (
                            <li key={reason}>{reason}</li>
                          ))}
                        </ul>
                      )}
                      <details>
                        <summary>Evidence for {row.asset_id}</summary>
                        <pre className="evidence-json" tabIndex={0}>
                          {JSON.stringify(row, null, 2)}
                        </pre>
                      </details>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title="No matching candidates">
            Try another asset ID or inspect the data diagnostics below.
          </EmptyState>
        )}
        {limit < candidates.length && (
          <Button variant="outline" onClick={() => setLimit(limit + 50)}>
            Show next 50 candidates
          </Button>
        )}
        <details>
          <summary>Data and allocation diagnostics</summary>
          <pre className="evidence-json" tabIndex={0}>
            {JSON.stringify(
              {
                data: result.data_diagnostics,
                allocation: result.allocation_exclusions,
              },
              null,
              2,
            )}
          </pre>
        </details>
      </Card>
    </>
  );
}

export function CandidateInspection() {
  const { setJob } = useWorkspace();
  const [mode, setMode] = useState<Mode>("synthetic_fixture");
  const [snapshots, setSnapshots] = useState<S["SnapshotV1"][]>([]);
  const [strategies, setStrategies] = useState<S["StrategyV1"][]>([]);
  const [snapshotId, setSnapshotId] = useState("");
  const [versionId, setVersionId] = useState("");
  const [asOf, setAsOf] = useState("");
  const [cursor, setCursor] = useState<string | null>(null);
  const [inventoryError, setInventoryError] = useState("");
  const [error, setError] = useState("");
  const [admissionError, setAdmissionError] = useState("");
  const [admissionCorrelation, setAdmissionCorrelation] = useState<
    string | null
  >(null);
  const [lookupError, setLookupError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [reload, setReload] = useState(0);
  const [chosenRunId, setRunId] = useState("");
  const savedRunId = useSyncExternalStore(
    subscribeSavedEvaluation,
    readSavedEvaluation,
    serverSavedEvaluation,
  );
  const runId = chosenRunId || savedRunId;
  const discovery = useRef<AbortController | null>(null);
  const [lookup, setLookup] = useState<string | null>(null);
  const [evaluation, setEvaluation] = useState<
    S["StrategyEvaluationV1"] | null
  >(null);
  const [pollRevision, setPollRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    discovery.current = controller;
    const api = createApiClient(window.location.origin, (input, init) =>
      fetch(input, { ...init, signal: controller.signal }),
    );
    async function load() {
      try {
        const [data, rules] = await Promise.all([
          api.GET("/api/v1/data/snapshots", {
            params: { query: { mode, limit: 25 } },
          }),
          api.GET("/api/v1/strategies", { params: { query: { limit: 100 } } }),
        ]);
        if (controller.signal.aborted) return;
        if (!data.data || !rules.data) throw new Error("unavailable");
        setSnapshots(data.data.items);
        setCursor(data.data.next_cursor);
        setStrategies(rules.data.items);
        const first = data.data.items.find((row) => row.quality !== "blocked");
        setSnapshotId(first?.id ?? "");
        setAsOf(first?.latest_completed_session ?? "");
        setVersionId((old) =>
          rules.data!.items.some((row) => row.published_version.id === old)
            ? old
            : (rules.data!.items.find(
                (row) => row.template_key === "risk_adjusted_momentum_v1",
              )?.published_version.id ??
              rules.data!.items[0]?.published_version.id ??
              ""),
        );
      } catch {
        if (!controller.signal.aborted)
          setInventoryError(
            "Snapshot or strategy discovery is unavailable. Reload choices to try again.",
          );
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    void load();
    return () => controller.abort();
  }, [mode, reload]);
  useEffect(() => {
    if (!runId) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let failures = 0;
    const api = createApiClient(window.location.origin, (input, init) =>
      fetch(input, { ...init, signal: controller.signal }),
    );
    async function poll() {
      try {
        const response = await api.GET(
          "/api/v1/strategy-evaluations/{evaluation_id}",
          { params: { path: { evaluation_id: runId } } },
        );
        if (controller.signal.aborted) return;
        if (!response.data) {
          if (response.response.status === 404) {
            setError("That evaluation was not found. Check its saved ID.");
            return;
          }
          throw new Error("unavailable");
        }
        failures = 0;
        setEvaluation(response.data);
        setError("");
        try {
          const job = await api.GET("/api/v1/jobs/{job_id}", {
            params: { path: { job_id: response.data.job_id } },
          });
          if (job.data && !controller.signal.aborted) setJob(job.data);
        } catch {
          /* Evaluation status is independently persisted and verified. */
        }
        if (controller.signal.aborted) return;
        if (
          ["queued", "running", "cancel_requested"].includes(
            response.data.status,
          )
        )
          timer = setTimeout(() => void poll(), 2000);
      } catch {
        if (!controller.signal.aborted) {
          failures += 1;
          if (failures <= 3) {
            setError(
              `Status is unavailable. Retrying (${failures}/3); saved evidence may be out of date.`,
            );
            timer = setTimeout(() => void poll(), 1000 * 2 ** failures);
          } else
            setError(
              "Automatic updates stopped after repeated failures. Use Reload evaluation to resume.",
            );
        }
      }
    }
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [runId, pollRevision, setJob]);
  function selectRun(identity: string) {
    setEvaluation(null);
    setAdmissionError("");
    setAdmissionCorrelation(null);
    setLookupError("");
    setError("");
    setRunId(identity);
    setLookup(identity);
    setPollRevision((value) => value + 1);
    const url = new URL(window.location.href);
    url.searchParams.set("evaluation", identity);
    window.history.replaceState(null, "", url);
    try {
      localStorage.setItem(storageKey, identity);
    } catch {
      /* URL retains recovery ID. */
    }
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setAdmissionError("");
    setAdmissionCorrelation(null);
    try {
      const response = await client().POST("/api/v1/strategy-evaluations", {
        body: {
          strategy_version_id: versionId,
          snapshot_id: snapshotId,
          as_of_session: asOf,
        },
      });
      if (!response.data) {
        setAdmissionCorrelation(response.error?.error.correlation_id ?? null);
        const code = response.error?.error.code;
        setAdmissionError(
          code === "STALE_DATA"
            ? "The selected snapshot is blocked or lacks a completed session at that date."
            : code === "INSUFFICIENT_MARKET_DATA"
              ? "Choose a session with data and a scheduled next trading session in this snapshot."
              : code === "WORKLOAD_LIMIT"
                ? "This snapshot exceeds supported diagnostic workload limits."
                : "Evaluation could not be queued. Check the inputs and local service, then try again.",
        );
        return;
      }
      selectRun(response.data.evaluation_id);
    } catch {
      setAdmissionError(
        "Evaluation could not be queued. Check the local service and try again.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function moreSnapshots() {
    const controller = discovery.current;
    if (!cursor || !controller || controller.signal.aborted) return;
    const api = createApiClient(window.location.origin, (input, init) =>
      fetch(input, { ...init, signal: controller.signal }),
    );
    try {
      const response = await api.GET("/api/v1/data/snapshots", {
        params: { query: { mode, limit: 25, cursor } },
      });
      if (!response.data) throw new Error("unavailable");
      if (controller.signal.aborted || discovery.current !== controller) return;
      setSnapshots((old) => [...old, ...response.data!.items]);
      setCursor(response.data.next_cursor);
    } catch {
      if (!controller.signal.aborted && discovery.current === controller)
        setInventoryError(
          "More snapshot history could not be loaded. Try again.",
        );
    }
  }
  function resetChoices(nextMode: Mode = mode) {
    setMode(nextMode);
    setAdmissionError("");
    setAdmissionCorrelation(null);
    setLoading(true);
    setInventoryError("");
    setSnapshots([]);
    setSnapshotId("");
    setAsOf("");
    setCursor(null);
    setReload((value) => value + 1);
  }
  const inventory = snapshots.filter((row) => row.mode === mode);
  const selected = inventory.find((row) => row.id === snapshotId);
  const pending =
    evaluation &&
    ["queued", "running", "cancel_requested"].includes(evaluation.status);
  return (
    <div className="candidate-inspection">
      <div className="page-heading">
        <div>
          <p className="eyebrow">TRACE THE DECISION</p>
          <h1>Candidate inspection</h1>
          <p>
            Explore measured signals, exclusions and feasible targets. Paper
            only.
          </p>
        </div>
      </div>
      <Card title="Choose pinned inputs">
        {inventoryError && (
          <p role="alert" className="notice notice-error">
            {inventoryError}
          </p>
        )}
        {admissionError && (
          <p role="alert" className="notice notice-error">
            {admissionError}
            {admissionCorrelation && (
              <>
                {" "}
                Diagnostic ID: <code>{admissionCorrelation}</code>
              </>
            )}
          </p>
        )}
        {mode === "research_market_data" && (
          <p className="notice">
            Research evaluations require an elapsed decision cutoff: one hour
            before the next pinned trading session opens. Only evidence observed
            by that cutoff is eligible. Downloading historical prices cannot
            backdate their availability. Targets are diagnostics only; no orders
            or holdings change.
          </p>
        )}
        <form
          onSubmit={(event) => void submit(event)}
          className="inspection-form"
        >
          <label>
            Data source
            <select
              value={mode}
              onChange={(event) => resetChoices(event.target.value as Mode)}
            >
              <option value="synthetic_fixture">Synthetic demo</option>
              <option value="research_market_data">Market research data</option>
            </select>
          </label>
          <label>
            Snapshot
            <select
              value={snapshotId}
              onChange={(event) => {
                const value = snapshots.find(
                  (row) => row.id === event.target.value,
                );
                setSnapshotId(event.target.value);
                setAsOf(value?.latest_completed_session ?? "");
              }}
              disabled={loading || !inventory.length}
            >
              <option value="">
                {loading ? "Loading snapshots…" : "Choose a snapshot"}
              </option>
              {inventory.map((row) => (
                <option
                  key={row.id}
                  value={row.id}
                  disabled={row.quality === "blocked"}
                >
                  {row.latest_completed_session ?? "No complete session"} ·{" "}
                  {row.id} · {row.quality}
                </option>
              ))}
            </select>
          </label>
          <label>
            Strategy version
            <select
              value={versionId}
              onChange={(event) => setVersionId(event.target.value)}
              disabled={loading || !strategies.length}
            >
              <option value="">Choose a published version</option>
              {strategies.map((row) => (
                <option
                  key={row.published_version.id}
                  value={row.published_version.id}
                >
                  {row.name} · version {row.published_version.version}
                </option>
              ))}
            </select>
          </label>
          <label>
            As-of session
            <input
              type="date"
              value={asOf}
              min={selected?.coverage.first_session ?? undefined}
              max={selected?.coverage.latest_completed_session ?? undefined}
              onChange={(event) => setAsOf(event.target.value)}
              required
            />
          </label>
          <div className="inspection-actions">
            <Button
              type="submit"
              disabled={loading || busy || !snapshotId || !versionId || !asOf}
            >
              {busy ? "Queuing…" : "Evaluate pinned inputs"}
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => resetChoices()}
            >
              Reload choices
            </Button>
          </div>
        </form>
        {cursor && (
          <Button variant="outline" onClick={() => void moreSnapshots()}>
            Load older snapshots
          </Button>
        )}
        {!loading && !inventory.length && (
          <EmptyState
            title={
              mode === "synthetic_fixture"
                ? "No synthetic snapshot registered"
                : "No research snapshot registered"
            }
          >
            Prepare a snapshot in Settings & data. No source is substituted
            automatically.
          </EmptyState>
        )}
        <Link className="text-link" href="/settings/data">
          Prepare or inspect dataset coverage →
        </Link>
        {selected && (
          <>
            <DataProvenanceBadge
              mode={selected.mode}
              asOf={selected.latest_completed_session}
              provider={selected.provider}
              freshness={
                selected.mode === "synthetic_fixture"
                  ? "fixture"
                  : "unavailable"
              }
            />
            <WarningsPanel warnings={selected.warnings} />
          </>
        )}
      </Card>
      <Card title="Saved evaluation">
        <form
          className="lookup-row"
          onSubmit={(event) => {
            event.preventDefault();
            if (UUID_PATTERN.test(lookup ?? runId)) selectRun(lookup ?? runId);
            else setLookupError("Enter a valid saved evaluation UUID.");
          }}
        >
          <label htmlFor="evaluation-lookup">Evaluation ID</label>
          <input
            id="evaluation-lookup"
            value={lookup ?? runId}
            onChange={(event) => {
              setLookup(event.target.value);
              setLookupError("");
            }}
          />
          <Button variant="outline" type="submit">
            Load saved evaluation
          </Button>
        </form>
        {runId && (
          <>
            <p>
              <code>{runId}</code>
            </p>
            <Button
              variant="outline"
              onClick={() => setPollRevision((value) => value + 1)}
            >
              Reload evaluation
            </Button>
          </>
        )}
        {(lookupError || error) && (
          <p role="alert" className="notice notice-error">
            {lookupError || error}
          </p>
        )}
        {runId && !evaluation && !error && (
          <p role="status">Loading persisted evaluation…</p>
        )}
        {evaluation && (
          <>
            <p role="status">
              Evaluation status:{" "}
              <strong>{evaluation.status.replaceAll("_", " ")}</strong>
            </p>
            <p>
              Job <code>{evaluation.job_id}</code>
            </p>
            <p>
              As-of {evaluation.inputs.as_of_session} ·{" "}
              {evaluation.mode === "synthetic_fixture"
                ? "Synthetic demonstration"
                : "Market research data"}
            </p>
          </>
        )}
        {pending && (
          <p>
            The worker is processing pinned inputs. No target is shown until
            completion.
          </p>
        )}
        {evaluation?.status === "failed" && (
          <p role="alert">
            Evaluation failed: {evaluation.error?.code}. No completed targets
            were published. Diagnostic ID: {evaluation.error?.correlation_id}
          </p>
        )}
        {evaluation?.status === "cancelled" && (
          <p>
            The evaluation was cancelled; no completed targets were published.
          </p>
        )}
      </Card>
      {evaluation?.status === "completed" && evaluation.result && (
        <Result key={evaluation.id} evaluation={evaluation} />
      )}
    </div>
  );
}
