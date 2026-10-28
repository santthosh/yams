"""ADR-011 mean-reversion measurements; no independent eligibility or risk policy."""

import math
from collections.abc import Sequence
from decimal import Decimal, localcontext
from typing import Annotated, Literal

from pydantic import Field

from backend.domain.strategy import MeanReversionSignalConfig
from backend.domain.types import Contract, FiniteNumber, Price, decimal_text
from backend.strategies.features import prices, sample_log_volatility


class MeanReversionFeatures(Contract):
    kind: Literal["mean_reversion"]
    mean_reversion_distance: FiniteNumber
    mean_reversion_sma: Price
    volatility: Annotated[FiniteNumber, Field(ge=0)]


class MeanReversionScore(Contract):
    kind: Literal["mean_reversion"]
    mean_reversion_z: FiniteNumber
    score: FiniteNumber


def measure(closes: Sequence[str], signals: MeanReversionSignalConfig) -> MeanReversionFeatures:
    window = signals.mean_reversion_sessions
    if len(closes) < window:
        raise ValueError("Insufficient mean-reversion history")
    observed = prices(closes[-window:])
    with localcontext() as context:
        context.prec = max(len(value) for value in closes) + 28
        average = sum(observed, Decimal(0)) / window
        distance = (average - observed[-1]) / average
        value = float(distance)
        if not math.isfinite(value) or (distance != 0 and value == 0):
            raise ValueError("Mean reversion is outside numerical resolution")
    return MeanReversionFeatures(
        kind="mean_reversion",
        mean_reversion_distance=value,
        mean_reversion_sma=decimal_text(average),
        volatility=sample_log_volatility(closes, signals.volatility_sessions),
    )
