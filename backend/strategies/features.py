"""Numerical helpers; callers must supply contiguous as-of calendar windows."""

import math
from collections.abc import Sequence
from decimal import Decimal, localcontext


def prices(values: Sequence[str]) -> tuple[Decimal, ...]:
    result = tuple(Decimal(value) for value in values)
    if not result or any(not value.is_finite() or value <= 0 for value in result):
        raise ValueError("Prices must be positive finite decimals")
    return result


def window_momentum(values: Sequence[str], sessions: int) -> float:
    if type(sessions) is not int or sessions < 1 or len(values) < sessions + 1:
        raise ValueError("Insufficient momentum history")
    first, last = prices((values[-sessions - 1], values[-1]))
    with localcontext() as context:
        context.prec = max(len(value) for value in values) + 28
        change = (last - first) / first
        result = float(change)
    if not math.isfinite(result) or (change != 0 and result == 0):
        raise ValueError("Momentum is outside numerical resolution")
    return result


def sample_log_volatility(values: Sequence[str], returns: int = 60) -> float:
    if type(returns) is not int or returns < 2 or len(values) < returns + 1:
        raise ValueError("Insufficient volatility history")
    window = prices(values[-returns - 1 :])
    logs = []
    with localcontext() as context:
        context.prec = max(len(value) for value in values) + 28
        for previous, current in zip(window[:-1], window[1:], strict=True):
            relative = (current - previous) / previous
            # Decimal ln avoids a float ratio rounding a small nonzero return to 1.
            value = float((current / previous).ln())
            if not math.isfinite(value) or (relative != 0 and value == 0):
                raise ValueError("Return is outside numerical resolution")
            logs.append(value)
    mean = math.fsum(value / returns for value in logs)
    deviations = [value - mean for value in logs]
    result = math.hypot(*deviations) / math.sqrt(returns - 1) * math.sqrt(252)
    if not math.isfinite(result) or (any(deviations) and result == 0):
        raise ValueError("Volatility is outside numerical resolution")
    return result


def population_zscores(values: Sequence[float]) -> tuple[float, ...]:
    if any(not math.isfinite(value) for value in values):
        raise ValueError("Nonfinite cross-section")
    if not values:
        return ()
    scale = max(abs(value) for value in values)
    if scale == 0:
        return (0.0,) * len(values)
    scaled = [value / scale for value in values]
    mean = math.fsum(value / len(values) for value in scaled)
    centered = [value - mean for value in scaled]
    dispersion = math.hypot(*centered) / math.sqrt(len(values))
    if dispersion == 0:
        if len(set(values)) != 1:
            raise ValueError("Dispersion is outside numerical resolution")
        return (0.0,) * len(values)
    return tuple(value / dispersion for value in centered)
