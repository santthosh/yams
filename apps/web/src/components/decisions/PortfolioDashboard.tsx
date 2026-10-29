"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { createApiClient } from "../../api/generated/client";
import type { components } from "../../api/generated/schema";
import { Card, DataProvenanceBadge, Money } from "../evidence";
import { Button } from "../ui/button";
type S = components["schemas"];
export function PortfolioDashboard() {
  const [accounts, setAccounts] = useState<S["PaperPortfolioV1"][]>([]);
  const [schedules, setSchedules] = useState<
    Record<string, S["PortfolioScheduleV1"]>
  >({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [more, setMore] = useState(false);
  const [epoch, setEpoch] = useState(0);
  useEffect(() => {
    const c = new AbortController();
    void (async () => {
      setLoading(true);
      setError("");
      try {
        const api = createApiClient(window.location.origin);
        const r = await api.GET("/api/v1/portfolios", {
          params: { query: { limit: 25 } },
          signal: c.signal,
        });
        if (c.signal.aborted) return;
        if (!r.data) throw new Error();
        setAccounts(r.data.items);
        setMore(!!r.data.next_cursor);
        const results = await Promise.all(
          r.data.items.map(async (a) => {
            try {
              const s = await api.GET(
                "/api/v1/portfolios/{portfolio_id}/schedule",
                { params: { path: { portfolio_id: a.id } }, signal: c.signal },
              );
              return s.data ? ([a.id, s.data] as const) : null;
            } catch {
              return null;
            }
          }),
        );
        if (!c.signal.aborted)
          setSchedules(Object.fromEntries(results.filter((r) => r !== null)));
      } catch {
        if (!c.signal.aborted)
          setError(
            "Paper account state is unavailable. Refresh local services; no balance or action is assumed.",
          );
      } finally {
        if (!c.signal.aborted) setLoading(false);
      }
    })();
    return () => c.abort();
  }, [epoch]);
  return (
    <Card title="Paper accounts and next actions">
      <div className="portfolio-actions">
        <Link href="/portfolios">Create or browse paper accounts →</Link>
        <Button
          variant="outline"
          disabled={loading}
          onClick={() => setEpoch((v) => v + 1)}
        >
          Refresh accounts and reviews
        </Button>
      </div>
      {loading && (
        <p role="status">Loading posted accounts and review status…</p>
      )}
      {error && (
        <p role="alert" className="notice notice-error">
          {error}
        </p>
      )}
      {!loading && !error && !accounts.length && (
        <p>
          No paper accounts yet.{" "}
          <Link href="/settings/data">Load offline fixture data</Link>, then{" "}
          <Link href="/portfolios">create a synthetic cash account</Link>. No
          capital or recommendations are assumed before confirmation.
        </p>
      )}
      <div className="portfolio-account-list">
        {accounts.map((a) => {
          const s = schedules[a.id];
          return (
            <article className="portfolio-account-summary" key={a.id}>
              <h3>
                <Link href={`/portfolios/${a.id}`}>{a.name}</Link>
              </h3>
              <DataProvenanceBadge
                mode={a.valuation_mode}
                asOf={a.valuation_as_of_session}
                freshness={
                  a.valuation_mode === "synthetic_fixture"
                    ? "fixture"
                    : a.valuation.status === "stale"
                      ? "stale"
                      : "unavailable"
                }
              />
              <p>
                Posted cash <Money value={a.cash_usd} /> · Value{" "}
                <Money value={a.total_value_usd} /> · {a.holdings.length} posted
                holdings
              </p>
              <p>
                {a.state} · Revision {a.revision}
                {a.reconciliation_failed ? " · Reconciliation blocked" : ""}
              </p>
              {a.valuation.status !== "available" && (
                <p>
                  Valuation {a.valuation.status}: {a.valuation.reason}
                </p>
              )}
              <p>
                Next review {s?.next_review_session ?? "Unknown"} · Due{" "}
                {s?.next_review_due_at ?? "Unknown"}
              </p>
              <p>
                {s?.active_order_batch_id
                  ? "Approved paper orders remain pending; inspect the batch before another approval."
                  : s
                    ? "No active paper batch reported."
                    : "Schedule and pending-batch status unavailable."}
              </p>
              <p>
                Backlog{" "}
                {s?.due_backlog == null
                  ? "Unknown"
                  : s.due_backlog
                    ? "Due work remains"
                    : "No due work reported"}{" "}
                · Supervisor {s?.supervisor.status ?? "Unavailable"}
              </p>
              <Link href={`/portfolios/${a.id}/decisions`}>
                {s?.active_order_batch_id
                  ? "Inspect pending orders and decisions"
                  : "Review target and scenarios"}{" "}
                →
              </Link>
            </article>
          );
        })}
      </div>
      {more && (
        <p>
          Showing the first 25 accounts.{" "}
          <Link href="/portfolios">Browse all account pages</Link>.
        </p>
      )}
    </Card>
  );
}
