"""Single-order admission and atomic lease-fenced ledger publication.

Each job can post one action OR one order. The next job is admitted only after
that commit, so an uncommitted sale never funds a buy. Missing evidence leaves
intent pending; a newer publication or explicit fixture-clock advance permits
another bounded attempt. There is no automatic financial replay clock.
"""

import logging
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID, uuid5

from pydantic import Field, TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.domain.common import JobResult
from backend.domain.fill_job import ScheduledFillPayload
from backend.domain.market import SnapshotManifestV1
from backend.domain.types import Contract, Hash256, SourceMode, UTCTimestamp
from backend.jobs.queue import Lease, Queue
from backend.jobs.registry import validate_workload
from backend.market_data.models import Calendar, CorporateAction
from backend.market_data.snapshots import PublicationFenceError
from backend.persistence.models.job import JobAttempt
from backend.persistence.models.ledger import PaperOrder, PaperOrderBatch
from backend.persistence.models.portfolio import PaperPortfolio
from backend.persistence.models.snapshot import CurrentSnapshot, DatasetSnapshot
from backend.portfolio.corporate_actions import action_key, apply_action
from backend.portfolio.execution import (
    ExecutionContext,
    MarketEvidence,
    calendar_digest,
    next_eligible_session,
)
from backend.portfolio.execution_sources import verify_execution_sources
from backend.portfolio.ledger import (
    LedgerConflict,
    _check_projection,
    _locked,
    _post_action,
    _post_order,
    digest,
)
from backend.strategies.build import engine_fingerprint


class PreparedFill(Contract):
    payload: ScheduledFillPayload
    calendar: Calendar
    execution_calendar: Calendar
    observed_at: UTCTimestamp
    execution_engine_version: Hash256
    market: MarketEvidence
    actions: Annotated[tuple[CorporateAction, ...], Field(max_length=1000)]


def enqueue_batch_attempt(
    queue: Queue, batch_id: UUID, *, fixture_observed_at: datetime | None = None
) -> UUID | None:
    """Trusted private fixture clock or real wall time; one bounded due order."""
    with Session(queue.engine) as session:
        owner = session.scalar(
            select(PaperOrderBatch.portfolio_id).where(PaperOrderBatch.id == batch_id)
        )
    if owner is None:
        raise LookupError("Paper batch does not exist")
    with Session(queue.engine) as session, session.begin():
        account = _locked(session, owner)
        batch = session.get(PaperOrderBatch, batch_id)
        assert batch is not None
        if batch.terminal or account.reconciliation_failed or account.status != "active":
            return None
        return _enqueue_locked_attempt(queue, session, account, batch, fixture_observed_at)


def _enqueue_locked_attempt(
    queue: Queue,
    session: Session,
    account: PaperPortfolio,
    batch: PaperOrderBatch,
    fixture_observed_at: datetime | None,
    *,
    request_correlation: UUID | None = None,
) -> UUID | None:
    """Caller owns the portfolio lock; shared bounded order admission, no fills."""
    now = fixture_observed_at or datetime.now(UTC)
    if (fixture_observed_at is not None) != (account.source_mode == "synthetic_fixture"):
        raise ValueError("Fixture execution requires an explicit replay clock")
    if now < batch.eligible_open_at:
        return None
    orders = list(
        session.scalars(
            select(PaperOrder).where(PaperOrder.batch_id == batch.id, ~PaperOrder.terminal)
        )
    )
    if not orders:
        return None
    order = min(orders, key=lambda row: (0 if row.side == "SELL" else 1, row.asset_id, row.ordinal))
    pointer = session.get(CurrentSnapshot, account.source_mode)
    source = session.get(DatasetSnapshot, pointer.snapshot_id) if pointer else None
    if source is None or source.quality == "blocked":
        return None
    manifest = SnapshotManifestV1.model_validate(source.manifest)
    calendar_rows = next(
        (a.row_count for a in manifest.artifacts if a.path == manifest.calendar.artifact_path),
        None,
    )
    if calendar_rows is None or calendar_rows < 1:
        raise ValueError("Execution calendar lacks admission metadata")
    validate_workload(assets=len(manifest.coverage.asset_ids), sessions=calendar_rows)
    payload = ScheduledFillPayload(
        portfolio_id=batch.portfolio_id,
        batch_id=batch.id,
        order_id=order.id,
        asset_id=order.asset_id,
        eligible_session=batch.eligible_open_at.date(),
        source_mode=TypeAdapter(SourceMode).validate_python(account.source_mode),
        decision_snapshot_id=batch.snapshot_id,
        decision_snapshot_sha256=batch.snapshot_sha256,
        execution_snapshot_id=source.id,
        execution_snapshot_sha256=source.manifest_hash,
        fixture_observed_at=fixture_observed_at,
    )
    identity = uuid5(
        batch.id,
        "fill-attempt:"
        + digest(
            [
                str(order.id),
                source.manifest_hash,
                account.revision,
                fixture_observed_at.isoformat() if fixture_observed_at else None,
            ]
        ),
    )
    return queue._enqueue(
        session,
        "apply_scheduled_fills",
        payload.model_dump(mode="json"),
        identity,
        correlation_id=request_correlation,
    )


def seal_fill(queue: Queue, lease: Lease, value: str) -> None:
    """Portfolio lock first; queue fence, economic effect and job result commit together."""
    if len(value.encode()) > 2 * 1024 * 1024:
        raise ValueError("Oversized fill preparation")
    prepared = PreparedFill.model_validate_json(value)
    payload = ScheduledFillPayload.model_validate(lease.payload)
    execution_build = engine_fingerprint()  # Filesystem reads precede financial locks.
    if prepared.execution_engine_version != execution_build:
        raise ValueError("Execution build changed after preparation")
    if prepared.payload != payload or (
        prepared.market.snapshot_id,
        prepared.market.snapshot_sha256,
        prepared.market.mode,
    ) != (payload.execution_snapshot_id, payload.execution_snapshot_sha256, payload.source_mode):
        raise ValueError("Prepared fill differs from admitted evidence")
    with Session(queue.engine) as session, session.begin():
        account = _locked(session, payload.portfolio_id)
        job, now = queue.owned(session, lease)
        if (
            job is None
            or job.status != "running"
            or job.attempt_deadline is None
            or job.attempt_deadline <= now
        ):
            raise PublicationFenceError("Fill lease/cancellation authority lost")
        batch = session.get(PaperOrderBatch, payload.batch_id)
        order = session.get(PaperOrder, payload.order_id)
        if (
            batch is None
            or order is None
            or batch.portfolio_id != account.id
            or order.batch_id != batch.id
            or (batch.snapshot_id, batch.snapshot_sha256, account.source_mode)
            != (payload.decision_snapshot_id, payload.decision_snapshot_sha256, payload.source_mode)
        ):
            raise LedgerConflict("Fill job linkage differs from immutable approval")
        observation = payload.fixture_observed_at or prepared.observed_at
        if prepared.observed_at != observation or (
            payload.fixture_observed_at is None and prepared.observed_at > now
        ):
            raise ValueError("Fill observation clock is invalid")
        eligible = next_eligible_session(
            prepared.calendar, batch.decision_cutoff, batch.approved_at
        )
        if eligible.session_date != payload.eligible_session or order.asset_id != payload.asset_id:
            raise LedgerConflict("Order/session differs from approved job")
        original = session.get(DatasetSnapshot, payload.decision_snapshot_id)
        execution = session.get(DatasetSnapshot, payload.execution_snapshot_id)
        if (
            original is None
            or execution is None
            or (
                original.manifest_hash != payload.decision_snapshot_sha256
                or execution.manifest_hash != payload.execution_snapshot_sha256
                or original.source_mode != payload.source_mode
                or execution.source_mode != payload.source_mode
                or original.quality == "blocked"
                or execution.quality == "blocked"
            )
        ):
            raise LedgerConflict("Registered execution evidence differs from job")
        decision_manifest = SnapshotManifestV1.model_validate(original.manifest)
        execution_manifest = SnapshotManifestV1.model_validate(execution.manifest)
        if (decision_manifest.snapshot_id(), execution_manifest.snapshot_id()) != (
            original.id,
            execution.id,
        ):
            raise LedgerConflict("Registered snapshot manifests are inconsistent")
        context = ExecutionContext.model_validate(batch.context)
        if (
            decision_manifest.manifest_hash() != original.manifest_hash
            or execution_manifest.manifest_hash() != execution.manifest_hash
            or context.snapshot_id != batch.snapshot_id
            or context.snapshot_sha256 != batch.snapshot_sha256
            or context.calendar_sha256 != batch.calendar_sha256
            or calendar_digest(prepared.calendar) != batch.calendar_sha256
            or context.approved_at != batch.approved_at
            or context.decision_cutoff != batch.decision_cutoff
        ):
            raise LedgerConflict("Execution preparation differs from frozen approval")
        verify_execution_sources(
            decision_manifest,
            execution_manifest,
            prepared.calendar,
            prepared.execution_calendar,
            eligible,
            payload.asset_id,
        )
        if any(
            row.asset_id != payload.asset_id or row.session_date != eligible.session_date
            for row in prepared.market.bars
        ):
            raise ValueError("Preparation contains unrelated execution bars")
        before_revision = account.revision
        blocking_reason: str | None = None
        if not batch.terminal and not order.terminal:
            state = _check_projection(session, account)
            entitlements = {item.key: item for item in state.entitlements}
            phases = []
            for action in prepared.actions:
                if action.effective_session > eligible.session_date:
                    continue
                # Preserve ex-date holdings before later payable recognition.
                # _post_action rejects capture if intervening trades make it unsafe.
                phase = action.effective_session
                if action.kind == "dividend" and action_key(action) in entitlements:
                    phase = min(
                        action.payable_session or eligible.session_date, eligible.session_date
                    )
                phases.append((phase, action))
            held = {item.asset_id for item in state.positions}
            ambiguous = Counter((action.effective_session, action.asset_id) for _, action in phases)
            if any(count > 1 and asset in held for (_, asset), count in ambiguous.items()):
                raise LedgerConflict("Ambiguous same-session corporate-action order")
            for phase, action in sorted(
                phases, key=lambda item: (item[0], item[1].effective_session, action_key(item[1]))
            ):
                _post_action(
                    session,
                    account.id,
                    action=action,
                    snapshot_id=payload.execution_snapshot_id,
                    calendar=prepared.execution_calendar,
                    session_date=phase,
                    observed_at=observation,
                    live=payload.source_mode == "research_market_data",
                    execution_engine_version=execution_build,
                )
                if account.revision != before_revision:
                    break
                checked = apply_action(
                    _check_projection(session, account),
                    action,
                    session=phase,
                    observed_at=observation,
                    live=payload.source_mode == "research_market_data",
                    calendar=prepared.execution_calendar,
                )
                if checked.status == "pending" and checked.reason != "WAITING_FOR_PAYABLE_SESSION":
                    zero_entitlement = any(
                        item.key == action_key(action) and Decimal(item.quantity) == 0
                        for item in checked.state_after.entitlements
                    )
                    if not (action.kind == "dividend" and zero_entitlement):
                        blocking_reason = checked.reason or "UNRESOLVED_CORPORATE_ACTION"
                        break
            if blocking_reason is not None:
                order.reason = batch.reason = blocking_reason
            if account.revision == before_revision and blocking_reason is None:
                _post_order(
                    session,
                    order.id,
                    owner=account.id,
                    calendar=prepared.calendar,
                    execution_calendar=prepared.execution_calendar,
                    market=prepared.market,
                    observed_at=observation,
                    actions=prepared.actions,
                    execution_engine_version=execution_build,
                )
        # Recheck deadline after bounded validation/SQL, before publishing anything.
        job, finished = queue.owned(session, lease)
        if (
            job is None
            or job.status != "running"
            or job.attempt_deadline is None
            or job.attempt_deadline <= finished
        ):
            raise PublicationFenceError("Fill authority expired before commit")
        attempt = session.get(JobAttempt, (job.id, job.attempts))
        assert attempt is not None
        attempt.diagnostics = {**attempt.diagnostics, "execution_engine_version": execution_build}
        job.result = JobResult(
            kind="resource",
            resource_id=batch.id,
            message="Paper batch attempt committed; inspect batch for pending or terminal state.",
        ).model_dump(mode="json")
        job.status, job.progress = "completed", 100
        queue.finish_attempt(session, job, finished, "completed")


def enqueue_due_batches(queue: Queue) -> int:
    """Bounded oldest-first catch-up; fixtures retain their last explicit replay clock.

    An approval alone never invents a fixture future clock. A completed attempt's
    persisted clock lets restart continue remaining orders at that same instant.
    Semantic keys suppress repeated polls of unchanged evidence/state.
    """
    from backend.persistence.models.job import Job

    with Session(queue.engine) as session:
        candidates = list(
            session.execute(
                select(PaperOrderBatch.id, PaperOrderBatch.context)
                .where(~PaperOrderBatch.terminal)
                .order_by(PaperOrderBatch.eligible_open_at, PaperOrderBatch.id)
                .limit(queue.limits.catchup_batch)
            )
        )
        due: list[tuple[UUID, datetime | None]] = []
        for batch_id, context in candidates:
            clock = None
            if context["mode"] == "synthetic_fixture":
                prior = session.scalar(
                    select(Job)
                    .where(
                        Job.kind == "apply_scheduled_fills",
                        Job.payload["batch_id"].as_string() == str(batch_id),
                    )
                    .order_by(Job.created_at.desc(), Job.id.desc())
                    .limit(1)
                )
                if prior is None:
                    continue
                clock = ScheduledFillPayload.model_validate(prior.payload).fixture_observed_at
            due.append((batch_id, clock))
    count = 0
    for batch_id, clock in due:
        try:
            if enqueue_batch_attempt(queue, batch_id, fixture_observed_at=clock) is not None:
                count += 1
        except (ValueError, LookupError):
            # One invalid/reconciliation-blocked target cannot starve other jobs.
            # A DB outage is deliberately not swallowed: publication authority is lost.
            logging.getLogger(__name__).warning("paper_catchup_unavailable batch_id=%s", batch_id)

    return count
