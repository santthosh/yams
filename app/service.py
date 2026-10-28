"""Application services: portfolio valuation, recommendation building, applying trades, backtest cache."""

from __future__ import annotations

import threading
import uuid
from decimal import Decimal

import pandas as pd

from app import engine, explain
from app.backtest import BacktestResult, run_backtest
from app.config import FORECAST, STRATEGY
from app.data import MarketData
from app.forecast import run_forecast
from app.ledger import Conflict, Ledger, now

_bt_cache: dict[tuple, BacktestResult] = {}
_bt_lock = threading.Lock()


class AppError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def sectors(md: MarketData) -> dict[str, str | None]:
    return {t: md.sector(t) for t in md.universe.index}


def get_backtest(md: MarketData, initial_cash: float) -> BacktestResult:
    key = (md.fetched_at, round(initial_cash, 2))
    with _bt_lock:
        if key not in _bt_cache:
            _bt_cache.clear()
            _bt_cache[key] = run_backtest(md.close, md.open, md.volume, sectors(md), md.members, initial_cash)
        return _bt_cache[key]


def portfolio_view(md: MarketData, ledger: Ledger, quotes: dict | None = None) -> dict:
    """Valued at the latest daily close; `live` adds an intraday view when quotes newer than that close exist."""
    p = ledger.portfolio()
    holdings, cash = ledger.state()
    reasons = {}
    last = ledger.latest_applied()
    if last:
        reasons = {pos["ticker"]: pos["explanation"] for pos in last["positions"]}
    rows, total, unavailable = [], float(cash), []
    for t, q in sorted(holdings.items()):
        px = md.latest_close(t)
        if px is None:
            unavailable.append(t)
        value = float(q) * px if px is not None else None
        total += value or 0.0
        rows.append({"ticker": t, "name": md.name(t), "sector": md.sector(t) or "—", "qty": float(q),
                     "price": px, "value": value, "reason": reasons.get(t, "")})
    for r in rows:
        r["weight"] = r["value"] / total if r["value"] is not None and total > 0 else None
    rows.sort(key=lambda r: -(r["value"] or 0))
    initial = float(p["initial_cash"])
    spy_now = md.latest_close(STRATEGY.benchmark)
    spy_ret = spy_now / p["spy_start_price"] - 1 if spy_now else None
    return {
        "initial_cash": initial,
        "created_at": p["created_at"],
        "start_as_of": p["start_as_of"],
        "cash": float(cash),
        "cash_weight": float(cash) / total if total > 0 else None,
        "holdings": rows,
        "total": None if unavailable else total,
        "unavailable": unavailable,
        "pnl": None if unavailable else total - initial,
        "return": None if unavailable else total / initial - 1,
        "spy_return": spy_ret,
        "valued_as_of": md.as_of,
        "live": _live_view(md, holdings, cash, initial, p["spy_start_price"], quotes or {}),
    }


def _live_view(md: MarketData, holdings, cash, initial: float, spy_start: float, quotes: dict) -> dict:
    """Value the portfolio at intraday quotes. Display only: recommendations always use daily closes."""
    as_of_date = pd.Timestamp(md.as_of).date()
    newer = {t: q for t, q in quotes.items() if q[1].date() > as_of_date}  # same-day quotes add nothing
    needed = [*holdings, STRATEGY.benchmark]
    if not quotes:
        return {"status": "unavailable", "message": "Live prices unavailable; showing closing prices."}
    if any(t not in newer for t in needed):
        return {"status": "closed", "message": f"No trading since the {md.as_of} close; showing closing prices."}
    prices, total, prev_total = {}, float(cash), float(cash)
    for t, q in holdings.items():
        px, prev = newer[t][0], md.latest_close(t)
        prices[t] = {"price": px, "value": float(q) * px, "change": px / prev - 1 if prev else None}
        total += float(q) * px
        prev_total += float(q) * (prev or px)
    for v in prices.values():
        v["weight"] = v["value"] / total if total > 0 else None
    spy_px = newer[STRATEGY.benchmark][0]
    spy_prev = md.latest_close(STRATEGY.benchmark)
    return {
        "status": "live",
        "time": min(newer[t][1] for t in needed).strftime("%b %d, %I:%M %p ET"),
        "prices": prices,
        "total": total,
        "cash_weight": float(cash) / total if total > 0 else None,
        "pnl": total - initial,
        "return": total / initial - 1,
        "day_change": total - prev_total,
        "day_return": total / prev_total - 1 if prev_total > 0 else None,
        "spy_return": spy_px / spy_start - 1 if spy_start else None,
        "spy_day_return": spy_px / spy_prev - 1 if spy_prev else None,
    }


def build_recommendation(md: MarketData, ledger: Ledger) -> dict:
    holdings, cash = ledger.state()
    trade_count = ledger.trade_count()
    sec = sectors(md)
    ev = engine.evaluate(md.close, md.volume, sec, md.members)
    tickers = set(holdings) | set(ev.targets)
    prices = {t: md.latest_close(t) for t in tickers}
    missing = [t for t, p in prices.items() if p is None]
    if missing:
        raise AppError("NO_PRICE", f"No price available for {', '.join(missing)}; refresh data.", 409)
    orders = engine.plan_orders(holdings, cash, prices, ev.targets)
    value = float(cash) + sum(float(q) * prices[t] for t, q in holdings.items())
    current_w = {t: float(q) * prices[t] / value for t, q in holdings.items()} if value > 0 else {}
    # Post-trade weights: traded names move to target, HOLDs keep their current weight.
    post_w = {o.ticker: (o.current_weight if o.side == "HOLD" else o.target_weight) for o in orders}
    post_w = {t: w for t, w in post_w.items() if w > 0}
    est_cost = sum(o.est_cost for o in orders)
    fc = run_forecast(md.close, current_w, post_w, value, est_cost)

    cand = ev.candidates
    eligible = ev.eligible
    members = set(md.members)
    selected = cand.loc[list(ev.targets)] if ev.targets else cand.iloc[0:0]
    median_vol = float(selected["vol60"].median()) if len(selected) else 0.0
    positions = []
    for t, w in sorted(ev.targets.items(), key=lambda kv: -kv[1]):
        row = cand.loc[t]
        positions.append({
            "ticker": t, "name": md.name(t), "sector": row["sector"], "weight": w,
            "rank": int(row["rank"]), "score": float(row["score"]), "m126": float(row["m126"]),
            "m63": float(row["m63"]), "vol60": float(row["vol60"]), "price": prices[t],
            "capped": ev.capped.get(t),
            "explanation": explain.position(t, md.name(t), row, len(eligible), w, ev.uncapped_weights.get(t),
                                            ev.capped.get(t), median_vol),
        })
    actions = []
    for o in sorted(orders, key=lambda o: ["SELL", "REDUCE", "BUY", "INCREASE", "HOLD"].index(o.action)):
        row = cand.loc[o.ticker] if o.ticker in cand.index else None
        actions.append({
            "ticker": o.ticker, "name": md.name(o.ticker), "action": o.action, "side": o.side,
            "current_weight": o.current_weight, "target_weight": o.target_weight,
            "current_qty": str(o.current_qty), "qty": str(o.qty), "price": o.price, "notional": o.notional,
            "est_cost": o.est_cost, "reasons": o.reasons,
            "explanation": explain.action(o, md.name(o.ticker), row, members),
        })
    runners = eligible[eligible["selection"] != "SELECTED"].head(5)
    runners_up = [{"ticker": t, "name": md.name(t), "sector": r["sector"], "rank": int(r["rank"]),
                   "why": explain.why_not(r, members, t)} for t, r in runners.iterrows()]
    excluded = {k: int(v) for k, v in cand[~cand["eligible"]]["reason"].value_counts().items()}
    sector_w: dict[str, float] = {}
    for p in positions:
        sector_w[p["sector"]] = sector_w.get(p["sector"], 0.0) + p["weight"]

    counts = {a: sum(1 for x in actions if x["action"] == a) for a in ("BUY", "INCREASE", "REDUCE", "SELL", "HOLD")}
    if not ev.targets:
        summary_action = "MOVE_TO_CASH"
    elif all(a["side"] == "HOLD" for a in actions):
        summary_action = "HOLD"
    else:
        summary_action = "REBALANCE"
    parts = [f"{n} {k.lower()}" for k, n in counts.items() if n]
    summary = {"MOVE_TO_CASH": "Move to cash: no stock passed the filters.",
               "HOLD": "Hold: no change is large enough to be worth trading.",
               "REBALANCE": "Rebalance: " + ", ".join(parts) + "."}[summary_action]

    bt = get_backtest(md, float(ledger.portfolio()["initial_cash"]))
    step = max(1, len(bt.dates) // 150)
    rec = {
        "id": str(uuid.uuid4()),
        "created_at": now(),
        "data_as_of": md.as_of,
        "data_fetched_at": md.fetched_at,
        "data_source": md.source,
        "trade_count": trade_count,
        "summary_action": summary_action,
        "summary": summary,
        "regime": ev.regime,
        "regime_text": explain.regime(ev.regime, ev.spy_close, ev.spy_sma),
        "portfolio_value": value,
        "cash": float(cash),
        "positions": positions,
        "cash_target_weight": ev.cash_weight,
        "sector_weights": dict(sorted(sector_w.items(), key=lambda kv: -kv[1])),
        "actions": actions,
        "est_total_cost": est_cost,
        "forecast": fc,
        "backtest": {
            "verdict": explain.verdict(bt), "metrics": bt.metrics, "start": bt.start, "end": bt.end,
            "dates": bt.dates[::step], "equity": bt.equity[::step], "benchmark": bt.benchmark[::step],
        },
        "runners_up": runners_up,
        "excluded": excluded,
        "n_universe": len(cand),
        "n_eligible": len(eligible),
    }
    ledger.save_recommendation(rec)
    return {**rec, "status": "ready"}


def apply_recommendation(md: MarketData, ledger: Ledger, rec_id: str) -> list[engine.Fill]:
    rec = ledger.get_recommendation(rec_id)
    if rec is None:
        raise AppError("NOT_FOUND", "Recommendation not found.", 404)
    holdings, cash = ledger.state()
    orders = [
        engine.Order(a["ticker"], a["action"], a["side"], a["current_weight"], a["target_weight"],
                     Decimal(a["current_qty"]), Decimal(a["qty"]), a["price"], a["notional"], a["est_cost"],
                     a["reasons"])
        for a in rec["actions"]
    ]
    fill_prices = {a["ticker"]: a["price"] for a in rec["actions"]}  # latest close in the rec's data
    try:
        _, _, fills, _ = engine.execute(orders, holdings, cash, fill_prices)
        ledger.apply(rec_id, fills, md.fetched_at)
    except Conflict as e:
        raise AppError("STATE_CONFLICT", str(e), 409) from e
    return fills


FORECAST_CAPTION = (f"Scenario based on resampling the last year of daily returns over "
                    f"{FORECAST.horizon_calendar_days} calendar days (~{FORECAST.horizon_sessions} trading sessions). "
                    f"Not a prediction.")
