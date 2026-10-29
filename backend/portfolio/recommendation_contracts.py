"""Closed frozen worker inputs; no public NAV, price, cost or approval overrides."""

from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from backend.domain.evaluation import StrategyEvaluationResultV1
from backend.domain.recommendation import RecommendationV1
from backend.domain.recommendation_api import RecommendationRequest
from backend.domain.strategy import StrategyConfigV1
from backend.domain.types import Contract, Hash256, SourceMode, UTCTimestamp
from backend.forecasting.contracts import ForecastInputs
from backend.portfolio.execution import PortfolioState
from backend.portfolio.planner import OrderPlan

MAX_RECOMMENDATION_BYTES = 8 * 1024 * 1024


class RecommendationPayload(Contract):
    schema_version: Literal[1] = 1
    recommendation_id: UUID
    forecast_id: UUID
    portfolio_id: UUID
    portfolio_revision: Annotated[int, Field(strict=True, ge=1)]
    last_sequence: Annotated[int, Field(strict=True, ge=1)]
    state_observed_at: UTCTimestamp
    state: PortfolioState
    inputs: RecommendationRequest
    strategy_version_id: UUID
    config_canonical_json: Annotated[str, Field(strict=True, max_length=262144)]
    config_sha256: Hash256
    snapshot_id: UUID
    snapshot_sha256: Hash256
    calendar_sha256: Hash256
    source_mode: SourceMode
    decision_cutoff_utc: UTCTimestamp
    engine_version: Hash256
    requested_at: UTCTimestamp

    @property
    def config(self) -> StrategyConfigV1:
        return StrategyConfigV1.from_json(self.config_canonical_json)

    @model_validator(mode="after")
    def immutable_identity(self) -> Self:
        if self.state_observed_at > self.decision_cutoff_utc:
            raise ValueError("Posted portfolio state was not known at this cutoff")
        if self.config.config_hash() != self.config_sha256:
            raise ValueError("Recommendation strategy fingerprint differs")
        if self.inputs.snapshot_id is not None and self.inputs.snapshot_id != self.snapshot_id:
            raise ValueError("Recommendation snapshot differs from explicit request")
        expected = (
            "synthetic_replay" if self.source_mode == "synthetic_fixture" else "current_paper"
        )
        if self.inputs.clock_mode != expected:
            raise ValueError("Clock mode must agree with the portfolio source")
        if self.source_mode != "synthetic_fixture" and self.decision_cutoff_utc > self.requested_at:
            raise ValueError("Real decision cutoff has not elapsed")
        return self


class RecommendationPrepared(Contract):
    evaluation: StrategyEvaluationResultV1
    plan: OrderPlan


class RecommendationComputed(Contract):
    prepared: RecommendationPrepared
    recommendation: RecommendationV1
    forecast_inputs: ForecastInputs
