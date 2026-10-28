"""90-day block-bootstrap scenario forecast, proposed vs. hold, on shared paths (SPEC §6)."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from app.config import FORECAST, ForecastConfig


def _summary(terminal: np.ndarray, start_value: float) -> dict:
    p10, p50, p90 = np.percentile(terminal, [10, 50, 90])
    return {
        "median_return": float(p50),
        "p10_return": float(p10),
        "p90_return": float(p90),
        "prob_loss": float((terminal < 0).mean()),
        "median_ending_value": round(start_value * (1 + float(p50)), 2),
        "p10_ending_value": round(start_value * (1 + float(p10)), 2),
        "p90_ending_value": round(start_value * (1 + float(p90)), 2),
    }


def run_forecast(
    close: pd.DataFrame,
    current: dict[str, float],
    proposed: dict[str, float],
    portfolio_value: float,
    trade_cost: float,
    cfg: ForecastConfig = FORECAST,
    benchmark: str | None = "SPY",
) -> dict:
    """Weights exclude cash (cash earns 0). `trade_cost` (USD) is charged up front to the proposed case.

    Drift adjustment: stocks are picked *because* their recent returns were high, so replaying their
    raw history would project that selection bias forward. Each asset's mean daily return is replaced
    with the benchmark's mean over the same window; volatility and co-movement are kept.
    """
    tickers = sorted({t for t, w in {**current, **proposed}.items() if w > 0} | {t for t in current if current[t] > 0})
    base = {
        "horizon_calendar_days": cfg.horizon_calendar_days,
        "horizon_sessions": cfg.horizon_sessions,
        "method": "5-day block bootstrap of the last 252 daily returns (all assets resampled together), "
                  "each stock's average return replaced by SPY's",
        "paths": cfg.paths,
        "seed": cfg.seed,
        "lookback_returns": cfg.lookback_returns,
        "start_value": round(portfolio_value, 2),
        "trade_cost": round(trade_cost, 2),
    }
    if portfolio_value <= 0:
        return {**base, "status": "unavailable", "reason": "Portfolio has no value to project."}
    missing = [t for t in tickers if t not in close.columns]
    window = close[[t for t in tickers if t in close.columns]].tail(cfg.lookback_returns + 1)
    rets = window.pct_change().iloc[1:]
    short = [t for t in tickers if t in rets.columns and rets[t].notna().sum() < cfg.lookback_returns]
    if missing or short or len(rets) < cfg.lookback_returns:
        bad = ", ".join(missing + short)
        return {**base, "status": "unavailable", "reason": f"Less than a year of daily returns for: {bad}."}

    R = rets.to_numpy() if tickers else np.zeros((cfg.lookback_returns, 0))
    if benchmark and benchmark in close.columns and len(R.T):
        bench = close[benchmark].tail(cfg.lookback_returns + 1).pct_change().iloc[1:]
        if bench.notna().all():
            R = R - R.mean(axis=0) + float(bench.mean())
    rng = np.random.default_rng(cfg.seed)
    n_blocks = math.ceil(cfg.horizon_sessions / cfg.block_sessions)
    starts = rng.integers(0, len(R) - cfg.block_sessions + 1, size=(cfg.paths, n_blocks))
    rows = (starts[:, :, None] + np.arange(cfg.block_sessions)).reshape(cfg.paths, -1)[:, : cfg.horizon_sessions]
    paths = R[rows]  # (paths, sessions, assets) — same paths for both portfolios

    def growth(weights: dict[str, float]) -> np.ndarray:
        """(paths, sessions) growth factor of $1; constant weights, cash at 0%."""
        w = np.array([weights.get(t, 0.0) for t in tickers])
        daily = paths @ w if len(w) else np.zeros(paths.shape[:2])
        return np.cumprod(1 + daily, axis=1)

    g_hold = growth(current)
    g_prop = growth(proposed) * (1 - trade_cost / portfolio_value)
    hold, prop = g_hold[:, -1] - 1, g_prop[:, -1] - 1
    s_hold, s_prop = _summary(hold, portfolio_value), _summary(prop, portfolio_value)
    return {
        **base,
        "status": "available",
        "proposed": s_prop,
        "hold": s_hold,
        "delta_median_return": s_prop["median_return"] - s_hold["median_return"],
        "delta_median_value": round(s_prop["median_ending_value"] - s_hold["median_ending_value"], 2),
        "fan": _fan(close.index[-1], g_prop, g_hold, portfolio_value),
    }


FAN_PCTS = (10, 25, 50, 75, 90)


def _fan(as_of: pd.Timestamp, g_prop: np.ndarray, g_hold: np.ndarray, value: float) -> dict:
    """Portfolio-value percentiles for each future session (index 0 = today), for the fan chart.

    Dates are weekdays after `as_of` (exchange holidays ignored), so they are approximate.
    """
    dates = [as_of] + list(pd.bdate_range(as_of + pd.Timedelta(days=1), periods=g_prop.shape[1]))

    def bands(g: np.ndarray) -> dict:
        q = np.percentile(g, FAN_PCTS, axis=0) * value
        return {f"p{p}": [round(value, 2)] + [round(float(v), 2) for v in row] for p, row in zip(FAN_PCTS, q)}

    return {"dates": [d.strftime("%Y-%m-%d") for d in dates], "proposed": bands(g_prop), "hold": bands(g_hold)}
