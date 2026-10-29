"""Recommendation admission/history and truthful asynchronous forecast transport."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from backend.domain.common import ErrorDetail, JobStatus, JobV1
from backend.domain.evaluation import StrategyEvaluationResultV1
from backend.domain.forecast import ForecastV1
from backend.domain.recommendation import RecommendationV1
from backend.domain.strategy import StrategyConfigV1
from backend.domain.types import (
    Contract,
    Hash256,
    SessionDate,
    SourceMode,
    UTCTimestamp,
    canonical_json,
    load_json,
)

ClockMode = Literal["synthetic_replay", "current_paper"]


class RecommendationRequest(Contract):
    as_of_session: SessionDate
    snapshot_id: UUID | None = None
    clock_mode: ClockMode
    seed: Annotated[int, Field(strict=True, ge=0, le=18446744073709551615)] = 42

    def canonical_bytes(self) -> bytes:
        return canonical_json(load_json(self.model_dump_json()))


class RecommendationAccepted(Contract):
    recommendation_id: UUID
    job_id: UUID


class RecommendationSummaryV1(Contract):
    id: UUID
    portfolio_id: UUID
    job_id: UUID
    status: JobStatus
    disposition: Literal["ready", "applied", "dismissed", "expired"] | None
    inputs: RecommendationRequest
    inputs_canonical_json: str
    portfolio_revision: int
    strategy_version_id: UUID
    snapshot_id: UUID
    data_status: SourceMode
    created_at: UTCTimestamp
    error: ErrorDetail | None


class RecommendationPageV1(Contract):
    items: tuple[RecommendationSummaryV1, ...]
    next_cursor: str | None


class RecommendationDetailV1(RecommendationV1):
    """Original content plus separately changing disposition and forecast job state."""

    job_id: UUID
    inputs: RecommendationRequest
    inputs_canonical_json: str
    clock_mode: ClockMode
    computed_at: UTCTimestamp
    config_sha256: Hash256
    calendar_sha256: Hash256
    strategy_config: StrategyConfigV1
    strategy_evidence: StrategyEvaluationResultV1
    forecast_inputs_canonical_json: str
    forecast_job: JobV1
    forecast: ForecastV1 | None
    is_current: bool
    current_portfolio_revision: int
    stale_reasons: tuple[str, ...]
