"""Public paper authorization controls; all price/clock inputs remain server-owned."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StrictBool

from backend.domain.common import JobV1
from backend.domain.orders import PaperOrderBatchV1
from backend.domain.recommendation_api import ClockMode
from backend.domain.types import Contract, Hash256, Reason, SourceMode, UTCTimestamp


class ApplyRecommendationRequest(Contract):
    expected_revision: Annotated[int, Field(strict=True, ge=1, le=9223372036854775807)]


class PaperActionRequest(Contract):
    """Explicit empty JSON body; caller timestamps/amounts are forbidden."""


class PaperApprovalAccepted(Contract):
    batch_id: UUID
    portfolio_id: UUID
    recommendation_id: UUID
    approval_idempotency_key: UUID
    approved_revision: Annotated[int, Field(strict=True, ge=1)]
    approved_at: UTCTimestamp
    eligible_open_at: UTCTimestamp
    operator_recorded_at: UTCTimestamp | None
    data_status: SourceMode
    clock_mode: ClockMode
    paper_only: Literal[True] = True


class PaperBatchDetailV1(PaperOrderBatchV1):
    data_status: SourceMode
    clock_mode: ClockMode
    paper_only: Literal[True] = True
    snapshot_sha256: Hash256
    operator_recorded_at: UTCTimestamp | None
    current_portfolio_revision: Annotated[int, Field(strict=True, ge=1)]
    fixture_clock_at: UTCTimestamp | None
    latest_fill_job: JobV1 | None
    can_advance_fixture: StrictBool
    advance_unavailable_reason: Reason | None


class FixtureAdvanceAccepted(Contract):
    batch_id: UUID
    job_id: UUID
    fixture_observed_at: UTCTimestamp
    data_status: Literal["synthetic_fixture"] = "synthetic_fixture"
    paper_only: Literal[True] = True


class RecommendationDispositionV1(Contract):
    recommendation_id: UUID
    status: Literal["ready", "applied", "dismissed", "expired"]
