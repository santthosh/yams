"""Closed StrategyConfigV1 and exact canonical identity from ADR-003."""

import hashlib
import unicodedata
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    BeforeValidator,
    Field,
    PlainSerializer,
    StrictBool,
    WithJsonSchema,
    field_validator,
    model_validator,
)

from backend.domain.types import (
    Contract,
    Money,
    PositiveWeight,
    Weight,
    canonical_json,
    decimal_text,
    load_json,
)


def _config_money(value: str) -> str:
    if Decimal(value) > Decimal("999999999999.99"):
        raise ValueError("Configuration amount exceeds v1 bound")
    return value


ConfigMoney = Annotated[Money, AfterValidator(_config_money)]


def _score_number(value: object) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, int | float | Decimal):
        raise ValueError("Score weight must be a JSON number")
    number = Decimal(str(value))
    if not number.is_finite() or abs(number) > 1:
        raise ValueError("Score weight must be finite and within [-1, 1]")
    if number != number.quantize(Decimal("0.000001")):
        raise ValueError("Score weights support at most six fractional digits")
    return number


ScoreNumber = Annotated[
    Decimal,
    BeforeValidator(_score_number),
    PlainSerializer(float, return_type=float, when_used="json"),
    WithJsonSchema({"type": "number", "minimum": -1, "maximum": 1, "multipleOf": 0.000001}),
]


class UniverseConfig(Contract):
    kind: Literal["liquid_us_equities"]
    min_price_usd: ConfigMoney
    min_median_dollar_volume_usd: ConfigMoney
    min_history_sessions: Annotated[int, Field(strict=True, ge=252, le=2520)]


class ScoreWeights(Contract):
    momentum_long: ScoreNumber
    momentum_short: ScoreNumber
    volatility_penalty: ScoreNumber

    @model_validator(mode="after")
    def valid_weights(self) -> Self:
        if self.momentum_long < 0 or self.momentum_short < 0 or self.volatility_penalty > 0:
            raise ValueError("Momentum weights are positive; volatility is a penalty")
        if self.momentum_long + self.momentum_short - self.volatility_penalty != 1:
            raise ValueError("Absolute score weights must sum to one")
        return self


class SignalConfig(Contract):
    kind: Literal["risk_adjusted_momentum"]
    momentum_long_sessions: Annotated[int, Field(strict=True, ge=1, le=2519)]
    momentum_short_sessions: Annotated[int, Field(strict=True, ge=1, le=2519)]
    volatility_sessions: Annotated[int, Field(strict=True, ge=2, le=2519)]
    trend_sma_sessions: Annotated[int, Field(strict=True, ge=1, le=2520)]
    require_positive_trend: StrictBool
    z_score_weights: ScoreWeights

    @model_validator(mode="after")
    def ordered_lookbacks(self) -> Self:
        if self.momentum_short_sessions >= self.momentum_long_sessions:
            raise ValueError("Short momentum lookback must be less than long")
        return self


class AlternativeSignalConfig(Contract):
    volatility_sessions: Annotated[int, Field(strict=True, ge=2, le=2519)]
    trend_sma_sessions: Annotated[int, Field(strict=True, ge=1, le=2520)]
    require_positive_trend: StrictBool


class MeanReversionSignalConfig(AlternativeSignalConfig):
    kind: Literal["mean_reversion"]
    mean_reversion_sessions: Annotated[int, Field(strict=True, ge=2, le=2520)]


class LowVolatilitySignalConfig(AlternativeSignalConfig):
    kind: Literal["low_volatility"]


StrategySignals = Annotated[
    SignalConfig | MeanReversionSignalConfig | LowVolatilitySignalConfig,
    Field(discriminator="kind"),
]


class PortfolioConfig(Contract):
    max_positions: Annotated[int, Field(strict=True, ge=1, le=100)]
    weighting: Literal["inverse_volatility"]
    max_position_weight: PositiveWeight
    max_sector_weight: PositiveWeight
    min_cash_weight: Weight
    min_trade_usd: ConfigMoney
    rebalance_band_absolute_weight: Weight


class RebalanceConfig(Contract):
    frequency: Literal["monthly"]


class ExecutionPolicy(Contract):
    id: Literal["us_eod_next_open_v1"]


# Python str.strip includes extra control separators; ADR-003 uses Unicode White_Space only.
WHITE_SPACE = (
    "\u0009\u000a\u000b\u000c\u000d\u0020\u0085\u00a0\u1680"
    + "".join(chr(code) for code in range(0x2000, 0x200B))
    + "\u2028\u2029\u202f\u205f\u3000"
)


class StrategyConfigV1(Contract):
    schema_version: Literal[1]
    display_name: Annotated[str, Field(strict=True)]
    universe: UniverseConfig
    signals: StrategySignals
    portfolio: PortfolioConfig
    rebalance: RebalanceConfig
    execution_policy: ExecutionPolicy

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("schema_version must be integer1")
        return value

    @field_validator("display_name")
    @classmethod
    def valid_display_name(cls, value: str) -> str:
        value = value.strip(WHITE_SPACE)
        if not 1 <= len(value) <= 120 or any(
            unicodedata.category(char) in {"Cc", "Cs"} for char in value
        ):
            raise ValueError("Display name must contain 1–120 characters without controls")
        return value

    @model_validator(mode="after")
    def enough_history(self) -> Self:
        signals = self.signals
        windows = [signals.volatility_sessions + 1, signals.trend_sma_sessions, 20]
        if isinstance(signals, SignalConfig):
            windows.extend(
                [signals.momentum_long_sessions + 1, signals.momentum_short_sessions + 1]
            )
        elif isinstance(signals, MeanReversionSignalConfig):
            windows.append(signals.mean_reversion_sessions)
        required = max(windows)
        if self.universe.min_history_sessions < required:
            raise ValueError("History does not cover every required lookback")
        return self

    @classmethod
    def from_json(cls, data: str | bytes) -> Self:
        """Use at raw JSON boundaries to preserve numbers and reject duplicate keys."""
        return cls.model_validate(load_json(data))

    def canonical_bytes(self) -> bytes:
        value = self.model_dump(mode="python")
        for field in ("min_price_usd", "min_median_dollar_volume_usd"):
            value["universe"][field] = decimal_text(Decimal(value["universe"][field]))
        for field in (
            "max_position_weight",
            "max_sector_weight",
            "min_cash_weight",
            "min_trade_usd",
            "rebalance_band_absolute_weight",
        ):
            value["portfolio"][field] = decimal_text(Decimal(value["portfolio"][field]))
        return canonical_json(value)

    def config_hash(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()
