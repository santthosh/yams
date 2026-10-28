"""Decision engine (SPEC §4): eligibility → features → score → capped weights → orders → fills.

Pure functions, no I/O. The live recommendation and the backtest both call `evaluate`,
`plan_orders` and `execute`, so there is exactly one implementation of the decision logic.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, Decimal

import numpy as np
import pandas as pd

from app.config import STRATEGY, StrategyConfig

CENT = Decimal("0.01")
SHARE = Decimal("0.000001")
PRICE = Decimal("0.0001")

# Exclusion reason codes, in the order they are checked.
REASONS = {
    "SHORT_HISTORY": "Less than a year of clean daily prices",
    "BAD_DATA": "Missing or invalid price data",
    "NO_SECTOR": "No sector classification",
    "LOW_PRICE": "Share price under $5",
    "ILLIQUID": "Trades less than $10M per day",
    "BELOW_TREND": "Price is below its 200-day average (downtrend)",
}


@dataclass
class Evaluation:
    as_of: str
    regime: str  # "risk_on" | "risk_off"
    spy_close: float
    spy_sma: float
    candidates: pd.DataFrame  # every universe ticker: features, z-scores, score, rank, eligible, reason
    targets: dict[str, float]  # ticker -> weight (cash excluded)
    cash_weight: float
    uncapped_weights: dict[str, float]  # inverse-vol weights before caps (for explanations)
    capped: dict[str, str] = field(default_factory=dict)  # ticker -> "position" | "sector"

    @property
    def eligible(self) -> pd.DataFrame:
        return self.candidates[self.candidates["eligible"]].sort_values("rank")


# ---------------------------------------------------------------- scoring


def _zscore(s: pd.Series) -> pd.Series:
    sd = s.std(ddof=0)
    if not np.isfinite(sd) or sd == 0:
        return pd.Series(0.0, index=s.index)
    return (s - s.mean()) / sd


def compute_candidates(
    close: pd.DataFrame, volume: pd.DataFrame, sectors: dict[str, str | None], members: list[str], cfg: StrategyConfig
) -> pd.DataFrame:
    """Features and eligibility as of the last row of `close` (only data <= T is ever passed in)."""
    window = cfg.min_history_sessions + 1
    c = close[members].tail(window)
    v = volume[members].tail(window)
    last = c.iloc[-1]
    full_history = c.notna().all() & (len(c) >= window)
    mlong, mshort = cfg.momentum_long_sessions, cfg.momentum_short_sessions
    df = pd.DataFrame(index=pd.Index(members, name="ticker"))
    df["sector"] = [sectors.get(t) for t in members]
    df["price"] = last
    df["m126"] = last / c.iloc[-1 - mlong] - 1 if len(c) > mlong else np.nan
    df["m63"] = last / c.iloc[-1 - mshort] - 1 if len(c) > mshort else np.nan
    logret = np.log(c / c.shift(1)).tail(cfg.volatility_sessions)
    df["vol60"] = logret.std(ddof=1) * math.sqrt(252)
    df["sma200"] = c.tail(cfg.trend_sma_sessions).mean()
    df["dollar_volume"] = (c * v).tail(cfg.liquidity_window).median()

    reason = pd.Series("", index=df.index, dtype=object)
    finite = np.isfinite(df[["price", "m126", "m63", "vol60", "sma200", "dollar_volume"]]).all(axis=1)
    checks = [
        ("SHORT_HISTORY", ~full_history),
        ("BAD_DATA", ~finite | (df["vol60"] <= 0)),
        ("NO_SECTOR", df["sector"].isna() | (df["sector"] == "")),
        ("LOW_PRICE", df["price"] < cfg.min_price_usd),
        ("ILLIQUID", df["dollar_volume"] < cfg.min_median_dollar_volume_usd),
        ("BELOW_TREND", df["price"] <= df["sma200"]),
    ]
    for code, mask in checks:
        reason[(reason == "") & mask.fillna(True)] = code
    df["reason"] = reason
    df["eligible"] = reason == ""

    el = df["eligible"]
    for col in ("z_m126", "z_m63", "z_vol60", "score"):
        df[col] = np.nan
    if el.any():
        df.loc[el, "z_m126"] = _zscore(df.loc[el, "m126"])
        df.loc[el, "z_m63"] = _zscore(df.loc[el, "m63"])
        df.loc[el, "z_vol60"] = _zscore(df.loc[el, "vol60"])
        df.loc[el, "score"] = (
            cfg.w_mom_long * df.loc[el, "z_m126"]
            + cfg.w_mom_short * df.loc[el, "z_m63"]
            - cfg.w_vol_penalty * df.loc[el, "z_vol60"]
        )
    ranked = df[el].reset_index().sort_values(["score", "ticker"], ascending=[False, True])
    df["rank"] = pd.Series(range(1, len(ranked) + 1), index=ranked["ticker"].values).reindex(df.index)
    return df


# ---------------------------------------------------------------- allocation


def allocate(
    raw: dict[str, float], sectors: dict[str, str], budget: float, pos_cap: float, sec_cap: float
) -> tuple[dict[str, float], dict[str, str]]:
    """Distribute `budget` proportional to `raw`, respecting position and sector caps.

    Iterative water-fill: capped names are frozen and their excess is redistributed among the
    remaining names; whatever cannot be placed stays in cash. Deterministic (sorted iteration).
    """
    w = {t: 0.0 for t in sorted(raw)}
    active = set(w)
    capped: dict[str, str] = {}
    eps = 1e-12
    for _ in range(4 * len(w) + 4):
        remaining = budget - sum(w.values())
        if remaining <= eps or not active:
            break
        total = sum(raw[t] for t in active)
        for t in sorted(active):
            w[t] += remaining * raw[t] / total
        clipped = False
        for s in sorted({sectors[t] for t in active}):
            members = [t for t in w if sectors[t] == s]
            ssum = sum(w[t] for t in members)
            if ssum > sec_cap + eps:
                act = [t for t in members if t in active]
                act_sum = sum(w[t] for t in act)
                room = max(sec_cap - (ssum - act_sum), 0.0)
                for t in act:
                    w[t] = w[t] * room / act_sum
                    active.discard(t)
                    capped[t] = "sector"
                clipped = True
        for t in sorted(w):
            if w[t] > pos_cap + eps:
                w[t] = pos_cap
                active.discard(t)
                capped[t] = "position"
                clipped = True
        if not clipped:
            break
    return {t: x for t, x in w.items() if x > 0}, capped


def evaluate(
    close: pd.DataFrame,
    volume: pd.DataFrame,
    sectors: dict[str, str | None],
    members: list[str],
    cfg: StrategyConfig = STRATEGY,
) -> Evaluation:
    """Full strategy decision as of the last session in `close`."""
    as_of = close.index[-1]
    cand = compute_candidates(close, volume, sectors, members, cfg)
    spy = close[cfg.benchmark].dropna()
    spy_close = float(spy.iloc[-1])
    spy_sma = float(spy.tail(cfg.trend_sma_sessions).mean())
    regime = "risk_off" if spy_close < spy_sma else "risk_on"
    cash_floor = cfg.risk_off_cash_weight if regime == "risk_off" else cfg.min_cash_weight

    # Walk down the ranking; skip a name if its sector already holds the most names the
    # sector cap can fund (8 positions × 40% = 3 per sector), so the budget can actually be deployed.
    per_sector = max(1, math.floor(cfg.max_positions * cfg.max_sector_weight + 1e-9))
    chosen: list[str] = []
    count: dict[str, int] = {}
    cand["selection"] = ""
    for t in cand[cand["eligible"]].sort_values("rank").index:
        if len(chosen) >= cfg.max_positions:
            cand.at[t, "selection"] = "OUTRANKED"
            continue
        s = cand.at[t, "sector"]
        if count.get(s, 0) >= per_sector:
            cand.at[t, "selection"] = "SECTOR_FULL"
            continue
        chosen.append(t)
        count[s] = count.get(s, 0) + 1
        cand.at[t, "selection"] = "SELECTED"
    top = cand.loc[chosen]
    raw = {t: 1.0 / float(top.at[t, "vol60"]) for t in top.index}
    budget = 1.0 - cash_floor
    total_raw = sum(raw.values())
    uncapped = {t: budget * r / total_raw for t, r in raw.items()} if raw else {}
    targets, capped = allocate(
        raw, {t: top.at[t, "sector"] for t in top.index}, budget, cfg.max_position_weight, cfg.max_sector_weight
    )
    return Evaluation(
        as_of=as_of.strftime("%Y-%m-%d"),
        regime=regime,
        spy_close=spy_close,
        spy_sma=spy_sma,
        candidates=cand,
        targets=targets,
        cash_weight=1.0 - sum(targets.values()),
        uncapped_weights=uncapped,
        capped=capped,
    )


# ---------------------------------------------------------------- orders & fills


@dataclass
class Order:
    ticker: str
    action: str  # BUY | INCREASE | REDUCE | SELL | HOLD
    side: str  # BUY | SELL | HOLD
    current_weight: float
    target_weight: float
    current_qty: Decimal
    qty: Decimal  # shares to trade (0 for HOLD)
    price: float  # decision price used for estimates
    notional: float
    est_cost: float
    reasons: list[str]


def _d(x: float, q: Decimal) -> Decimal:
    return Decimal(repr(float(x))).quantize(q, rounding=ROUND_HALF_EVEN)


def plan_orders(
    holdings: dict[str, Decimal],
    cash: Decimal,
    prices: dict[str, float],
    targets: dict[str, float],
    cfg: StrategyConfig = STRATEGY,
) -> list[Order]:
    """Turn target weights into BUY/SELL/HOLD orders for the current holdings (SPEC §4.4, §7)."""
    held = {t: q for t, q in holdings.items() if q > 0}
    value = float(cash) + sum(float(q) * prices[t] for t, q in held.items())
    slip = cfg.slippage_bps / 10_000
    orders = []
    for t in sorted(set(held) | set(targets)):
        p = prices[t]
        cur_q = held.get(t, Decimal(0))
        cur_w = float(cur_q) * p / value if value > 0 else 0.0
        tgt_w = targets.get(t, 0.0)
        delta_usd = (tgt_w - cur_w) * value
        reasons: list[str] = []
        if cur_q > 0 and tgt_w == 0:
            action, qty, reasons = "SELL", cur_q, ["NOT_IN_TARGET"]
        else:
            over_cap = cur_w > cfg.max_position_weight + 1e-9 and tgt_w < cur_w
            if abs(tgt_w - cur_w) < cfg.rebalance_band and not over_cap:
                action, qty, reasons = "HOLD", Decimal(0), ["IN_BAND"]
            elif abs(delta_usd) < cfg.min_trade_usd:
                action, qty, reasons = "HOLD", Decimal(0), ["TOO_SMALL"]
            elif delta_usd > 0:
                action = "BUY" if cur_q == 0 else "INCREASE"
                qty = Decimal(repr(round(delta_usd / p, 9))).quantize(SHARE, rounding=ROUND_DOWN)
                reasons = ["NEW_POSITION"] if cur_q == 0 else ["BELOW_TARGET"]
            else:
                action = "REDUCE"
                qty = min(cur_q, Decimal(repr(round(-delta_usd / p, 9))).quantize(SHARE, rounding=ROUND_HALF_EVEN))
                reasons = ["OVER_CAP"] if over_cap else ["ABOVE_TARGET"]
        if action != "HOLD" and qty <= 0:
            action, qty, reasons = "HOLD", Decimal(0), ["TOO_SMALL"]
        side = "HOLD" if action == "HOLD" else ("SELL" if action in ("SELL", "REDUCE") else "BUY")
        notional = float(qty) * p
        orders.append(Order(t, action, side, cur_w, tgt_w, cur_q, qty, p, notional, notional * slip, reasons))
    return orders


@dataclass
class Fill:
    ticker: str
    side: str
    qty: Decimal
    price: Decimal  # fill price incl. slippage
    cost: Decimal  # slippage paid
    cash_delta: Decimal


def execute(
    orders: list[Order],
    holdings: dict[str, Decimal],
    cash: Decimal,
    fill_prices: dict[str, float],
    cfg: StrategyConfig = STRATEGY,
) -> tuple[dict[str, Decimal], Decimal, list[Fill], list[str]]:
    """Simulate fills: sells first (proceeds fund buys), buys resized to available cash.

    Returns (new holdings, new cash, fills, skipped tickers). Cash never goes negative.
    """
    slip = Decimal(repr(cfg.slippage_bps)) / Decimal(10_000)
    min_trade = Decimal(repr(cfg.min_trade_usd))
    h = dict(holdings)
    fills: list[Fill] = []
    skipped: list[str] = []
    for o in sorted(orders, key=lambda o: (o.side != "SELL", o.ticker)):
        if o.side == "HOLD" or o.qty <= 0:
            continue
        px = fill_prices.get(o.ticker)
        if px is None or not math.isfinite(px) or px <= 0:
            skipped.append(o.ticker)
            continue
        p = _d(px, PRICE)
        if o.side == "SELL":
            qty = min(o.qty, h.get(o.ticker, Decimal(0)))
            if qty <= 0:
                continue
            fp = (p * (1 - slip)).quantize(PRICE, rounding=ROUND_HALF_EVEN)
            gross = (qty * p).quantize(CENT, rounding=ROUND_HALF_EVEN)
            proceeds = (qty * fp).quantize(CENT, rounding=ROUND_HALF_EVEN)
            h[o.ticker] = h.get(o.ticker, Decimal(0)) - qty
            cash += proceeds
            fills.append(Fill(o.ticker, "SELL", qty, fp, gross - proceeds, proceeds))
        else:
            fp = (p * (1 + slip)).quantize(PRICE, rounding=ROUND_HALF_EVEN)
            qty = min(o.qty, (cash / fp).quantize(SHARE, rounding=ROUND_DOWN))
            spend = (qty * fp).quantize(CENT, rounding=ROUND_HALF_EVEN)
            while spend > cash and qty > 0:
                qty -= SHARE
                spend = (qty * fp).quantize(CENT, rounding=ROUND_HALF_EVEN)
            if spend < min_trade:
                skipped.append(o.ticker)
                continue
            gross = (qty * p).quantize(CENT, rounding=ROUND_HALF_EVEN)
            h[o.ticker] = h.get(o.ticker, Decimal(0)) + qty
            cash -= spend
            fills.append(Fill(o.ticker, "BUY", qty, fp, spend - gross, -spend))
    h = {t: q for t, q in h.items() if q > 0}
    assert cash >= 0, "cash went negative"
    return h, cash, fills, skipped
