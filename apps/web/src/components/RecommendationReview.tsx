"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { createApiClient } from "../api/generated/client";
import type { components } from "../api/generated/schema";
import { UUID_PATTERN } from "../lib/validation";
import { Card, DataProvenanceBadge, Money, ReturnPercent } from "./evidence";
import { Button } from "./ui/button";
import { HoldingsTable } from "./portfolios/HoldingsTable";
import { DecisionEvidence } from "./decisions/DecisionEvidence";
import { PaperControls } from "./decisions/PaperControls";
type S = components["schemas"];
type Attempt = { key: string; body: S["RecommendationRequest"] };
export function RecommendationReview({ id }: { id: string }) {
  const [account, setAccount] = useState<S["PaperPortfolioV1"] | null>(null);
  const [inputs, setInputs] = useState<S["DecisionInputsV1"] | null>(null);
  const [schedule, setSchedule] = useState<S["PortfolioScheduleV1"] | null>(
    null,
  );
  const [history, setHistory] = useState<S["RecommendationSummaryV1"][]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [selected, setSelected] = useState("");
  const [decision, setDecision] = useState<S["RecommendationDetailV1"] | null>(
    null,
  );
  const [job, setJob] = useState<S["JobV1"] | null>(null);
  const [asOf, setAsOf] = useState("");
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [storageReady, setStorageReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [epoch, setEpoch] = useState(0);
  const locked = useRef(false);
  const historyExpanded = useRef(false);
  const storage = `yams:review:v1:${id}`;
  const refresh = () => setEpoch((v) => v + 1);
  useEffect(() => {
    let live = true;
    void Promise.resolve().then(() => {
      if (!live) return;
      try {
        const raw = localStorage.getItem(storage);
        if (!raw) setStorageReady(true);
        if (raw) {
          const value = JSON.parse(raw) as Attempt;
          if (
            !UUID_PATTERN.test(value.key) ||
            !/^\d{4}-\d{2}-\d{2}$/.test(value.body.as_of_session) ||
            value.body.clock_mode !== "synthetic_replay" ||
            value.body.seed !== 42
          )
            throw new Error("Invalid saved request");
          setStorageReady(true);
          setAttempt(value);
          setAsOf(value.body.as_of_session);
        }
      } catch {
        setActionError(
          "Saved review request cannot be read. Resolve local storage before submitting a new request.",
        );
      }
    });
    return () => {
      live = false;
    };
  }, [storage]);
  useEffect(() => {
    const c = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    void (async () => {
      if (!UUID_PATTERN.test(id)) {
        setError("Invalid account identifier.");
        setLoading(false);
        return;
      }
      setError("");
      try {
        const api = createApiClient(window.location.origin);
        const [a, context, s, h] = await Promise.all([
          api.GET("/api/v1/portfolios/{portfolio_id}", {
            params: { path: { portfolio_id: id } },
            signal: c.signal,
          }),
          api.GET("/api/v1/portfolios/{portfolio_id}/decision-inputs", {
            params: { path: { portfolio_id: id } },
            signal: c.signal,
          }),
          api.GET("/api/v1/portfolios/{portfolio_id}/schedule", {
            params: { path: { portfolio_id: id } },
            signal: c.signal,
          }),
          api.GET("/api/v1/portfolios/{portfolio_id}/recommendations", {
            params: { path: { portfolio_id: id }, query: { limit: 25 } },
            signal: c.signal,
          }),
        ]);
        if (c.signal.aborted) return;
        if (!a.data || !h.data)
          throw new Error(
            a.response.status === 404
              ? "Paper account not found."
              : "Account or decision history unavailable.",
          );
        setAccount(a.data);
        setInputs(context.data ?? null);
        setSchedule(s.data ?? null);
        setHistory((old) => [
          ...h.data!.items,
          ...old.filter(
            (row) => !h.data!.items.some((fresh) => fresh.id === row.id),
          ),
        ]);
        if (!historyExpanded.current) setCursor(h.data.next_cursor);
        if (context.data?.suggested_session)
          setAsOf((old) => old || context.data!.suggested_session!);
        const identity = selected || h.data.items[0]?.id;
        if (identity && !selected) {
          setSelected(identity);
          return;
        }
        if (identity) {
          const original = h.data.items.find((r) => r.id === identity);
          const j = original
            ? await api.GET("/api/v1/jobs/{job_id}", {
                params: { path: { job_id: original.job_id } },
                signal: c.signal,
              })
            : null;
          const r = await api.GET(
            "/api/v1/recommendations/{recommendation_id}",
            {
              params: { path: { recommendation_id: identity } },
              signal: c.signal,
            },
          );
          if (c.signal.aborted) return;
          setJob(j?.data ?? null);
          if (r.data) {
            setDecision(r.data);
            // The server serves a published detail only after the review job
            // completes. Preserve older pages, but refresh this original row's
            // current disposition/status from that authoritative response.
            setHistory((rows) =>
              rows.map((row) =>
                row.id === identity
                  ? {
                      ...row,
                      status: "completed",
                      disposition: r.data!.status,
                      error: null,
                    }
                  : row,
              ),
            );
          } else if (r.response.status !== 409)
            throw new Error(
              "Original decision evidence unavailable. Previously displayed evidence may be stale.",
            );
          const active =
            j?.data &&
            ["queued", "running", "cancel_requested"].includes(j.data.status);
          const forecasting =
            r.data &&
            ["queued", "running", "cancel_requested"].includes(
              r.data.forecast_job.status,
            );
          if (active || forecasting)
            timer = setTimeout(() => setEpoch((v) => v + 1), 2000);
        }
      } catch (e) {
        if (!c.signal.aborted)
          setError(
            e instanceof Error
              ? e.message
              : "Local services unavailable. Refresh to retry.",
          );
      } finally {
        if (!c.signal.aborted) setLoading(false);
      }
    })();
    return () => {
      c.abort();
      clearTimeout(timer);
    };
  }, [id, selected, epoch]);
  async function generate() {
    if (
      locked.current ||
      !storageReady ||
      (!attempt && (!asOf || !inputs?.snapshot_id))
    )
      return;
    locked.current = true;
    setBusy(true);
    setActionError("");
    try {
      const value = attempt ?? {
        key: crypto.randomUUID(),
        body: {
          as_of_session: asOf,
          snapshot_id: inputs!.snapshot_id,
          clock_mode: "synthetic_replay" as const,
          seed: 42,
        },
      };
      localStorage.setItem(storage, JSON.stringify(value));
      setAttempt(value);
      const r = await createApiClient(window.location.origin).POST(
        "/api/v1/portfolios/{portfolio_id}/recommendations",
        {
          params: {
            path: { portfolio_id: id },
            header: { "Idempotency-Key": value.key },
          },
          body: value.body,
        },
      );
      if (!r.data) {
        if (r.response.status >= 500)
          throw new Error(
            "Review outcome unconfirmed. Retry the saved request with its original date and key.",
          );
        localStorage.removeItem(storage);
        setAttempt(null);
        setActionError(
          r.error?.error.message ??
            "Review conflicts with current state. Refresh and inspect the source.",
        );
        return;
      }
      localStorage.removeItem(storage);
      setAttempt(null);
      setDecision(null);
      setSelected(r.data.recommendation_id);
      refresh();
    } catch (e) {
      setActionError(
        e instanceof Error
          ? e.message
          : "Connection lost. Retry the saved review; no new key will be created.",
      );
    } finally {
      locked.current = false;
      setBusy(false);
    }
  }
  async function cancelJob(identity: string) {
    try {
      const r = await createApiClient(window.location.origin).POST(
        "/api/v1/jobs/{job_id}/cancel",
        { params: { path: { job_id: identity } }, body: {} },
      );
      if (!r.data) throw new Error("Job state changed; refresh to inspect it.");
      refresh();
    } catch {
      setActionError(
        "Cancellation is unconfirmed. Refresh the original job before retrying.",
      );
    }
  }
  async function older() {
    if (!cursor || busy) return;
    setBusy(true);
    try {
      const r = await createApiClient(window.location.origin).GET(
        "/api/v1/portfolios/{portfolio_id}/recommendations",
        {
          params: { path: { portfolio_id: id }, query: { limit: 25, cursor } },
        },
      );
      if (!r.data) throw new Error();
      setHistory((old) => [
        ...new Map(
          [...old, ...r.data!.items].map((row) => [row.id, row]),
        ).values(),
      ]);
      historyExpanded.current = true;
      setCursor(r.data.next_cursor);
    } catch {
      setActionError(
        "Older history unavailable; displayed rows are a partial page.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="portfolio-page decision-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">REVIEW → AUTHORIZE → OBSERVE</p>
          <h1>Decision Center</h1>
          <p>{account?.name ?? "Paper account"} · Paper only</p>
        </div>
        <Button variant="outline" onClick={refresh}>
          Refresh decision and posted state
        </Button>
      </div>
      <Link href={`/portfolios/${id}`}>
        ← Posted account and transaction ledger
      </Link>
      {loading && (
        <p role="status">
          Loading account, current source and original decisions…
        </p>
      )}
      {error && (
        <p role="alert" className="notice notice-error">
          {error} Refresh before authorizing; previously displayed evidence is
          not a fresh approval check.
        </p>
      )}
      {account && (
        <>
          <DataProvenanceBadge
            mode={account.valuation_mode}
            asOf={account.valuation_as_of_session}
            freshness={
              account.valuation_mode === "synthetic_fixture"
                ? "fixture"
                : "unavailable"
            }
          />
          {account.valuation_mode === "synthetic_fixture" && (
            <p className="small-label">SYNTHETIC_DATA_ONLY</p>
          )}
          <Card title="1. Posted holdings and review inputs">
            <p>
              Posted valuation marks:{" "}
              {account.valuation_as_of_session ?? "Unavailable"}. Original
              decisions below retain their own as-of session and frozen account
              state.
            </p>
            <p>
              Posted cash <Money value={account.cash_usd} /> · Account value{" "}
              <Money value={account.total_value_usd} /> · Revision{" "}
              {account.revision}
            </p>
            <HoldingsTable holdings={account.holdings} />
            <p>
              Position cap{" "}
              <ReturnPercent value={account.risk_policy.max_position_weight} />{" "}
              · Minimum trade{" "}
              <Money value={account.risk_policy.min_trade_usd} />
            </p>
            <p>
              Bound version <code>{account.strategy_version_id}</code>
            </p>
            {account.valuation.status !== "available" && (
              <p className="notice notice-warning">
                Valuation {account.valuation.status}: {account.valuation.reason}
                . A missing mark is never zero.
              </p>
            )}
            <p>
              Explicit synthetic replay: selecting and submitting a later
              session observes that virtual cutoff without trading. The clock
              cannot rewind. Background reviews never advance future time.
              Current clock {inputs?.clock_at ?? "Unavailable"}.
            </p>
            <p>
              The server suggests the earliest session with 252 calendar return
              intervals and pinned 90-day horizon support. Actual prices and
              eligibility are checked by the engine; no return-based date
              selection.
            </p>
            {!inputs?.snapshot_id && (
              <p role="status">
                No registered accounting snapshot.{" "}
                <Link href="/settings/data">
                  Load the offline fixture snapshot
                </Link>
                , then refresh.
              </p>
            )}
            {inputs?.unavailable_reason && (
              <p>
                Session suggestion unavailable:{" "}
                {inputs.unavailable_reason.replaceAll("_", " ")}. You can
                inspect existing evidence; data failures remain explicit.
              </p>
            )}
            <form
              className="portfolio-form"
              onSubmit={(e) => {
                e.preventDefault();
                void generate();
              }}
            >
              <label htmlFor="decision-session">
                As-of pinned session
                <input
                  id="decision-session"
                  type="date"
                  required
                  value={asOf}
                  onChange={(e) => setAsOf(e.target.value)}
                  disabled={busy || !!attempt}
                />
              </label>
              <div className="portfolio-actions">
                <Button
                  type="submit"
                  disabled={
                    busy ||
                    !storageReady ||
                    (!attempt &&
                      (!asOf ||
                        !inputs?.snapshot_id ||
                        account.state !== "active" ||
                        account.valuation_mode !== "synthetic_fixture" ||
                        account.reconciliation_failed))
                  }
                >
                  {busy
                    ? "Submitting review…"
                    : attempt
                      ? "Recover saved review request"
                      : "Generate paper review"}
                </Button>
              </div>
            </form>
            {actionError && (
              <p role="alert" className="notice notice-error">
                {actionError}
              </p>
            )}
          </Card>
          <Card title="Original review history">
            <p>
              Cached computed decisions retain their original inputs and
              evidence. Select one to inspect it; a new review never rewrites an
              old decision.
            </p>
            <label htmlFor="decision-history">
              Review
              <select
                id="decision-history"
                value={selected}
                onChange={(e) => {
                  setDecision(null);
                  setJob(null);
                  setSelected(e.target.value);
                }}
              >
                <option value="">No selected review</option>
                {history.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.inputs.as_of_session} · {r.status} ·{" "}
                    {r.disposition ?? "unpublished"} · {r.id}
                  </option>
                ))}
              </select>
            </label>
            {!history.length && (
              <p>No generated review yet. Submit the explicit date above.</p>
            )}
            {cursor && (
              <Button
                variant="outline"
                disabled={busy}
                onClick={() => void older()}
              >
                Load older reviews
              </Button>
            )}
            {job && (
              <>
                <p role="status">
                  Review job {job.status} ·{" "}
                  {job.error?.message ?? "Original worker status"}
                </p>
                {["queued", "running"].includes(job.status) && (
                  <Button
                    variant="outline"
                    onClick={() => void cancelJob(job.id)}
                  >
                    Cancel review job
                  </Button>
                )}
              </>
            )}
            {decision &&
              ["queued", "running"].includes(decision.forecast_job.status) && (
                <Button
                  variant="outline"
                  onClick={() => void cancelJob(decision.forecast_job.id)}
                >
                  Cancel scenario job
                </Button>
              )}
          </Card>
          {decision && <DecisionEvidence decision={decision} />}
          <PaperControls
            key={decision?.id ?? "pending"}
            recommendationId={selected || null}
            decision={error ? null : decision}
            refresh={refresh}
            initialBatchId={
              schedule?.active_batch_controls_available
                ? schedule.active_order_batch_id
                : null
            }
          />
          <Card title="Monthly review status">
            <p>
              Next session {schedule?.next_review_session ?? "Not yet known"} ·
              Due {schedule?.next_review_due_at ?? "Not yet known"}
            </p>
            <p>
              Backlog{" "}
              {schedule?.due_backlog == null
                ? "Unknown"
                : schedule.due_backlog
                  ? "Due work remains"
                  : "No due work reported"}{" "}
              · Last scan {schedule?.last_observed_at ?? "Unobserved"}
            </p>
            <p>
              Supervisor {schedule?.supervisor.status ?? "Unavailable"}.
              Monitoring only runs while Docker is active; observation gaps are
              not exact shutdown times.
            </p>
          </Card>
        </>
      )}
    </div>
  );
}
