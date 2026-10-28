"""ADR-013/Q12 statistics over posted net NAV; never changes cash or positions."""

import math
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation, localcontext
from fractions import Fraction

from pydantic import TypeAdapter

from backend.backtesting.runner import BacktestCoreResult
from backend.domain.experiment import ExperimentMetrics, MetricValue
from backend.domain.types import Contract, Money, Reason
from backend.portfolio.execution import ExecutionResult, money

SESSIONS_PER_YEAR = 252


class TradeCost(Contract):
    gross_usd: Money
    fees_usd: Money
    slippage_usd: Money


class PeriodMetrics(Contract):
    daily_nav_observations: int
    return_observations: int
    metrics: ExperimentMetrics


class MetricsPeriods(Contract):
    total: PeriodMetrics
    development: PeriodMetrics
    holdout: PeriodMetrics


def unavailable(reason: Reason) -> MetricValue:
    return MetricValue(value=None, unavailable_reason=reason)


def statistic(value: Fraction | Decimal | int) -> MetricValue:
    try:
        finite = float(value)
    except (OverflowError, ValueError):
        return unavailable("NUMERICAL_RANGE")
    if not math.isfinite(finite):
        return unavailable("NUMERICAL_RANGE")
    return MetricValue(value=finite, unavailable_reason=None)


def _decimal(value: Fraction) -> Decimal:
    return Decimal(value.numerator) / Decimal(value.denominator)


def _money(value: Fraction) -> str:
    with localcontext() as context:
        context.prec = 80
        return money(_decimal(value))


def calculate_metrics(
    nav_usd: Sequence[str],
    *,
    trades: Sequence[TradeCost] = (),
    previous_nav_usd: str | None = None,
) -> ExperimentMetrics:
    """Owned daily closes determine turnover; an optional prior close supplies returns only."""
    validated = TypeAdapter(tuple[Money, ...]).validate_python(tuple(nav_usd))
    owned = tuple(Fraction(value) for value in validated)
    if previous_nav_usd is not None:
        previous = TypeAdapter(Money).validate_python(previous_nav_usd)
        curve = (Fraction(previous), *owned)
    else:
        curve = owned
    gross = sum((Fraction(row.gross_usd) for row in trades), Fraction())
    fees = sum((Fraction(row.fees_usd) for row in trades), Fraction())
    slippage = sum((Fraction(row.slippage_usd) for row in trades), Fraction())
    mean_nav = sum(owned, Fraction()) / len(owned) if owned else Fraction()
    turnover = (
        statistic(gross / mean_nav)
        if mean_nav > 0
        else unavailable("ZERO_MEAN_NAV" if owned else "NO_OBSERVATIONS")
    )
    reason = "NO_OBSERVATIONS" if not owned else "INSUFFICIENT_RETURN_HISTORY"
    cumulative = annualized = volatility = sharpe = drawdown = unavailable(reason)
    n = len(curve) - 1
    if owned and n > 0:
        if curve[0] <= 0:
            cumulative = annualized = drawdown = unavailable("ZERO_START_NAV")
        else:
            cumulative = statistic(curve[-1] / curve[0] - 1)
            with localcontext() as context:
                context.prec = 80
                try:
                    annualized = statistic(
                        _decimal(curve[-1] / curve[0]) ** (Decimal(SESSIONS_PER_YEAR) / n) - 1
                    )
                except (InvalidOperation, OverflowError):
                    annualized = unavailable("NUMERICAL_RANGE")
            peak = curve[0]
            largest = Fraction()
            for value in curve:
                peak = max(peak, value)
                largest = max(largest, 1 - value / peak)
            drawdown = statistic(largest)
        if any(value == 0 for value in curve[:-1]):
            volatility = sharpe = unavailable("ZERO_RETURN_DENOMINATOR")
        elif n >= 2:
            returns = tuple(
                current / previous - 1 for previous, current in zip(curve, curve[1:], strict=False)
            )
            with localcontext() as context:
                context.prec = 80
                observed = tuple(_decimal(value) for value in returns)
                mean = sum(observed, Decimal()) / n
                # Statistics use bounded-precision Decimal; exact-rational sums
                # over thousands of unrelated return denominators grow needlessly.
                variance = (
                    Decimal(0)
                    if all(value == returns[0] for value in returns)
                    else sum(((value - mean) ** 2 for value in observed), Decimal()) / (n - 1)
                )
                std = variance.sqrt()
                annual_scale = Decimal(SESSIONS_PER_YEAR).sqrt()
                volatility = statistic(std * annual_scale)
                sharpe = (
                    statistic(mean / std * annual_scale)
                    if variance > 0
                    else unavailable("ZERO_VARIANCE")
                )
    return ExperimentMetrics(
        cumulative_return_fraction=cumulative,
        annualized_return_fraction=annualized,
        annualized_volatility_fraction=volatility,
        max_drawdown_fraction=drawdown,
        turnover_fraction=turnover,
        sharpe_ratio=sharpe,
        slippage_usd=_money(slippage),
        fees_usd=_money(fees),
        trade_count=len(trades),
    )


def _costs(executions: Sequence[ExecutionResult]) -> tuple[TradeCost, ...]:
    return tuple(
        TradeCost(
            gross_usd=row.fill.gross_usd,
            fees_usd=row.fill.commission_usd,
            slippage_usd=row.fill.slippage_usd,
        )
        for row in executions
        if row.fill is not None
    )


def metrics_periods(
    core: BacktestCoreResult, nav_usd: Sequence[str] | None = None, *, include_trades: bool = True
) -> MetricsPeriods:
    """Same observed state across the split; holdout includes its first adjacent return."""
    values = tuple(nav_usd) if nav_usd is not None else tuple(row.nav_usd for row in core.points)
    if len(values) != len(core.points):
        raise ValueError("Metric periods require the exact core session sequence")
    results = {}
    for period in ("total", "development", "holdout"):
        indices = [
            i for i, point in enumerate(core.points) if period == "total" or point.phase == period
        ]
        owned = tuple(values[i] for i in indices)
        dates = {core.points[i].session_date for i in indices}
        previous = (
            values[indices[0] - 1] if period == "holdout" and indices and indices[0] > 0 else None
        )
        trades = (
            _costs(
                tuple(
                    row
                    for row in core.executions
                    if row.fill is not None and row.fill.execution_session in dates
                )
            )
            if include_trades
            else ()
        )
        results[period] = PeriodMetrics(
            daily_nav_observations=len(owned),
            return_observations=max(0, len(owned) - (previous is None)),
            metrics=calculate_metrics(owned, trades=trades, previous_nav_usd=previous),
        )
    return MetricsPeriods(**results)
