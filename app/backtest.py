"""Monthly walk-forward backtest (SPEC §5) using the same engine as live recommendations."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import ROUND_DOWN, Decimal

import numpy as np
import pandas as pd

from app import engine
from app.config import BACKTEST, STRATEGY, StrategyConfig


@dataclass
class BacktestResult:
    start: str
    end: str
    initial_cash: float
    dates: list[str]
    equity: list[float]
    benchmark: list[float]
    metrics: dict[str, dict[str, float]]  # {"strategy": {...}, "benchmark": {...}}
    rebalances: int
    trades: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def metrics(equity: pd.Series) -> dict[str, float]:
    ret = equity.pct_change().dropna()
    n = len(ret)
    total = equity.iloc[-1] / equity.iloc[0] - 1
    sd = ret.std(ddof=1) if n > 1 else float("nan")
    return {
        "total_return": float(total),
        "cagr": float((1 + total) ** (252 / n) - 1) if n else float("nan"),
        "volatility": float(sd * math.sqrt(252)),
        "sharpe": float(ret.mean() / sd * math.sqrt(252)) if sd and sd > 0 else float("nan"),
        "max_drawdown": float((equity / equity.cummax() - 1).min()),
        "ending_value": float(equity.iloc[-1]),
    }


def decision_indices(index: pd.DatetimeIndex, start_i: int) -> list[int]:
    """First session of the window, then the last session of every month (excluding the final bar)."""
    out = [start_i]
    for i in range(start_i + 1, len(index) - 1):
        if index[i].month != index[i + 1].month:
            out.append(i)
    return out


def run_backtest(
    close: pd.DataFrame,
    open_: pd.DataFrame,
    volume: pd.DataFrame,
    sectors: dict[str, str | None],
    members: list[str],
    initial_cash: float = 1000.0,
    cfg: StrategyConfig = STRATEGY,
    years: int = BACKTEST.years,
) -> BacktestResult:
    idx = close.index
    warmup = cfg.min_history_sessions + 1
    warnings = ["SURVIVORSHIP_BIAS: universe is today's S&P 500 membership applied to the past"]
    start_i = int(idx.searchsorted(idx[-1] - pd.DateOffset(years=years)))
    if start_i < warmup:
        start_i = warmup
        warnings.append("LIMITED_HISTORY: backtest window shortened to keep a 1-year feature warmup")
    if start_i >= len(idx) - 2:
        raise ValueError("Not enough history to backtest")

    mark = close.ffill()
    decisions = set(decision_indices(idx, start_i))
    slip = Decimal(repr(cfg.slippage_bps)) / Decimal(10_000)
    holdings: dict[str, Decimal] = {}
    cash = Decimal(repr(initial_cash)).quantize(engine.CENT)
    pending: list[engine.Order] | None = None
    equity, trades, turnovers = [], [], []

    bench = cfg.benchmark
    b_open = Decimal(repr(float(open_[bench].iloc[start_i + 1]))) * (1 + slip)
    b_qty = (cash / b_open).quantize(engine.SHARE, rounding=ROUND_DOWN)
    b_cash = float(cash - (b_qty * b_open).quantize(engine.CENT))
    benchmark = [initial_cash]

    for i in range(start_i, len(idx)):
        if pending is not None:
            row = open_.iloc[i]
            fill_px = {o.ticker: float(row[o.ticker]) for o in pending if o.side != "HOLD"}
            value_before = float(cash) + sum(float(q) * mark.iat[i - 1, close.columns.get_loc(t)]
                                            for t, q in holdings.items())
            holdings, cash, fills, _skipped = engine.execute(pending, holdings, cash, fill_px, cfg)
            traded = sum(abs(float(f.cash_delta)) for f in fills)
            if value_before > 0:
                turnovers.append(traded / 2 / value_before)
            for f in fills:
                trades.append({"date": idx[i].strftime("%Y-%m-%d"), "ticker": f.ticker, "side": f.side,
                               "qty": float(f.qty), "price": float(f.price), "cost": float(f.cost)})
            pending = None
        row_close = mark.iloc[i]
        value = float(cash) + sum(float(q) * float(row_close[t]) for t, q in holdings.items())
        if i > start_i:
            equity.append(value)
            benchmark.append(b_cash + float(b_qty) * float(row_close[bench]))
        else:
            equity.append(float(initial_cash))
        if i in decisions:
            ev = engine.evaluate(close.iloc[: i + 1], volume.iloc[: i + 1], sectors, members, cfg)
            prices = {t: float(row_close[t]) for t in set(holdings) | set(ev.targets)}
            pending = engine.plan_orders(holdings, cash, prices, ev.targets, cfg)

    dates = [d.strftime("%Y-%m-%d") for d in idx[start_i:]]
    eq = pd.Series(equity, index=idx[start_i:])
    bm = pd.Series(benchmark, index=idx[start_i:])
    m_s, m_b = metrics(eq), metrics(bm)
    m_s["trades"] = len(trades)
    m_s["costs"] = float(sum(t["cost"] for t in trades))
    m_s["avg_turnover"] = float(np.mean(turnovers)) if turnovers else 0.0
    m_b["trades"], m_b["costs"], m_b["avg_turnover"] = 1, float(initial_cash) * cfg.slippage_bps / 10_000, 0.0
    return BacktestResult(
        start=dates[0], end=dates[-1], initial_cash=initial_cash, dates=dates,
        equity=[round(x, 2) for x in equity], benchmark=[round(x, 2) for x in benchmark],
        metrics={"strategy": m_s, "benchmark": m_b}, rebalances=len(decisions), trades=trades, warnings=warnings,
    )
