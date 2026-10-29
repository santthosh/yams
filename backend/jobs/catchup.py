"""Bounded chronological monthly review catch-up; no approvals or price arithmetic."""

import logging
from dataclasses import dataclass
from datetime import date, datetime
from heapq import heappop, heappush
from pathlib import Path
from uuid import UUID, uuid5

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from backend.domain.recommendation_api import RecommendationRequest
from backend.jobs.queue import Queue, database_now
from backend.jobs.registry import validate_workload
from backend.jobs.review_admission import review_schema_available
from backend.jobs.review_clock import ReviewAnchor, monthly_anchors, next_review_anchor
from backend.market_data.catalog import verified_snapshot
from backend.market_data.files import PinnedSnapshot, SnapshotIntegrityError
from backend.market_data.models import Calendar
from backend.persistence.models.job import Job
from backend.persistence.models.ledger import LedgerEvent, PaperOrderBatch
from backend.persistence.models.portfolio import PaperPortfolio
from backend.persistence.models.review import PortfolioReviewOccurrence, PortfolioReviewTarget
from backend.persistence.models.snapshot import CurrentSnapshot, DatasetSnapshot
from backend.portfolio.accounts import AccountError
from backend.portfolio.ledger import LedgerConflict, ReconciliationFailure, _locked
from backend.portfolio.paper_clock import replay_floor
from backend.portfolio.recommendations import RecommendationAdmissionError, admit_recommendation

logger = logging.getLogger(__name__)
ACTIVE_JOBS = ("queued", "running", "cancel_requested")


@dataclass(frozen=True)
class ReviewSource:
    pinned: PinnedSnapshot
    calendar: Calendar
    anchors: tuple[ReviewAnchor, ...]
    first_session: date


@dataclass(frozen=True)
class ReviewCandidate:
    owner: UUID
    occurrence_id: UUID
    due_at: datetime


def _source(engine: Engine, root: Path) -> ReviewSource | None:
    with Session(engine) as session:
        pointer = session.get(CurrentSnapshot, "synthetic_fixture")
        source = session.get(DatasetSnapshot, pointer.snapshot_id) if pointer else None
    if source is None or source.quality == "blocked":
        return None
    pinned = verified_snapshot(source, root)  # No financial lock or DB session is held.
    calendar = Calendar.model_validate_json(
        pinned.artifacts[pinned.manifest.calendar.artifact_path]
    )
    first = pinned.manifest.coverage.first_session
    if first is None:
        return None
    validate_workload(
        assets=len(pinned.manifest.coverage.asset_ids), sessions=len(calendar.sessions)
    )
    return ReviewSource(pinned, calendar, monthly_anchors(calendar), first)


def _earlier_job(session: Session, owner: UUID) -> bool:
    return (
        session.scalar(
            select(Job.id)
            .join(
                PortfolioReviewOccurrence,
                PortfolioReviewOccurrence.job_id == Job.id,
            )
            .where(PortfolioReviewOccurrence.portfolio_id == owner, Job.status.in_(ACTIVE_JOBS))
            .limit(1)
        )
        is not None
    )


def _clear_next(target: PortfolioReviewTarget) -> None:
    target.next_session = target.next_due_at = target.next_window_end_at = None
    target.next_calendar_rows = None


def _set_anchor(target: PortfolioReviewTarget, anchor: ReviewAnchor) -> None:
    target.next_session, target.next_due_at = anchor.session, anchor.due_at
    target.next_window_end_at, target.next_calendar_rows = (
        anchor.window_end_at,
        list(anchor.calendar_rows),
    )


def _compatible_target(target: PortfolioReviewTarget, anchor: ReviewAnchor) -> bool:
    if target.next_session is None:
        return True
    original_rows = target.next_calendar_rows or []
    return (
        target.next_session == anchor.session
        and target.next_due_at == anchor.due_at
        and (target.next_window_end_at is None or target.next_window_end_at == anchor.window_end_at)
        and original_rows == list(anchor.calendar_rows[: len(original_rows)])
    )


def _prepare_target(
    engine: Engine, owner: UUID, source: ReviewSource | None, source_reason: str
) -> ReviewCandidate | None:
    with Session(engine) as session, session.begin():
        account = _locked(session, owner)
        now = database_now(session)
        target = session.get(PortfolioReviewTarget, owner)
        if target is None:
            target = PortfolioReviewTarget(
                portfolio_id=owner,
                last_observed_at=now,
                status="unobserved",
                reason="NOT_YET_OBSERVED",
            )
            session.add(target)
        target.last_observed_at = now
        clock = (
            replay_floor(session, owner, account.created_at)
            if account.source_mode == "synthetic_fixture"
            else now
        )
        target.last_clock_at = clock
        if account.status != "active":
            target.status, target.reason = "paused", "PORTFOLIO_NOT_ACTIVE"
            return None
        if account.reconciliation_failed:
            target.status, target.reason = "unavailable", "RECONCILIATION_REQUIRED"
            return None
        if account.source_mode != "synthetic_fixture":
            target.status, target.reason = "unavailable", "UNSUPPORTED_ACCOUNTING_SOURCE"
            return None
        pointer = session.get(CurrentSnapshot, account.source_mode)
        if (
            source is None
            or pointer is None
            or pointer.snapshot_id != source.pinned.manifest.snapshot_id()
        ):
            target.status, target.reason = "unavailable", source_reason
            return None
        if _earlier_job(session, owner):
            target.status, target.reason = "waiting", "WAITING_FOR_REVIEW_JOB"
            _clear_next(target)
            return None
        anchors = tuple(row for row in source.anchors if row.due_at >= account.created_at)
        anchor = next_review_anchor(anchors, source.first_session, target.last_handled_session)
        if anchor is None:
            target.status, target.reason = "unavailable", "FUTURE_REVIEW_CALENDAR_UNAVAILABLE"
            _clear_next(target)
            return None
        if not _compatible_target(target, anchor):
            target.status, target.reason = "unavailable", "REVIEW_CALENDAR_CHANGED"
            return None
        _set_anchor(target, anchor)
        state = anchor.state(clock)
        if state == "future":
            target.status, target.reason = "up_to_date", "NEXT_MONTHLY_REVIEW_NOT_DUE"
            return None
        if state == "unavailable":
            target.status, target.reason = "unavailable", "REVIEW_WINDOW_CALENDAR_UNAVAILABLE"
            return None
        identity = uuid5(owner, "monthly-review:" + anchor.session.isoformat())
        occurrence = session.get(PortfolioReviewOccurrence, identity)
        if occurrence is None:
            session.flush()
            occurrence = PortfolioReviewOccurrence(
                id=identity,
                portfolio_id=owner,
                decision_session=anchor.session,
                due_at=anchor.due_at,
                window_end_at=anchor.window_end_at,
                calendar_rows=list(anchor.calendar_rows),
                observed_snapshot_id=source.pinned.manifest.snapshot_id(),
                observed_snapshot_sha256=source.pinned.manifest.manifest_hash(),
                observed_clock_at=clock,
                created_at=now,
                outcome="waiting",
                reason="REVIEW_DUE",
            )
            session.add(occurrence)
        if occurrence.outcome != "waiting" or (
            occurrence.due_at,
            occurrence.window_end_at,
            occurrence.calendar_rows,
        ) != (anchor.due_at, anchor.window_end_at, list(anchor.calendar_rows)):
            target.status, target.reason = "unavailable", "REVIEW_CHECKPOINT_CONFLICT"
            return None
        target.status, target.reason = "catching_up", "REVIEW_DUE"
        return ReviewCandidate(owner, identity, anchor.due_at)


def _handle(
    session: Session,
    target: PortfolioReviewTarget,
    occurrence: PortfolioReviewOccurrence,
    now: datetime,
    clock: datetime,
    outcome: str,
    reason: str,
) -> None:
    occurrence.outcome, occurrence.reason = outcome, reason
    occurrence.handled_at, occurrence.handled_clock_at = now, clock
    target.last_handled_session = occurrence.decision_session
    target.last_observed_at, target.last_clock_at = now, clock
    target.status, target.reason = "catching_up", reason
    _clear_next(target)
    session.flush()


def _process_candidate(
    queue: Queue, source: ReviewSource, candidate: ReviewCandidate, may_admit: bool, root: Path
) -> str:
    with Session(queue.engine) as session, session.begin():
        account = _locked(session, candidate.owner)
        target = session.get(PortfolioReviewTarget, candidate.owner)
        occurrence = session.get(PortfolioReviewOccurrence, candidate.occurrence_id)
        if target is None or occurrence is None or occurrence.outcome != "waiting":
            return "deferred"
        now = database_now(session)
        clock = replay_floor(session, account.id, account.created_at)
        target.last_observed_at, target.last_clock_at = now, clock
        anchor = next(
            (row for row in source.anchors if row.session == occurrence.decision_session), None
        )
        pointer = session.get(CurrentSnapshot, account.source_mode)
        if (
            account.status != "active"
            or account.reconciliation_failed
            or account.source_mode != "synthetic_fixture"
            or pointer is None
            or pointer.snapshot_id != source.pinned.manifest.snapshot_id()
            or anchor is None
            or anchor.due_at != occurrence.due_at
            or list(anchor.calendar_rows) != occurrence.calendar_rows
        ):
            target.status, target.reason = "unavailable", "REVIEW_STATE_CHANGED"
            return "deferred"
        if _earlier_job(session, account.id):
            target.status, target.reason = "waiting", "WAITING_FOR_REVIEW_JOB"
            return "deferred"
        state = anchor.state(clock)
        if state == "missed":
            _handle(session, target, occurrence, now, clock, "missed", "REVIEW_WINDOW_PASSED")
            return "handled"
        if state != "current":
            target.status, target.reason = "waiting", "REVIEW_OPPORTUNITY_UNAVAILABLE"
            return "deferred"
        latest = session.execute(
            select(LedgerEvent.recorded_at, LedgerEvent.effective_at)
            .where(
                LedgerEvent.portfolio_id == account.id,
            )
            .order_by(LedgerEvent.sequence.desc())
            .limit(1)
        ).one_or_none()
        if latest is None:
            target.status, target.reason = "unavailable", "POSTED_CHRONOLOGY_UNAVAILABLE"
            return "deferred"
        if max(latest) > occurrence.due_at:
            _handle(session, target, occurrence, now, clock, "skipped", "POSTED_STATE_AFTER_CUTOFF")
            return "handled"
        active_batch = session.scalar(
            select(PaperOrderBatch.id)
            .where(
                PaperOrderBatch.portfolio_id == account.id,
                ~PaperOrderBatch.terminal,
            )
            .limit(1)
        )
        if active_batch is not None or not may_admit:
            target.status = "waiting"
            occurrence.reason = target.reason = (
                "ACTIVE_APPROVED_BATCH" if active_batch else "REVIEW_ADMISSION_LIMIT"
            )
            return "deferred"
        requested_session = occurrence.decision_session
    # Snapshot reads, immutable build hashing and normal admission own their short
    # transactions; no financial lock/session survives across this call.
    try:
        admit_recommendation(
            queue.engine,
            root,
            candidate.owner,
            RecommendationRequest(
                as_of_session=requested_session,
                snapshot_id=source.pinned.manifest.snapshot_id(),
                clock_mode="synthetic_replay",
            ),
            schedule_occurrence_id=candidate.occurrence_id,
        )
        return "admitted"
    except ValueError as error:
        reason = "REVIEW_ADMISSION_UNAVAILABLE"
        if isinstance(error, (RecommendationAdmissionError, AccountError)):
            reason = error.code
        elif isinstance(error, ReconciliationFailure):
            reason = "RECONCILIATION_REQUIRED"
        elif isinstance(error, LedgerConflict):
            reason = "REVIEW_STATE_CHANGED"
        elif isinstance(error, SnapshotIntegrityError):
            reason = "SOURCE_INTEGRITY_UNAVAILABLE"
        logger.warning(
            "portfolio_review_admission_unavailable portfolio_id=%s error_type=%s",
            candidate.owner,
            type(error).__name__,
        )
        with Session(queue.engine) as session, session.begin():
            _locked(session, candidate.owner)
            target = session.get(PortfolioReviewTarget, candidate.owner)
            occurrence = session.get(PortfolioReviewOccurrence, candidate.occurrence_id)
            if target is not None and occurrence is not None and occurrence.outcome == "waiting":
                target.status, target.reason = "waiting", reason
                occurrence.reason = reason
        return "deferred"


def catch_up_reviews(queue: Queue, root: Path) -> dict[str, int]:
    """Fair bounded target scan, oldest observed occurrences first, one review admission."""
    limit = queue.limits.catchup_batch
    with Session(queue.engine) as session:
        if not review_schema_available(session):
            return {"handled": 0, "admitted": 0, "deferred": 0}
        owners = list(
            session.scalars(
                select(PaperPortfolio.id)
                .outerjoin(
                    PortfolioReviewTarget,
                    PortfolioReviewTarget.portfolio_id == PaperPortfolio.id,
                )
                .where(PaperPortfolio.status == "active")
                .order_by(
                    PortfolioReviewTarget.last_observed_at.asc().nulls_first(), PaperPortfolio.id
                )
                .limit(limit)
            )
        )
    result = {"handled": 0, "admitted": 0, "deferred": 0}
    if not owners:
        return result
    source_reason = "SOURCE_UNAVAILABLE"
    try:
        source = _source(queue.engine, root)
    except ValueError:
        logger.warning("portfolio_review_source_unavailable")
        source, source_reason = None, "SOURCE_INTEGRITY_UNAVAILABLE"
    candidates: list[tuple[datetime, UUID, ReviewCandidate]] = []
    for owner in owners:
        candidate = _prepare_target(queue.engine, owner, source, source_reason)
        if candidate is not None:
            heappush(candidates, (candidate.due_at, candidate.owner, candidate))
    if source is None:
        return result
    for _ in range(limit):
        if not candidates:
            break
        _, _, candidate = heappop(candidates)
        outcome = _process_candidate(queue, source, candidate, result["admitted"] == 0, root)
        result[outcome] += 1
        if outcome == "handled":
            following = _prepare_target(queue.engine, candidate.owner, source, source_reason)
            if following is not None:
                heappush(candidates, (following.due_at, following.owner, following))
    return result
