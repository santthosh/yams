"""Atomic review linkage called only with the existing portfolio lock held."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.domain.market import SnapshotManifestV1
from backend.domain.recommendation_api import RecommendationAccepted, RecommendationRequest
from backend.jobs.review_clock import monthly_anchors
from backend.market_data.models import Calendar
from backend.persistence.models.ledger import PaperOrderBatch
from backend.persistence.models.portfolio import PaperPortfolio
from backend.persistence.models.review import PortfolioReviewOccurrence, PortfolioReviewTarget
from backend.persistence.models.snapshot import CurrentSnapshot
from backend.portfolio.ledger import LedgerConflict
from backend.portfolio.paper_clock import replay_floor


def review_schema_available(session: Session) -> bool:
    """Retain legacy upgrade probes; production readiness still gates startup."""
    return session.scalar(select(func.to_regclass("recommendation_request_alias"))) is not None


@dataclass(frozen=True)
class ScheduledAdmission:
    occurrence: PortfolioReviewOccurrence
    target: PortfolioReviewTarget
    observed_clock: datetime
    actual_at: datetime


def scheduled_admission(
    session: Session,
    portfolio: PaperPortfolio,
    occurrence_id: UUID,
    request: RecommendationRequest,
    manifest: SnapshotManifestV1,
    calendar: Calendar,
    actual_at: datetime,
) -> ScheduledAdmission:
    row = session.scalar(
        select(PortfolioReviewOccurrence)
        .where(
            PortfolioReviewOccurrence.id == occurrence_id,
            PortfolioReviewOccurrence.portfolio_id == portfolio.id,
        )
        .with_for_update()
    )
    target = session.get(PortfolioReviewTarget, portfolio.id)
    pointer = session.get(CurrentSnapshot, portfolio.source_mode)
    if (
        row is None
        or target is None
        or row.outcome != "waiting"
        or row.decision_session != request.as_of_session
        or portfolio.source_mode != "synthetic_fixture"
        or pointer is None
        or pointer.snapshot_id != manifest.snapshot_id()
    ):
        raise LedgerConflict("Scheduled review changed during admission")
    if (
        session.scalar(
            select(PaperOrderBatch.id)
            .where(
                PaperOrderBatch.portfolio_id == portfolio.id,
                ~PaperOrderBatch.terminal,
            )
            .limit(1)
        )
        is not None
    ):
        raise LedgerConflict("An approved batch must resolve before scheduled review")
    anchor = next(
        (item for item in monthly_anchors(calendar) if item.session == row.decision_session), None
    )
    clock = replay_floor(session, portfolio.id, portfolio.created_at)
    if (
        anchor is None
        or anchor.due_at != row.due_at
        or anchor.window_end_at != row.window_end_at
        or list(anchor.calendar_rows) != row.calendar_rows
        or anchor.state(clock) != "current"
    ):
        raise LedgerConflict("Original review opportunity is unavailable or has elapsed")
    return ScheduledAdmission(row, target, clock, actual_at)


def link_scheduled_admission(
    session: Session, context: ScheduledAdmission, accepted: RecommendationAccepted
) -> None:
    row, target = context.occurrence, context.target
    row.outcome, row.reason = "admitted", None
    row.recommendation_id, row.job_id = accepted.recommendation_id, accepted.job_id
    row.handled_at, row.handled_clock_at = context.actual_at, context.observed_clock
    target.last_handled_session = row.decision_session
    target.next_session = target.next_due_at = target.next_window_end_at = None
    target.next_calendar_rows = None
    target.last_observed_at, target.last_clock_at = context.actual_at, context.observed_clock
    target.status, target.reason = "review_admitted", "WAITING_FOR_REVIEW_JOB"
    session.flush()  # Link/checkpoint failures must roll back the new job/run as well.
