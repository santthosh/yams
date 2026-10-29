"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { createApiClient } from "../../api/generated/client";
import type { components } from "../../api/generated/schema";
import { Card, DataProvenanceBadge, EmptyState, Money } from "../evidence";
import { Button } from "../ui/button";

type S = components["schemas"];
type Mode = S["PaperPortfolioV1"]["valuation_mode"];
type Attempt = { key: string; body: S["PortfolioCreateRequest"] };
export function PortfolioBrowser() {
  const router = useRouter();
  const [accounts, setAccounts] = useState<S["PaperPortfolioV1"][]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode | "">("");
  const [epoch, setEpoch] = useState(0);
  const [loading, setLoading] = useState(true);
  const [moreLoading, setMoreLoading] = useState(false);
  const [error, setError] = useState("");
  const [strategies, setStrategies] = useState<S["StrategyV1"][]>([]);
  const [strategyCursor, setStrategyCursor] = useState<string | null>(null);
  const [strategyId, setStrategyId] = useState("");
  const [strategyError, setStrategyError] = useState("");
  const [strategiesLoading, setStrategiesLoading] = useState(true);
  const [name, setName] = useState("");
  const [cash, setCash] = useState("1000.00");
  const [sourceMode, setSourceMode] = useState<Mode>("synthetic_fixture");
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [createError, setCreateError] = useState("");
  const lifetime = useRef<AbortController | null>(null);
  const listRequest = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    lifetime.current = controller;
    void (async () => {
      try {
        const result = await createApiClient(window.location.origin).GET(
          "/api/v1/strategies",
          { params: { query: { limit: 100 } }, signal: controller.signal },
        );
        if (controller.signal.aborted) return;
        if (!result.data) throw new Error("Strategy registry unavailable");
        setStrategies(result.data.items);
        setStrategyCursor(result.data.next_cursor);
        setStrategyId(
          result.data.items.find(
            (row) => row.template_key === "risk_adjusted_momentum_v1",
          )?.id ??
            result.data.items[0]?.id ??
            "",
        );
      } catch {
        if (!controller.signal.aborted)
          setStrategyError(
            "Published strategy versions are unavailable. Reload this page before creating an account.",
          );
      } finally {
        if (!controller.signal.aborted) setStrategiesLoading(false);
      }
    })();
    return () => controller.abort();
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    listRequest.current = controller;
    void (async () => {
      setLoading(true);
      setMoreLoading(false);
      setError("");
      setAccounts([]);
      setCursor(null);
      try {
        const result = await createApiClient(window.location.origin).GET(
          "/api/v1/portfolios",
          {
            params: { query: { limit: 25, ...(mode ? { mode } : {}) } },
            signal: controller.signal,
          },
        );
        if (controller.signal.aborted) return;
        if (!result.data) throw new Error("Accounts unavailable");
        setAccounts(result.data.items);
        setCursor(result.data.next_cursor);
      } catch {
        if (!controller.signal.aborted)
          setError(
            "Paper accounts are unavailable. Check local storage or reconciliation, then reload.",
          );
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    })();
    return () => controller.abort();
  }, [mode, epoch]);
  async function moreAccounts() {
    if (!cursor || moreLoading) return;
    const signal = listRequest.current?.signal;
    setMoreLoading(true);
    setError("");
    try {
      const result = await createApiClient(window.location.origin).GET(
        "/api/v1/portfolios",
        {
          params: { query: { limit: 25, cursor, ...(mode ? { mode } : {}) } },
          signal,
        },
      );
      if (signal?.aborted) return;
      if (!result.data) throw new Error("Page unavailable");
      setAccounts((old) => [
        ...new Map(
          [...old, ...result.data!.items].map((row) => [row.id, row]),
        ).values(),
      ]);
      setCursor(result.data.next_cursor);
    } catch {
      if (!signal?.aborted)
        setError(
          "The next account page is unavailable. Current results are a partial list.",
        );
    } finally {
      if (!signal?.aborted) setMoreLoading(false);
    }
  }
  async function moreStrategies() {
    if (!strategyCursor || strategiesLoading) return;
    const signal = lifetime.current?.signal;
    setStrategiesLoading(true);
    setStrategyError("");
    try {
      const result = await createApiClient(window.location.origin).GET(
        "/api/v1/strategies",
        { params: { query: { limit: 100, cursor: strategyCursor } }, signal },
      );
      if (signal?.aborted) return;
      if (!result.data) throw new Error("Versions unavailable");
      setStrategies((old) => [
        ...new Map(
          [...old, ...result.data!.items].map((row) => [row.id, row]),
        ).values(),
      ]);
      setStrategyCursor(result.data.next_cursor);
    } catch {
      if (!signal?.aborted)
        setStrategyError(
          "More published strategies are unavailable. Existing choices are retained.",
        );
    } finally {
      if (!signal?.aborted) setStrategiesLoading(false);
    }
  }
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const selected = strategies.find((row) => row.id === strategyId);
    if (!attempt && !selected) return;
    const request: Attempt = attempt ?? {
      key: crypto.randomUUID(),
      body: {
        name,
        opening_cash_usd: cash,
        strategy_version_id: selected!.published_version.id,
        mode: sourceMode,
        snapshot_id: null,
      },
    };
    setAttempt(request);
    setBusy(true);
    setUncertain(false);
    setCreateError("");
    const signal = lifetime.current?.signal;
    try {
      const result = await createApiClient(window.location.origin).POST(
        "/api/v1/portfolios",
        {
          body: request.body,
          params: { header: { "Idempotency-Key": request.key } },
          signal,
        },
      );
      if (signal?.aborted) return;
      if (result.data) {
        router.push(`/portfolios/${result.data.id}`);
        return;
      }
      if (result.response.status >= 500) {
        setUncertain(true);
        setCreateError(
          "Creation outcome is unconfirmed. Retry to recover the original account. Your account details are kept for the retry.",
        );
      } else {
        setAttempt(null);
        setCreateError(
          result.response.status === 422
            ? "Check the account name, positive starting capital (at most two decimal places), and published version."
            : "The version, source or request conflicts with stored state. Reload accounts and check your selection before trying again.",
        );
      }
    } catch {
      if (!signal?.aborted) {
        setUncertain(true);
        setCreateError(
          "Connection lost before confirmation. Retry to recover this account using the original inputs.",
        );
      }
    } finally {
      if (!signal?.aborted) setBusy(false);
    }
  }
  const frozen = busy || uncertain;
  return (
    <div className="portfolio-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">YOUR SYNTHETIC CAPITAL</p>
          <h1>Paper portfolios</h1>
          <p>
            Independent accounts, posted holdings and an inspectable ledger.
          </p>
        </div>
        <span className="paper-badge">Paper only</span>
      </div>
      <Card title="Create a cash account">
        <p>
          Start with synthetic USD cash. Creating an account does not buy any
          securities.
        </p>
        {strategyError && (
          <p role="alert" className="notice notice-error">
            {strategyError}
          </p>
        )}
        <form
          className="portfolio-form"
          onSubmit={(event) => void create(event)}
        >
          <label htmlFor="portfolio-name">
            Account name
            <input
              id="portfolio-name"
              required
              maxLength={120}
              value={name}
              onChange={(event) => setName(event.target.value)}
              disabled={frozen}
              autoComplete="off"
            />
          </label>
          <label htmlFor="portfolio-cash">
            Starting capital (USD)
            <input
              id="portfolio-cash"
              type="text"
              inputMode="decimal"
              required
              pattern="[0-9]+(\.[0-9]{1,2})?"
              value={cash}
              onChange={(event) => setCash(event.target.value)}
              disabled={frozen}
            />
          </label>
          <label htmlFor="portfolio-strategy">
            Published strategy version
            <select
              id="portfolio-strategy"
              required
              value={strategyId}
              onChange={(event) => setStrategyId(event.target.value)}
              disabled={frozen || strategiesLoading || !strategies.length}
            >
              <option value="">
                {strategiesLoading
                  ? "Loading published versions…"
                  : "Choose a published version"}
              </option>
              {strategies.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.name} · v{row.published_version.version}
                </option>
              ))}
            </select>
          </label>
          <label htmlFor="portfolio-source">
            Account data source
            <select
              id="portfolio-source"
              value={sourceMode}
              onChange={(event) => setSourceMode(event.target.value as Mode)}
              disabled={frozen}
            >
              <option value="synthetic_fixture">
                Synthetic demo · offline fixtures
              </option>
              <option value="research_market_data">Market research data</option>
            </select>
          </label>
          <p className="portfolio-form-note">
            The selected version and source mode stay bound to this account.
            Market research accounts can hold synthetic cash; current real feeds
            do not support paper execution.
          </p>
          {createError && (
            <p role="alert" className="notice notice-error portfolio-form-note">
              {createError}
            </p>
          )}
          <div className="portfolio-actions">
            <Button type="submit" disabled={busy || (!attempt && !strategyId)}>
              {busy
                ? "Creating account…"
                : uncertain
                  ? "Retry same account creation"
                  : "Create paper account"}
            </Button>
            {strategyCursor && (
              <Button
                type="button"
                variant="outline"
                onClick={() => void moreStrategies()}
                disabled={frozen || strategiesLoading}
              >
                Load more strategies
              </Button>
            )}
          </div>
        </form>
      </Card>
      <Card title="Your accounts">
        <div className="portfolio-actions">
          <label className="field-label" htmlFor="portfolio-filter">
            Source filter
            <select
              id="portfolio-filter"
              value={mode}
              onChange={(event) => setMode(event.target.value as Mode | "")}
            >
              <option value="">All sources</option>
              <option value="synthetic_fixture">Synthetic demo</option>
              <option value="research_market_data">Market research data</option>
            </select>
          </label>
          <Button
            variant="outline"
            onClick={() => setEpoch((value) => value + 1)}
            disabled={loading}
          >
            Reload accounts
          </Button>
        </div>
        {loading && <p role="status">Loading paper accounts…</p>}
        {error && (
          <p role="alert" className="notice notice-error">
            {error}
          </p>
        )}
        {!loading && !error && !accounts.length && (
          <EmptyState
            title={
              mode ? "No accounts for this source" : "No paper accounts yet"
            }
          >
            Create an independent cash account above. No balances are assumed
            before the backend confirms it.
          </EmptyState>
        )}
        <div className="portfolio-account-list">
          {accounts.map((row) => (
            <article key={row.id} className="portfolio-account-summary">
              <h3>
                <Link href={`/portfolios/${row.id}`}>{row.name}</Link>
              </h3>
              <DataProvenanceBadge
                mode={row.valuation_mode}
                asOf={row.valuation_as_of_session}
                freshness={
                  row.valuation_mode === "synthetic_fixture"
                    ? "fixture"
                    : row.valuation.status === "stale"
                      ? "stale"
                      : "unavailable"
                }
              />
              <p>
                Value <Money value={row.total_value_usd} /> · Posted cash{" "}
                <Money value={row.cash_usd} />
              </p>
              <p>
                {row.state} · {row.holdings.length} posted holdings · Revision{" "}
                {row.revision}
              </p>
              {row.valuation.status !== "available" && (
                <p>
                  Valuation {row.valuation.status}:{" "}
                  {row.valuation.reason?.replaceAll("_", " ")}
                </p>
              )}
            </article>
          ))}
        </div>
        {cursor && (
          <Button
            variant="outline"
            onClick={() => void moreAccounts()}
            disabled={moreLoading}
          >
            {moreLoading ? "Loading accounts…" : "Load more accounts"}
          </Button>
        )}
      </Card>
    </div>
  );
}
