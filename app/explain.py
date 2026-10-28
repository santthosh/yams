"""Plain-English explanations built only from computed numbers (SPEC §7). No LLM."""

from __future__ import annotations

from app.config import STRATEGY
from app.engine import REASONS


def pct(x: float, signed: bool = False) -> str:
    return f"{x:+.0%}" if signed else f"{x:.0%}"


def position(t: str, name: str, row, n_eligible: int, weight: float, uncapped: float | None,
             capped: str | None, median_vol: float) -> str:
    s = (f"{name} ({row['sector']}) is {'up' if row['m126'] >= 0 else 'down'} {abs(row['m126']):.0%} over 6 months "
         f"and {'up' if row['m63'] >= 0 else 'down'} {abs(row['m63']):.0%} over 3 months, ranking "
         f"#{int(row['rank'])} of {n_eligible} eligible stocks.")
    vol = row["vol60"]
    if vol > median_vol * 1.1:
        s += (f" Its price swings ({vol:.0%} a year) are larger than the typical pick ({median_vol:.0%}), "
              f"so it gets a smaller share.")
    elif vol < median_vol * 0.9:
        s += (f" Its price swings ({vol:.0%} a year) are calmer than the typical pick ({median_vol:.0%}), "
              f"so it gets a larger share.")
    else:
        s += f" Its price swings ({vol:.0%} a year) are about typical for the picks."
    if capped == "position" and uncapped:
        s += (f" It would have received {uncapped:.1%}, but no single stock may exceed "
              f"{STRATEGY.max_position_weight:.0%}.")
    elif capped == "sector":
        s += f" Its sector hit the {STRATEGY.max_sector_weight:.0%} limit, so its weight was trimmed."
    return s + f" Target weight: {weight:.1%}."


def why_not(row, members: set[str], t: str) -> str:
    """Why a ticker is not (or no longer) in the target portfolio."""
    if row is None or t not in members:
        return "it is no longer in the S&P 500 universe the strategy draws from"
    if row["reason"] == "BELOW_TREND":
        return "its price fell below its 200-day average, so the trend filter removed it"
    if row["reason"]:
        return REASONS[row["reason"]].lower()
    if row.get("selection") == "SECTOR_FULL":
        return (f"it ranks #{int(row['rank'])}, but its sector ({row['sector']}) already has "
                f"{int(STRATEGY.max_positions * STRATEGY.max_sector_weight)} higher-ranked picks")
    return f"it now ranks #{int(row['rank'])}; only the top {STRATEGY.max_positions} are held"


def action(o, name: str, row, members: set[str]) -> str:
    qty = f"{float(o.qty):.4f}".rstrip("0").rstrip(".")
    if o.action == "BUY":
        return f"Buy about {qty} shares (${o.notional:,.2f}) to open a new {o.target_weight:.1%} position."
    if o.action == "INCREASE":
        return (f"Add ${o.notional:,.2f} ({qty} shares) to bring it from {o.current_weight:.1%} "
                f"to its {o.target_weight:.1%} target.")
    if o.action == "REDUCE":
        if "OVER_CAP" in o.reasons:
            return (f"Trim ${o.notional:,.2f}: at {o.current_weight:.1%} it exceeds the "
                    f"{STRATEGY.max_position_weight:.0%} single-stock limit.")
        return (f"Trim ${o.notional:,.2f} ({qty} shares): it has grown to {o.current_weight:.1%} "
                f"against a {o.target_weight:.1%} target.")
    if o.action == "SELL":
        return f"Sell all {qty} shares (${o.notional:,.2f}): {why_not(row, members, o.ticker)}."
    # HOLD
    if o.current_qty == 0:
        return (f"Not bought yet: its {o.target_weight:.1%} target is below the "
                f"{STRATEGY.rebalance_band * 100:.0f}-point minimum change worth trading.")
    diff = abs(o.target_weight - o.current_weight) * 100
    if "TOO_SMALL" in o.reasons:
        return f"Keep as is: the change would be under ${STRATEGY.min_trade_usd:.0f}."
    return (f"Keep as is: the target ({o.target_weight:.1%}) differs by only {diff:.1f} points, "
            f"so trading would cost more than it fixes.")


def regime(r: str, spy: float, sma: float) -> str:
    if r == "risk_off":
        return (f"The overall market (SPY ${spy:,.2f}) is below its 200-day average (${sma:,.2f}), so at least "
                f"{STRATEGY.risk_off_cash_weight:.0%} of the portfolio is held in cash.")
    return (f"The overall market (SPY ${spy:,.2f}) is above its 200-day average (${sma:,.2f}), so the strategy "
            f"invests up to {1 - STRATEGY.min_cash_weight:.0%} and keeps {STRATEGY.min_cash_weight:.0%} in cash.")


def verdict(bt) -> str:
    s, b = bt.metrics["strategy"], bt.metrics["benchmark"]
    made = "made money" if s["total_return"] > 0 else "lost money"
    beat = "beating" if s["ending_value"] > b["ending_value"] else "trailing"
    return (f"Backtest {bt.start} → {bt.end}: these exact rules would have turned ${bt.initial_cash:,.0f} into "
            f"${s['ending_value']:,.0f} ({made}, {beat} SPY's ${b['ending_value']:,.0f}), with a worst drop of "
            f"{s['max_drawdown']:.0%} (SPY: {b['max_drawdown']:.0%}). Past results on today's S&P 500 list "
            f"(survivorship-biased); not a guarantee.")
