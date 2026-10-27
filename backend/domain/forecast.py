"""ADR-006 forecast outputs, including explicit unavailable comparisons."""

from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, StrictStr, model_validator

from backend.domain.common import ArtifactReference
from backend.domain.types import (
    AssetId,
    Contract,
    FiniteNumber,
    Hash256,
    Money,
    Reason,
    SessionDate,
    SourceMode,
    UTCTimestamp,
)
from backend.domain.types import (
    FractionString as Weight,
)


class ForecastOutcome(Contract):
    median_return_fraction: Annotated[FiniteNumber, Field(ge=-1)]
    p10_return_fraction: Annotated[FiniteNumber, Field(ge=-1)]
    p90_return_fraction: Annotated[FiniteNumber, Field(ge=-1)]
    probability_of_loss: Annotated[FiniteNumber, Field(ge=0, le=1)]
    median_ending_value_usd: Money

    @model_validator(mode="after")
    def ordered_quantiles(self) -> Self:
        if not self.p10_return_fraction <= self.median_return_fraction <= self.p90_return_fraction:
            raise ValueError("Scenario quantiles must be ordered")
        return self


class ForecastWeight(Contract):
    asset_id: AssetId
    weight: Weight


class ForecastAllocation(Contract):
    weights: tuple[ForecastWeight, ...]
    cash_weight: Weight
    upfront_cost_usd: Money | None

    @model_validator(mode="after")
    def complete_weights(self) -> Self:
        if len({item.asset_id for item in self.weights}) != len(self.weights):
            raise ValueError("Duplicate forecast asset")
        total = sum((Decimal(item.weight) for item in self.weights), Decimal(self.cash_weight))
        if abs(total - 1) > Decimal("0.00000001"):
            raise ValueError("Forecast allocation must sum to one")
        return self


class RNGMetadata(Contract):
    generator: Literal["PCG64"]
    numpy_version: StrictStr
    sampling_version: Literal["noncircular_c_order_v1"]
    # Full state is an immutable hashed artifact, avoiding lossy JS 128-bit integers.
    initial_state: ArtifactReference | None


class ForecastV1(Contract):
    id: UUID
    status: Literal["available", "unavailable"]
    unavailable_reason: Reason | None
    as_of_session: SessionDate
    decision_cutoff_utc: UTCTimestamp
    data_status: SourceMode
    snapshot_id: UUID
    snapshot_sha256: Hash256
    calendar_version: Hash256 | None
    horizon_calendar_days: Annotated[int, Field(strict=True, ge=90, le=90)]
    horizon_trading_sessions: Annotated[int, Field(strict=True, ge=0, le=90)] | None
    horizon_end_at: UTCTimestamp | None
    future_sessions: tuple[SessionDate, ...] | None
    method: Literal["multivariate_block_bootstrap_v1"]
    seed: Annotated[int, Field(strict=True, ge=0, le=18446744073709551615)]
    simulation_count: Annotated[int, Field(strict=True, ge=5000, le=5000)]
    lookback_sessions: Annotated[int, Field(strict=True, ge=252, le=252)]
    block_length_sessions: Annotated[int, Field(strict=True, ge=5, le=5)]
    cash_return_fraction: Annotated[FiniteNumber, Field(ge=0, le=0)]
    initial_value_usd: Money | None
    current_allocation: ForecastAllocation
    proposed_allocation: ForecastAllocation
    rng: RNGMetadata
    input_array_sha256: Hash256 | None
    sampled_indices: ArtifactReference | None
    fingerprint: Hash256 | None
    fingerprint_schema_version: Annotated[int, Field(strict=True, ge=1, le=1)]
    engine_version: StrictStr
    proposed: ForecastOutcome | None
    hold_unchanged: ForecastOutcome | None
    median_return_delta_fraction: FiniteNumber | None
    comparability: Literal["common_shock_paths"]
    limitations: tuple[Reason, ...]

    @model_validator(mode="after")
    def available_result(self) -> Self:
        required_limits = {
            "SCENARIO_NOT_CALIBRATED_PREDICTION",
            "ZERO_CASH_YIELD",
            "CONSTANT_WEIGHT_APPROXIMATION",
            "ESTIMATED_UPFRONT_COST",
        }
        if not required_limits <= set(self.limitations):
            raise ValueError("Forecast limitations must disclose every model assumption")
        if self.future_sessions is not None:
            if self.future_sessions != tuple(sorted(set(self.future_sessions))):
                raise ValueError("Future sessions must be unique and chronological")
            if self.horizon_trading_sessions != len(self.future_sessions):
                raise ValueError("Session count must match the pinned horizon")
        if self.status == "unavailable":
            if self.unavailable_reason is None or any(
                item is not None
                for item in (self.proposed, self.hold_unchanged, self.median_return_delta_fraction)
            ):
                raise ValueError("Unavailable forecast requires reason and null outcomes")
            return self
        if self.unavailable_reason is not None or any(
            item is None
            for item in (
                self.proposed,
                self.hold_unchanged,
                self.median_return_delta_fraction,
                self.calendar_version,
                self.horizon_end_at,
                self.future_sessions,
                self.fingerprint,
                self.initial_value_usd,
                self.current_allocation.upfront_cost_usd,
                self.proposed_allocation.upfront_cost_usd,
            )
        ):
            raise ValueError("Available forecast requires complete outcomes and provenance")
        if (
            not self.horizon_trading_sessions
            or self.horizon_end_at is None
            or self.horizon_end_at <= self.decision_cutoff_utc
        ):
            raise ValueError("Available forecast requires a positive future horizon")
        assert self.initial_value_usd is not None
        assert self.current_allocation.upfront_cost_usd is not None
        assert self.proposed_allocation.upfront_cost_usd is not None
        nav = Decimal(self.initial_value_usd)
        if nav <= 0 or Decimal(self.current_allocation.upfront_cost_usd) != 0:
            raise ValueError("Current NAV must be positive and hold cost zero")
        if Decimal(self.proposed_allocation.upfront_cost_usd) >= nav:
            raise ValueError("Proposed cost must leave positive starting value")
        union = {
            item.asset_id
            for allocation in (self.current_allocation, self.proposed_allocation)
            for item in allocation.weights
            if Decimal(item.weight) > 0
        }
        if len(union) > 16:
            raise ValueError("Forecast union exceeds initial resource budget")
        if union and any(
            item is None
            for item in (self.input_array_sha256, self.sampled_indices, self.rng.initial_state)
        ):
            raise ValueError("Asset forecasts require array, sampled-index and RNG evidence")
        assert self.proposed is not None and self.hold_unchanged is not None
        assert self.median_return_delta_fraction is not None
        expected = self.proposed.median_return_fraction - self.hold_unchanged.median_return_fraction
        if abs(self.median_return_delta_fraction - expected) > 1e-12:
            raise ValueError("Comparison delta must equal the difference of scenario medians")
        return self
