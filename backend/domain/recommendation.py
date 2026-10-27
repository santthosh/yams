"""Recommendation evidence and complete allocation transport."""

from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, StrictStr, model_validator

from backend.domain.types import (
    AssetId,
    Contract,
    FiniteNumber,
    Hash256,
    Money,
    Quantity,
    Reason,
    SessionDate,
    SourceMode,
    UTCTimestamp,
)
from backend.domain.types import (
    FractionString as Weight,
)


class TargetWeight(Contract):
    asset_id: AssetId
    weight: Weight
    reason_codes: Annotated[tuple[Reason, ...], Field(min_length=1)]


class FeatureValue(Contract):
    name: StrictStr
    value: FiniteNumber | None
    unavailable_reason: Reason | None

    @model_validator(mode="after")
    def unavailable(self) -> Self:
        if (self.value is None) != (self.unavailable_reason is not None):
            raise ValueError("Missing feature value requires exactly one unavailable reason")
        return self


class CandidateEvidence(Contract):
    asset_id: AssetId
    features: tuple[FeatureValue, ...]
    score: FiniteNumber | None
    exclusion_reasons: tuple[Reason, ...]
    contributions: tuple[FeatureValue, ...]

    @model_validator(mode="after")
    def score_availability(self) -> Self:
        if self.score is None and not self.exclusion_reasons:
            raise ValueError("Missing score requires an exclusion reason")
        return self


class ActionEvidence(Contract):
    position_cap: Weight | None
    current_weight: Weight


class RecommendedAction(Contract):
    asset_id: AssetId
    side: Literal["BUY", "SELL", "HOLD"]
    label: Literal["INCREASE", "REDUCE", "HOLD"]
    current_weight: Weight
    target_weight: Weight
    estimated_notional_usd: Money
    estimated_quantity: Quantity
    reason_codes: Annotated[tuple[Reason, ...], Field(min_length=1)]
    evidence: ActionEvidence
    explanation: StrictStr

    @model_validator(mode="after")
    def action_consistency(self) -> Self:
        expected = {"BUY": "INCREASE", "SELL": "REDUCE", "HOLD": "HOLD"}
        if self.label != expected[self.side]:
            raise ValueError("Action label must agree with side")
        if self.side == "HOLD" and (
            Decimal(self.estimated_quantity) != 0 or Decimal(self.estimated_notional_usd) != 0
        ):
            raise ValueError("HOLD has zero quantity and notional")
        if self.side != "HOLD" and Decimal(self.estimated_quantity) <= 0:
            raise ValueError("BUY/SELL requires positive estimated quantity")
        return self


class RecommendationV1(Contract):
    id: UUID
    portfolio_id: UUID
    portfolio_revision: Annotated[int, Field(strict=True, ge=0)]
    strategy_version_id: UUID
    snapshot_id: UUID
    snapshot_sha256: Hash256
    as_of_session: SessionDate
    decision_cutoff_utc: UTCTimestamp
    data_status: SourceMode
    summary_action: Literal["BUY", "SELL", "HOLD", "REBALANCE", "ALLOCATE_TO_CASH"]
    target_weights: tuple[TargetWeight, ...]
    cash_target_weight: Weight
    actions: tuple[RecommendedAction, ...]
    candidates: tuple[CandidateEvidence, ...]
    estimated_total_trade_cost_usd: Money
    forecast_id: UUID
    engine_version: StrictStr
    created_at: UTCTimestamp
    status: Literal["ready", "applied", "dismissed", "expired"]

    @model_validator(mode="after")
    def complete_allocation(self) -> Self:
        ids = [target.asset_id for target in self.target_weights]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate target asset")
        total = sum((Decimal(target.weight) for target in self.target_weights), Decimal(0))
        if abs(total + Decimal(self.cash_target_weight) - 1) > Decimal("0.00000001"):
            raise ValueError("Complete target allocation including cash must sum to one")
        if self.created_at < self.decision_cutoff_utc:
            raise ValueError("Recommendation cannot precede its evidence cutoff")
        if self.summary_action == "ALLOCATE_TO_CASH" and total != 0:
            raise ValueError("Cash-only action cannot retain asset targets")
        return self
