"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { createApiClient } from "../../api/generated/client";
import type { components } from "../../api/generated/schema";
import { UUID_PATTERN } from "../../lib/validation";
import {
  Card,
  DataProvenanceBadge,
  Money,
  Quantity,
  ReturnPercent,
  WarningsPanel,
} from "../evidence";
import { Button } from "../ui/button";
import { HoldingsTable } from "./HoldingsTable";

type S = components["schemas"];
export function PortfolioDetail({ id }: { id: string }) {
  const [account, setAccount] = useState<S["PaperPortfolioV1"] | null>(null);
  const [transactions, setTransactions] = useState<
    S["PortfolioTransactionV1"][]
  >([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [moreLoading, setMoreLoading] = useState(false);
  const [error, setError] = useState("");
  const [moreError, setMoreError] = useState("");
  const [epoch, setEpoch] = useState(0);
  const lifetime = useRef<AbortController | null>(null);
  const valid = UUID_PATTERN.test(id);
  useEffect(() => {
    const controller = new AbortController();
    lifetime.current = controller;
    void (async () => {
      if (!valid) {
        setLoading(false);
        setError("This account identifier is invalid.");
        return;
      }
      setLoading(true);
      setMoreLoading(false);
      setError("");
      setMoreError("");
      setAccount(null);
      setTransactions([]);
      try {
        const api = createApiClient(window.location.origin);
        const [detail, history] = await Promise.all([
          api.GET("/api/v1/portfolios/{portfolio_id}", {
            params: { path: { portfolio_id: id } },
            signal: controller.signal,
          }),
          api.GET("/api/v1/portfolios/{portfolio_id}/transactions", {
            params: { path: { portfolio_id: id }, query: { limit: 25 } },
            signal: controller.signal,
          }),
        ]);
        if (controller.signal.aborted) return;
        if (!detail.data || !history.data) {
          setError(
            detail.response.status === 404
              ? "Paper account not found."
              : "Posted state or history is unavailable. A reconciliation or local-service problem may require attention. No new fill is implied.",
          );
          return;
        }
        setAccount(detail.data);
        setTransactions(history.data.items);
        setCursor(history.data.next_cursor);
      } catch {
        if (!controller.signal.aborted)
          setError(
            "The account could not be loaded. Check the local services, then retry.",
          );
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    })();
    return () => controller.abort();
  }, [id, valid, epoch]);
  async function more() {
    if (!cursor || moreLoading) return;
    const signal = lifetime.current?.signal;
    setMoreLoading(true);
    setMoreError("");
    try {
      const result = await createApiClient(window.location.origin).GET(
        "/api/v1/portfolios/{portfolio_id}/transactions",
        {
          params: { path: { portfolio_id: id }, query: { limit: 25, cursor } },
          signal,
        },
      );
      if (signal?.aborted) return;
      if (!result.data) throw new Error("Unavailable history");
      setTransactions((old) => [
        ...new Map(
          [...old, ...result.data!.items].map((row) => [row.id, row]),
        ).values(),
      ]);
      setCursor(result.data.next_cursor);
    } catch {
      if (!signal?.aborted)
        setMoreError(
          "More history is unavailable. The displayed rows are only a partial page.",
        );
    } finally {
      if (!signal?.aborted) setMoreLoading(false);
    }
  }
  return (
    <div className="portfolio-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">POSTED STATE, NOT A PREVIEW</p>
          <h1>{account?.name ?? "Paper account"}</h1>
          <p>Independent synthetic capital · Paper only</p>
        </div>
        <Button
          onClick={() => setEpoch((value) => value + 1)}
          disabled={loading}
        >
          Refresh posted state
        </Button>
      </div>
      <Link href="/portfolios">← All paper accounts</Link>
      {loading && <p role="status">Loading posted account and ledger…</p>}
      {error && (
        <p role="alert" className="notice notice-error">
          {error}
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
                : account.valuation.status === "stale"
                  ? "stale"
                  : account.valuation.status === "available" &&
                      account.valuation.as_of_session
                    ? "current"
                    : "unavailable"
            }
          />
          <WarningsPanel warnings={account.valuation.warnings} />
          {account.valuation.status !== "available" && (
            <p role="status" className="notice notice-warning">
              <strong>Valuation {account.valuation.status}</strong> ·{" "}
              {account.valuation.reason?.replaceAll("_", " ")}
              <br />
              Cash and posted quantities remain visible; a missing mark never
              becomes zero.
            </p>
          )}
          {account.valuation.reason === "ZERO_PORTFOLIO_VALUE" && (
            <p className="notice">
              The known total value is zero; percentage weights are undefined.
            </p>
          )}
          {account.reconciliation_failed && (
            <p role="alert" className="notice notice-error">
              Ledger reconciliation failed. New financial work is blocked.
            </p>
          )}
          <div className="portfolio-metrics">
            <Card title="Account value">
              <p className="portfolio-number">
                <Money value={account.total_value_usd} />
              </p>
              <p>
                {account.valuation_as_of_session
                  ? `Marks: ${account.valuation_as_of_session}`
                  : "No market-price session"}
              </p>
            </Card>
            <Card title="Posted cash">
              <p className="portfolio-number">
                <Money value={account.cash_usd} />
              </p>
              <p>
                Cash weight{" "}
                <ReturnPercent value={account.valuation.cash_weight} />
              </p>
            </Card>
            <Card title="Account state">
              <p className="portfolio-number">{account.state}</p>
              <p>
                Revision {account.revision} · Ledger sequence{" "}
                {account.last_sequence}
              </p>
              <p>
                {account.reconciliation_failed
                  ? "Reconciliation blocked"
                  : "No reconciliation failure reported"}
              </p>
            </Card>
          </div>
          <Card title="Strategy and assumptions">
            <p>
              Bound immutable version:{" "}
              <code>{account.strategy_version_id}</code>
            </p>
            <p>
              <Link href="/lab/strategies">Inspect the strategy registry</Link>
            </p>
            <p>
              Benchmark {account.benchmark_symbol} · Policy{" "}
              <code>{account.execution_policy_id}</code>
            </p>
            <p>
              Position cap{" "}
              <ReturnPercent value={account.risk_policy.max_position_weight} />{" "}
              · Minimum trade{" "}
              <Money value={account.risk_policy.min_trade_usd} />
            </p>
          </Card>
          <Card title="Posted holdings">
            <HoldingsTable holdings={account.holdings} />
          </Card>
          <Card title="Order lifecycle">
            <p>
              Inspect live pending orders, original decisions, and explicit
              paper controls in the{" "}
              <Link href={`/portfolios/${id}/decisions`}>
                Decision Center →
              </Link>
              . Posted holdings and ledger events remain below.
            </p>
          </Card>
          <Card title="Immutable transaction history">
            <p>
              Cash movements, fees and position changes below are posted backend
              records. Approval events do not change holdings.
            </p>
            {transactions[0]?.sequence !== account.last_sequence && (
              <p role="status" className="notice">
                Account and history were read at different times. Refresh for
                aligned evidence.
              </p>
            )}
            <div className="portfolio-ledger">
              {transactions.map((row) => (
                <article key={row.id} className="portfolio-event">
                  <div>
                    <h3>{row.kind.replaceAll("_", " ")}</h3>
                    <p>
                      Sequence {row.sequence} · Revision{" "}
                      {row.portfolio_revision} · {row.recorded_at}
                    </p>
                  </div>
                  <p>
                    Cash delta <Money value={row.cash_delta_usd} />
                  </p>
                  {row.position_changes.map((change) => (
                    <p key={change.asset_id}>
                      <code>{change.asset_id}</code> · Shares{" "}
                      <Quantity value={change.quantity_delta} /> · Basis delta{" "}
                      <Money value={change.total_basis_delta_usd} />
                    </p>
                  ))}
                  {row.fill && (
                    <>
                      <p>
                        Filled <Quantity value={row.fill.quantity} /> shares ·{" "}
                        {row.fill.execution_session}
                      </p>
                      <p>
                        Raw price <code>{row.fill.raw_price_usd} USD</code> ·
                        Executed <code>{row.fill.executed_price_usd} USD</code>
                      </p>
                      <p>
                        Gross <Money value={row.fill.gross_usd} /> · Commission{" "}
                        <Money value={row.fill.commission_usd} /> · Slippage{" "}
                        <Money value={row.fill.slippage_usd} />
                      </p>
                      <p>
                        Removed basis{" "}
                        <Money value={row.fill.removed_basis_usd} /> · Realized
                        P/L <Money value={row.fill.realized_pnl_usd} />
                      </p>
                    </>
                  )}
                  <details>
                    <summary>Inspect event lineage</summary>
                    <p>
                      Event <code>{row.id}</code>
                    </p>
                    <p>Execution/effective time {row.effective_at}</p>
                    <p>
                      Snapshot{" "}
                      <code>
                        {row.snapshot_id ?? "No market source required"}
                      </code>
                    </p>
                    <p>
                      Strategy version <code>{row.strategy_version_id}</code>
                    </p>
                    <p>
                      Event key <code>{row.event_key}</code>
                    </p>
                    {row.correction_target_id && (
                      <p>
                        Correction of <code>{row.correction_target_id}</code>
                      </p>
                    )}
                  </details>
                </article>
              ))}
            </div>
            {moreError && (
              <p role="alert" className="notice notice-error">
                {moreError}
              </p>
            )}
            {cursor && (
              <Button
                variant="outline"
                disabled={moreLoading}
                onClick={() => void more()}
              >
                {moreLoading ? "Loading history…" : "Load older transactions"}
              </Button>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
