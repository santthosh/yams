"""Bounded readonly scheduler projection; no enqueue, checkpoint repair or clock advance."""

from datetime import timedelta
from uuid import UUID

from pydantic import TypeAdapter
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from backend.domain.review import (
    PortfolioScheduleV1,
    ReviewOccurrenceV1,
    SupervisorObservationV1,
)
from backend.domain.types import SourceMode
from backend.jobs.queue import Queue, database_now
from backend.persistence.models.job import Job
from backend.persistence.models.ledger import PaperOrderBatch
from backend.persistence.models.recommendation import RecommendationPublication
from backend.persistence.models.review import (
    PortfolioReviewOccurrence,
    PortfolioReviewTarget,
    SchedulerObservation,
)
from backend.portfolio.ledger import _locked
from backend.portfolio.paper_clock import replay_floor


def schedule_status(engine: Engine, owner: UUID) -> PortfolioScheduleV1:
    with Session(engine) as session, session.begin():
        account = _locked(session, owner)
        target = session.get(PortfolioReviewTarget, owner)
        observation = session.get(SchedulerObservation, 1)
        now = database_now(session)
        supervisor = SupervisorObservationV1(
            status=(
                "unobserved"
                if observation is None
                else "fresh"
                if now <= observation.last_seen_at + timedelta(seconds=observation.grace_seconds)
                else "stale"
            ),
            measured_at=now,
            last_seen_at=observation.last_seen_at if observation else None,
            last_unobserved_start_at=observation.last_gap_start_at if observation else None,
            last_unobserved_end_at=observation.last_gap_end_at if observation else None,
        )
        rows = list(
            session.scalars(
                select(PortfolioReviewOccurrence)
                .where(
                    PortfolioReviewOccurrence.portfolio_id == owner,
                )
                .order_by(
                    PortfolioReviewOccurrence.decision_session.desc(),
                    PortfolioReviewOccurrence.id.desc(),
                )
                .limit(25)
            )
        )
        job_ids = [row.job_id for row in rows if row.job_id is not None]
        jobs = (
            {job.id: job for job in session.scalars(select(Job).where(Job.id.in_(job_ids)))}
            if job_ids
            else {}
        )
        recent = tuple(
            ReviewOccurrenceV1.model_validate(
                dict(
                    id=row.id,
                    as_of_session=row.decision_session,
                    intended_due_at=row.due_at,
                    opportunity_end_at=row.window_end_at,
                    first_observed_clock_at=row.observed_clock_at,
                    observed_snapshot_id=row.observed_snapshot_id,
                    observed_snapshot_sha256=row.observed_snapshot_sha256,
                    created_at=row.created_at,
                    outcome=row.outcome,
                    reason=row.reason,
                    handled_at=row.handled_at,
                    handled_clock_at=row.handled_clock_at,
                    recommendation_id=row.recommendation_id,
                    job=Queue.view(jobs[row.job_id]) if row.job_id is not None else None,
                )
            )
            for row in rows
        )
        batch = session.scalar(
            select(PaperOrderBatch).where(
                PaperOrderBatch.portfolio_id == owner,
                ~PaperOrderBatch.terminal,
            )
        )
        controls = (
            batch is not None
            and session.get(RecommendationPublication, batch.recommendation_id) is not None
        )
        mode = TypeAdapter(SourceMode).validate_python(account.source_mode)
        clock = (
            replay_floor(session, owner, account.created_at) if mode == "synthetic_fixture" else now
        )
        due_backlog = None
        if target is not None and target.next_due_at is not None:
            due_backlog = target.next_due_at <= clock
        return PortfolioScheduleV1.model_validate(
            dict(
                portfolio_id=owner,
                data_status=mode,
                clock_mode="synthetic_replay" if mode == "synthetic_fixture" else "current_paper",
                account_state=account.status,
                reconciliation_required=account.reconciliation_failed,
                last_observed_state=target.status if target else "unobserved",
                reason=target.reason if target else "NOT_YET_OBSERVED",
                last_observed_at=target.last_observed_at if target else None,
                clock_at=clock,
                observed_clock_at=target.last_clock_at if target else None,
                last_explicit_review_cutoff=target.last_explicit_review_cutoff if target else None,
                next_review_session=target.next_session if target else None,
                next_review_due_at=target.next_due_at if target else None,
                due_backlog=due_backlog,
                backlog_unavailable_reason=None
                if due_backlog is not None
                else "NEXT_REVIEW_NOT_YET_KNOWN",
                active_order_batch_id=batch.id if batch else None,
                active_batch_controls_available=controls,
                recent_occurrences=recent,
                supervisor=supervisor,
            )
        )
