"""ADR-011 low-volatility measurement; policy and execution remain shared."""

from collections.abc import Sequence
from typing import Annotated, Literal

from pydantic import Field

from backend.domain.strategy import LowVolatilitySignalConfig
from backend.domain.types import Contract, FiniteNumber
from backend.strategies.features import sample_log_volatility


class LowVolatilityFeatures(Contract):
    kind: Literal["low_volatility"]
    volatility: Annotated[FiniteNumber, Field(ge=0)]


class LowVolatilityScore(Contract):
    kind: Literal["low_volatility"]
    volatility_z: FiniteNumber
    score: FiniteNumber


def measure(closes: Sequence[str], signals: LowVolatilitySignalConfig) -> LowVolatilityFeatures:
    return LowVolatilityFeatures(
        kind="low_volatility", volatility=sample_log_volatility(closes, signals.volatility_sessions)
    )
