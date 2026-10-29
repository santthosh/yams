"""Readonly scheduling diagnostics; logical replay and actual observation remain separate."""

from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, StrictBool, model_validator

from backend.domain.common import JobV1
from backend.domain.recommendation_api import ClockMode
from backend.domain.types import Contract, Hash256, Reason, SessionDate, SourceMode, UTCTimestamp

ReviewState = Literal[
    "waiting", "review_admitted", "unavailable", "paused", "up_to_date", "catching_up", "unobserved"
]


class SupervisorObservationV1(Contract):
    status: Literal["unobserved", "fresh", "stale"]
    measured_at: UTCTimestamp
    last_seen_at: UTCTimestamp | None
    last_unobserved_start_at: UTCTimestamp | None
    last_unobserved_end_at: UTCTimestamp | None
    limitation: Literal["OBSERVATION_NOT_EXACT_SHUTDOWN"] = "OBSERVATION_NOT_EXACT_SHUTDOWN"


class ReviewOccurrenceV1(Contract):
    id: UUID
    as_of_session: SessionDate
    intended_due_at: UTCTimestamp
    opportunity_end_at: UTCTimestamp | None
    first_observed_clock_at: UTCTimestamp
    observed_snapshot_id: UUID
    observed_snapshot_sha256: Hash256
    created_at: UTCTimestamp
    outcome: Literal["waiting", "admitted", "missed", "skipped"]
    reason: Reason | None
    handled_at: UTCTimestamp | None
    handled_clock_at: UTCTimestamp | None
    recommendation_id: UUID | None
    job: JobV1 | None

    @model_validator(mode="after")
    def truthful_outcome(self) -> Self:
        if (
            self.outcome == "admitted" and (self.job is None or self.recommendation_id is None)
        ) or (
            self.outcome != "admitted"
            and (self.job is not None or self.recommendation_id is not None)
        ):
            raise ValueError("Admitted reviews require their original resource and job")
        if self.outcome == "waiting" and (
            self.reason is None or self.handled_at is not None or self.handled_clock_at is not None
        ):
            raise ValueError("Waiting reviews require a reason and no handled time")
        if self.outcome != "waiting" and (self.handled_at is None or self.handled_clock_at is None):
            raise ValueError("Handled reviews require actual and logical timing")
        return self


class PortfolioScheduleV1(Contract):
    portfolio_id: UUID
    frequency: Literal["monthly"] = "monthly"
    data_status: SourceMode
    clock_mode: ClockMode
    paper_only: Literal[True] = True
    account_state: Literal["active", "paused", "closed"]
    reconciliation_required: StrictBool
    last_observed_state: ReviewState
    reason: Reason | None
    last_observed_at: UTCTimestamp | None
    clock_at: UTCTimestamp
    observed_clock_at: UTCTimestamp | None
    last_explicit_review_cutoff: UTCTimestamp | None
    next_review_session: SessionDate | None
    next_review_due_at: UTCTimestamp | None
    due_backlog: StrictBool | None
    backlog_unavailable_reason: Reason | None
    active_order_batch_id: UUID | None
    active_batch_controls_available: StrictBool
    recent_occurrences: Annotated[tuple[ReviewOccurrenceV1, ...], Field(max_length=25)]
    supervisor: SupervisorObservationV1

    @model_validator(mode="after")
    def truthful_schedule(self) -> Self:
        if (self.next_review_session is None) != (self.next_review_due_at is None):
            raise ValueError("Next review requires both a session and cutoff")
        if self.due_backlog is None and self.backlog_unavailable_reason is None:
            raise ValueError("Unknown backlog requires a reason")
        if self.active_batch_controls_available and self.active_order_batch_id is None:
            raise ValueError("Batch controls require an actual batch")
        return self
