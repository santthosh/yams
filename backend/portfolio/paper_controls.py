"""Public paper controls delegate financial transitions to the shared ledger service."""

from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid5

from pydantic import TypeAdapter
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from backend.domain.fill_job import ScheduledFillPayload
from backend.domain.paper_api import (
    FixtureAdvanceAccepted,
    PaperApprovalAccepted,
    PaperBatchDetailV1,
    RecommendationDispositionV1,
)
from backend.domain.types import SourceMode, UTCTimestamp
from backend.jobs.queue import Queue
from backend.market_data.catalog import verified_snapshot
from backend.market_data.models import Calendar
from backend.persistence.models.job import Job
from backend.persistence.models.ledger import (
    LedgerEvent,
    PaperOrder,
    PaperOrderBatch,
    RecommendationReference,
)
from backend.persistence.models.recommendation import RecommendationPublication, RecommendationRun
from backend.persistence.models.snapshot import CurrentSnapshot, DatasetSnapshot
from backend.portfolio.batches import StaleApprovalData, _retry, approve_batch, batch_view
from backend.portfolio.execution import next_eligible_session
from backend.portfolio.execution_sources import verify_execution_sources
from backend.portfolio.fills import _enqueue_locked_attempt
from backend.portfolio.ledger import LedgerConflict, _locked, digest
from backend.portfolio.paper_clock import replay_floor
from backend.portfolio.recommendation_queries import RecommendationPending


def public_recommendation(session: Session, identity: UUID) -> RecommendationReference:
    run = session.get(RecommendationRun, identity)
    if run is None:
        raise LookupError("Recommendation does not exist")
    publication = session.get(RecommendationPublication, identity)
    job = session.get(Job, run.job_id)
    if job is None or job.kind != "evaluate_portfolio" or job.payload != run.payload:
        raise ValueError("Recommendation linkage is unavailable")
    if publication is None:
        if job.status == "completed":
            raise ValueError("Completed recommendation has no publication")
        raise RecommendationPending(Queue.view(job))
    row = session.get(RecommendationReference, identity)
    if job.status != "completed" or row is None or row.portfolio_id != run.portfolio_id:
        raise ValueError("Recommendation publication is unavailable")
    return row


def _audit(session: Session, batch: PaperOrderBatch) -> datetime | None:
    event = session.get(LedgerEvent, batch.id)
    if event is None or event.kind != "batch_approval" or event.portfolio_id != batch.portfolio_id:
        raise ValueError("Approval audit is unavailable")
    actual = event.payload.get("details", {}).get("operator_recorded_at")
    return TypeAdapter(UTCTimestamp).validate_python(actual) if actual is not None else None


def approval_result(engine: Engine, identity: UUID, key: UUID) -> PaperApprovalAccepted:
    """Read the original identity without source files, freshness or mutations."""
    with Session(engine) as session:
        rec = public_recommendation(session, identity)
        batch = session.scalar(
            select(PaperOrderBatch).where(
                PaperOrderBatch.portfolio_id == rec.portfolio_id,
                PaperOrderBatch.idempotency_key == key,
            )
        )
        if batch is None:
            raise LookupError("Approval key does not exist")
        if batch.recommendation_id != identity:
            from backend.portfolio.batches import ApprovalIdempotencyConflict

            raise ApprovalIdempotencyConflict("Key belongs to a different recommendation")
        mode = TypeAdapter(SourceMode).validate_python(batch.context["mode"])
        return PaperApprovalAccepted(
            batch_id=batch.id,
            portfolio_id=batch.portfolio_id,
            recommendation_id=batch.recommendation_id,
            approval_idempotency_key=batch.idempotency_key,
            approved_revision=batch.approved_revision,
            approved_at=batch.approved_at,
            eligible_open_at=batch.eligible_open_at,
            operator_recorded_at=_audit(session, batch),
            data_status=mode,
            clock_mode="synthetic_replay" if mode == "synthetic_fixture" else "current_paper",
        )


def apply_recommendation(
    engine: Engine, root: Path, identity: UUID, revision: int, key: UUID
) -> PaperApprovalAccepted:
    with Session(engine) as session:
        rec = public_recommendation(session, identity)
        owner, snapshot = rec.portfolio_id, rec.snapshot_id
        request_hash = digest(
            dict(
                portfolio_id=str(owner), recommendation_id=str(identity), expected_revision=revision
            )
        )
        prior = _retry(session, owner, key, request_hash)
        source = session.get(DatasetSnapshot, snapshot) if prior is None else None
    if prior is None:
        if source is None:
            raise ValueError("Decision source is unavailable")
        pinned = verified_snapshot(source, root)  # Filesystem work precedes the portfolio lock.
        approve_batch(
            engine,
            owner,
            identity,
            expected_revision=revision,
            idempotency_key=key,
            pinned=pinned,
            server_clock=True,
        )
    return approval_result(engine, identity, key)


def batch_detail(engine: Engine, identity: UUID) -> PaperBatchDetailV1:
    with Session(engine) as session:
        owner = session.scalar(
            select(PaperOrderBatch.portfolio_id).where(PaperOrderBatch.id == identity)
        )
    if owner is None:
        raise LookupError("Paper batch does not exist")
    with Session(engine) as session, session.begin():
        account = _locked(session, owner)
        batch = session.get(PaperOrderBatch, identity)
        assert batch is not None
        public_recommendation(session, batch.recommendation_id)
        orders = list(
            session.scalars(
                select(PaperOrder)
                .where(PaperOrder.batch_id == identity)
                .order_by(PaperOrder.ordinal)
            )
        )
        latest = session.scalar(
            select(Job)
            .where(
                Job.kind == "apply_scheduled_fills",
                Job.payload["batch_id"].as_string() == str(identity),
            )
            .order_by(Job.created_at.desc(), Job.id.desc())
            .limit(1)
        )
        active = session.scalar(
            select(Job.id)
            .where(
                Job.kind == "apply_scheduled_fills",
                Job.payload["batch_id"].as_string() == str(identity),
                Job.status.in_(("queued", "running", "cancel_requested")),
            )
            .limit(1)
        )
        mode = TypeAdapter(SourceMode).validate_python(batch.context["mode"])
        reason = (
            "NOT_SYNTHETIC_FIXTURE"
            if mode != "synthetic_fixture"
            else "BATCH_TERMINAL"
            if batch.terminal
            else "PORTFOLIO_UNAVAILABLE"
            if account.reconciliation_failed or account.status != "active"
            else "FILL_JOB_ACTIVE"
            if active is not None
            else None
        )
        return PaperBatchDetailV1.model_validate(
            batch_view(batch, orders).model_dump()
            | dict(
                data_status=mode,
                clock_mode="synthetic_replay" if mode == "synthetic_fixture" else "current_paper",
                snapshot_sha256=batch.snapshot_sha256,
                operator_recorded_at=_audit(session, batch),
                current_portfolio_revision=account.revision,
                fixture_clock_at=replay_floor(session, owner, batch.approved_at)
                if mode == "synthetic_fixture"
                else None,
                latest_fill_job=Queue.view(latest) if latest is not None else None,
                can_advance_fixture=reason is None,
                advance_unavailable_reason=reason,
            )
        )


def dismiss_recommendation(engine: Engine, identity: UUID) -> RecommendationDispositionV1:
    with Session(engine) as session, session.begin():
        public_recommendation(session, identity)
        row = session.scalar(
            select(RecommendationReference)
            .where(RecommendationReference.id == identity)
            .with_for_update()
        )
        assert row is not None
        if row.disposition not in {"ready", "expired", "dismissed"}:
            raise LedgerConflict("An applied recommendation cannot be dismissed")
        row.disposition = "dismissed"
        return RecommendationDispositionV1(recommendation_id=identity, status="dismissed")


def advance_fixture(queue: Queue, root: Path, identity: UUID, key: UUID) -> FixtureAdvanceAccepted:
    """Explicit operator step; retry lookup precedes choosing a new replay time."""
    request_identity = uuid5(identity, "public-fixture-step:" + str(key))
    with Session(queue.engine) as session:
        prior = session.scalar(select(Job).where(Job.correlation_id == request_identity))
        if prior is not None:
            return _advance_result(prior, identity)
        batch = session.get(PaperOrderBatch, identity)
        if batch is None:
            raise LookupError("Paper batch does not exist")
        public_recommendation(session, batch.recommendation_id)
        owner = batch.portfolio_id
        pointer = session.get(CurrentSnapshot, "synthetic_fixture")
        source = session.get(DatasetSnapshot, pointer.snapshot_id) if pointer else None
        original = session.get(DatasetSnapshot, batch.snapshot_id)
    if source is None or original is None:
        raise StaleApprovalData("Execution source is unavailable")
    decision = verified_snapshot(original, root)
    execution = verified_snapshot(source, root)
    calendar = Calendar.model_validate_json(
        execution.artifacts[execution.manifest.calendar.artifact_path]
    )
    original_calendar = Calendar.model_validate_json(
        decision.artifacts[decision.manifest.calendar.artifact_path]
    )
    with Session(queue.engine) as session, session.begin():
        account = _locked(session, owner)
        prior = session.scalar(select(Job).where(Job.correlation_id == request_identity))
        if prior is not None:
            return _advance_result(prior, identity)
        batch = session.get(PaperOrderBatch, identity)
        assert batch is not None
        if (
            account.source_mode != "synthetic_fixture"
            or batch.context["mode"] != "synthetic_fixture"
        ):
            raise LedgerConflict("Only synthetic fixtures support explicit replay")
        if batch.terminal or account.reconciliation_failed or account.status != "active":
            raise LedgerConflict("Paper batch cannot advance")
        active = session.scalar(
            select(Job.id)
            .where(
                Job.kind == "apply_scheduled_fills",
                Job.payload["batch_id"].as_string() == str(identity),
                Job.status.in_(("queued", "running", "cancel_requested")),
            )
            .limit(1)
        )
        if active is not None:
            raise LedgerConflict("A fill attempt is still active")
        pointer = session.get(CurrentSnapshot, "synthetic_fixture")
        if pointer is None or pointer.snapshot_id != source.id or source.quality == "blocked":
            raise StaleApprovalData("Execution source changed during verification")
        eligible = next_eligible_session(
            original_calendar, batch.decision_cutoff, batch.approved_at
        )
        floor = replay_floor(session, owner, batch.approved_at)
        next_close = next(
            (
                row.close_at
                for row in calendar.sessions
                if row.close_at > floor and row.open_at >= batch.eligible_open_at
            ),
            None,
        )
        if next_close is None:
            raise StaleApprovalData("Pinned fixture calendar has no later completed session")
        # Compatibility is verified before accepting a durable step; quote availability
        # remains the existing worker's responsibility and may leave orders pending.
        orders = list(
            session.scalars(
                select(PaperOrder).where(PaperOrder.batch_id == identity, ~PaperOrder.terminal)
            )
        )
        for order in orders:
            verify_execution_sources(
                decision.manifest,
                execution.manifest,
                original_calendar,
                calendar,
                eligible,
                order.asset_id,
            )
        job_id = _enqueue_locked_attempt(
            queue, session, account, batch, next_close, request_correlation=request_identity
        )
        if job_id is None:
            raise LedgerConflict("No pending order can be admitted")
        job = session.get(Job, job_id)
        assert job is not None
        return _advance_result(job, identity)


def _advance_result(job: Job, batch_id: UUID) -> FixtureAdvanceAccepted:
    payload = ScheduledFillPayload.model_validate(job.payload)
    if (
        job.kind != "apply_scheduled_fills"
        or payload.batch_id != batch_id
        or payload.fixture_observed_at is None
    ):
        raise ValueError("Fixture step identity differs from its admitted job")
    return FixtureAdvanceAccepted(
        batch_id=batch_id, job_id=job.id, fixture_observed_at=payload.fixture_observed_at
    )
