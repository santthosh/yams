"""Private operator-authorization service; no HTTP shortcut or financial posting.

The caller loads a verified immutable snapshot before calling. #49 owns producing
recommendations; #50 owns public approval. Source files/network are never opened
while a portfolio lock is held.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import UUID, uuid5

from pydantic import Field, TypeAdapter, model_validator
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from backend.domain.orders import PaperOrderBatchV1, PaperOrderV1
from backend.domain.types import Contract, SourceMode, UTCTimestamp
from backend.market_data.files import PinnedSnapshot
from backend.market_data.models import Calendar
from backend.persistence.models.ledger import (
    LedgerEvent,
    PaperOrder,
    PaperOrderBatch,
    RecommendationReference,
)
from backend.persistence.models.snapshot import CurrentSnapshot, DatasetSnapshot
from backend.portfolio.execution import (
    DEFAULT_EXECUTION_POLICY,
    ExecutionContext,
    OrderIntent,
    calendar_digest,
    next_eligible_session,
)
from backend.portfolio.ledger import LedgerConflict, _append, _check_projection, _locked, digest
from backend.portfolio.paper_clock import operator_audit, operator_clock


class ApprovalIdempotencyConflict(LedgerConflict):
    """The original key refers to different immutable approval inputs."""


class StaleApprovalData(LedgerConflict):
    """The original decision source is stale or incompatible."""


class ApprovalIntegrityConflict(LedgerConflict):
    """Original immutable content differs from its recorded digest."""


class NoExecutableOrders(LedgerConflict):
    """A legitimate HOLD/cash recommendation has no batch to authorize."""


class ExecutionIntentV1(Contract):
    """Immutable internal recommendation content, separate from its public view."""

    schema_version: Literal[1] = 1
    engine_version: Annotated[str, Field(strict=True, min_length=1)]
    orders: Annotated[tuple[OrderIntent, ...], Field(min_length=1, max_length=1000)]

    @model_validator(mode="after")
    def unique(self) -> Self:
        if len({row.key for row in self.orders}) != len(self.orders):
            raise ValueError("Duplicate order identity")
        if len({row.asset_id for row in self.orders}) != len(self.orders):
            raise ValueError("An asset may have only one approved intent")
        if any(Decimal(row.requested_quantity) <= 0 for row in self.orders):
            raise ValueError("Approved orders must have positive quantity")
        return self


def _retry(session: Session, owner: UUID, key: UUID, request_hash: str) -> UUID | None:
    prior = session.scalar(
        select(PaperOrderBatch).where(
            PaperOrderBatch.portfolio_id == owner, PaperOrderBatch.idempotency_key == key
        )
    )
    if prior is None:
        return None
    if prior.request_sha256 != request_hash:
        raise ApprovalIdempotencyConflict("Approval idempotency key refers to different inputs")
    return prior.id


def approve_batch(
    engine: Engine,
    portfolio_id: UUID,
    recommendation_id: UUID,
    *,
    expected_revision: int,
    idempotency_key: UUID,
    pinned: PinnedSnapshot | None = None,
    approved_at: datetime | None = None,
    server_clock: bool = False,
) -> UUID:
    """Approve stored intent once; unchanged cash/holdings, one active reservation.

    `approved_at` is a trusted server-owned clock seam for explicit fixture replay,
    never an HTTP backdating field. Research approvals always use current UTC.
    Exact retry precedes freshness/revision checks and preserves the original time.
    """
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError("Expected revision must be a nonnegative integer")
    command = dict(
        portfolio_id=str(portfolio_id),
        recommendation_id=str(recommendation_id),
        expected_revision=expected_revision,
    )
    request_hash = digest(command)
    with Session(engine) as session:
        prior = _retry(session, portfolio_id, idempotency_key, request_hash)
        if prior is not None:
            return prior
    if pinned is None:
        raise LedgerConflict("New approval requires verified decision evidence")
    manifest = pinned.manifest
    mode: SourceMode = manifest.mode
    if mode != "synthetic_fixture" and approved_at is not None:
        raise ValueError("Research approval cannot override the operator approval clock")
    now = TypeAdapter(UTCTimestamp).validate_python(approved_at or datetime.now(UTC))
    calendar = Calendar.model_validate_json(pinned.artifacts[manifest.calendar.artifact_path])
    if calendar_digest(calendar) != manifest.calendar.version or manifest.quality == "blocked":
        raise StaleApprovalData("Decision snapshot/calendar is unavailable")
    # Current providers do not support complete action/raw execution accounting.
    # No schema or approval operation may silently promote their capabilities.
    if mode != "synthetic_fixture":
        raise LedgerConflict("Unsupported accounting source")
    with Session(engine) as session, session.begin():
        account = _locked(session, portfolio_id)
        prior = _retry(session, portfolio_id, idempotency_key, request_hash)
        if prior is not None:
            return prior
        before = _check_projection(session, account)
        latest = session.scalar(
            select(LedgerEvent.recorded_at)
            .where(LedgerEvent.portfolio_id == account.id)
            .order_by(LedgerEvent.sequence.desc())
            .limit(1)
        )
        if not server_clock and latest is not None and now < latest:
            raise LedgerConflict("Operator clock precedes posted history")

        if account.status != "active" or account.revision != expected_revision:
            raise LedgerConflict("Portfolio revision/state changed; reevaluate")
        if (
            session.scalar(
                select(PaperOrderBatch.id).where(
                    PaperOrderBatch.portfolio_id == portfolio_id, ~PaperOrderBatch.terminal
                )
            )
            is not None
        ):
            raise LedgerConflict("Portfolio already has an active reservation")
        rec = session.scalar(
            select(RecommendationReference)
            .where(RecommendationReference.id == recommendation_id)
            .with_for_update()
        )
        if rec is None:
            raise LookupError("Recommendation does not exist")
        actual = None
        if server_clock:
            if approved_at is not None:
                raise ValueError("Server-owned approval cannot accept a caller timestamp")
            now, actual = operator_clock(
                session, portfolio_id, mode, max(rec.created_at, rec.decision_cutoff)
            )
        registered = session.get(DatasetSnapshot, rec.snapshot_id)
        current = session.get(CurrentSnapshot, mode)
        if digest(rec.content) != rec.content_sha256:
            raise ApprovalIntegrityConflict("Recommendation immutable content is unavailable")
        if (
            rec.portfolio_id != portfolio_id
            or rec.strategy_version_id != account.strategy_version_id
            or rec.portfolio_revision != expected_revision
            or rec.disposition != "ready"
            or rec.source_mode != account.source_mode
            or rec.source_mode != mode
            or rec.created_at > now
            or rec.decision_cutoff > now
        ):
            raise LedgerConflict("Recommendation is obsolete or incompatible")
        if (
            registered is None
            or registered.id != manifest.snapshot_id()
            or registered.manifest_hash != manifest.manifest_hash()
            or registered.manifest != manifest.model_dump(mode="json")
            or registered.quality == "blocked"
            or current is None
            or current.snapshot_id != registered.id
        ):
            raise StaleApprovalData("Recommendation source is stale or incompatible")
        if (
            rec.content.get("execution_intent") is None
            and "recommendation_canonical_json" in rec.content
        ):
            raise NoExecutableOrders("Recommendation has no executable orders to approve")
        intent = ExecutionIntentV1.model_validate(rec.content.get("execution_intent"))
        if any(row.asset_id not in manifest.coverage.asset_ids for row in intent.orders):
            raise StaleApprovalData("Approved asset is absent from decision source")
        decision = next(
            (row for row in calendar.sessions if row.session_date == rec.as_of_session), None
        )
        if decision is None or rec.decision_cutoff < decision.close_at:
            raise LedgerConflict("Recommendation cutoff precedes its decision session")
        eligible = next_eligible_session(calendar, rec.decision_cutoff, now)
        context = ExecutionContext(
            snapshot_id=registered.id,
            snapshot_sha256=registered.manifest_hash,
            calendar_sha256=calendar_digest(calendar),
            mode=mode,
            engine_version=intent.engine_version,
            execution_mode="historical_replay",
            decision_session=rec.as_of_session,
            decision_cutoff=rec.decision_cutoff,
            approved_at=now,
        )
        ordered = tuple(
            sorted(
                intent.orders,
                key=lambda row: (0 if row.side == "SELL" else 1, row.asset_id, row.key),
            )
        )
        approved = {"orders": [row.model_dump(mode="json") for row in ordered]}
        identity = uuid5(portfolio_id, "approval:" + str(idempotency_key))
        batch = PaperOrderBatch(
            id=identity,
            portfolio_id=portfolio_id,
            recommendation_id=rec.id,
            strategy_version_id=rec.strategy_version_id,
            snapshot_id=registered.id,
            snapshot_sha256=registered.manifest_hash,
            calendar_sha256=context.calendar_sha256,
            approved_revision=expected_revision,
            approved_at=now,
            decision_cutoff=rec.decision_cutoff,
            eligible_open_at=eligible.open_at,
            idempotency_key=idempotency_key,
            request_sha256=request_hash,
            intent=approved,
            intent_sha256=digest(approved),
            context=context.model_dump(mode="json"),
            policy=DEFAULT_EXECUTION_POLICY.model_dump(mode="json"),
            status="pending",
            terminal=False,
            reason="AWAITING_ELIGIBLE_OPEN",
            created_at=now,
        )
        session.add(batch)
        session.flush()
        for ordinal, row in enumerate(ordered):
            session.add(
                PaperOrder(
                    id=uuid5(identity, row.key),
                    batch_id=identity,
                    ordinal=ordinal,
                    asset_id=row.asset_id,
                    sector=row.sector,
                    side=row.side,
                    intent_key=row.key,
                    requested_quantity=Decimal(row.requested_quantity),
                    filled_quantity=Decimal("0"),
                    pending_quantity=Decimal(row.requested_quantity),
                    closed_quantity=Decimal("0"),
                    status="pending",
                    terminal=False,
                    reason="AWAITING_ELIGIBLE_OPEN",
                )
            )
        rec.disposition = "applied"
        _append(
            session,
            account,
            key="approval:" + str(idempotency_key),
            kind="batch_approval",
            before=before,
            after=before,
            command=command | {"batch_id": str(identity)},
            recorded_at=now,
            effective_at=now,
            snapshot_id=registered.id,
            details=operator_audit(actual),
        )
        session.flush()
        return identity


def cancel_batch(
    engine: Engine,
    batch_id: UUID,
    *,
    cancelled_at: datetime | None = None,
    server_clock: bool = False,
) -> UUID:
    """Close only outstanding intent; any committed fills remain immutable."""
    now = TypeAdapter(UTCTimestamp).validate_python(cancelled_at or datetime.now(UTC))
    with Session(engine) as session:
        owner = session.scalar(
            select(PaperOrderBatch.portfolio_id).where(PaperOrderBatch.id == batch_id)
        )
    if owner is None:
        raise LookupError("Paper batch does not exist")
    with Session(engine) as session, session.begin():
        account = _locked(session, owner)
        batch = session.scalar(
            select(PaperOrderBatch).where(PaperOrderBatch.id == batch_id).with_for_update()
        )
        assert batch is not None
        if batch.terminal:
            return batch.id
        before = _check_projection(session, account)
        actual = None
        if server_clock:
            if cancelled_at is not None:
                raise ValueError("Server-owned cancellation cannot accept a caller timestamp")
            now, actual = operator_clock(
                session,
                owner,
                TypeAdapter(SourceMode).validate_python(account.source_mode),
                batch.approved_at,
            )
        latest = session.scalar(
            select(LedgerEvent.recorded_at)
            .where(LedgerEvent.portfolio_id == account.id)
            .order_by(LedgerEvent.sequence.desc())
            .limit(1)
        )
        if latest is not None and now < latest:
            raise LedgerConflict("Operator clock precedes posted history")

        orders = list(
            session.scalars(
                select(PaperOrder)
                .where(PaperOrder.batch_id == batch_id)
                .order_by(PaperOrder.id)
                .with_for_update()
            )
        )
        for row in orders:
            if not row.terminal:
                row.closed_quantity += row.pending_quantity
                row.pending_quantity = Decimal("0")
                row.terminal = True
                row.status = "partially_filled" if row.filled_quantity > 0 else "cancelled"
                row.reason = "OPERATOR_CANCELLED"
        batch.terminal = True
        batch.status = (
            "partially_filled" if any(row.filled_quantity > 0 for row in orders) else "cancelled"
        )
        batch.reason = "OPERATOR_CANCELLED"
        _append(
            session,
            account,
            key="cancel:" + str(batch_id),
            kind="batch_cancel",
            before=before,
            after=before,
            command={"batch_id": str(batch_id)},
            recorded_at=now,
            effective_at=now,
            snapshot_id=batch.snapshot_id,
            details=operator_audit(actual),
        )
        session.flush()
        return batch.id


def read_batch(engine: Engine, batch_id: UUID) -> PaperOrderBatchV1:
    """Typed private state for the owning future HTTP transport; never posts."""
    with Session(engine) as session:
        owner = session.scalar(
            select(PaperOrderBatch.portfolio_id).where(PaperOrderBatch.id == batch_id)
        )
    if owner is None:
        raise LookupError("Paper batch does not exist")
    with Session(engine) as session, session.begin():
        _locked(session, owner)
        batch = session.get(PaperOrderBatch, batch_id)
        assert batch is not None
        orders = list(
            session.scalars(
                select(PaperOrder)
                .where(PaperOrder.batch_id == batch_id)
                .order_by(PaperOrder.ordinal)
            )
        )
        return batch_view(batch, orders)


def batch_view(batch: PaperOrderBatch, orders: list[PaperOrder]) -> PaperOrderBatchV1:
    """Map rows already read under the caller's portfolio lock."""
    return PaperOrderBatchV1.model_validate(
        dict(
            id=batch.id,
            portfolio_id=batch.portfolio_id,
            recommendation_id=batch.recommendation_id,
            approval_idempotency_key=batch.idempotency_key,
            approved_revision=batch.approved_revision,
            approved_at=batch.approved_at,
            decision_cutoff_utc=batch.decision_cutoff,
            snapshot_id=batch.snapshot_id,
            calendar_version=batch.calendar_sha256,
            execution_policy_id=batch.policy["id"],
            eligible_open_at=batch.eligible_open_at,
            status=batch.status,
            terminal=batch.terminal,
            reason=batch.reason,
            orders=tuple(
                PaperOrderV1.model_validate(
                    dict(
                        id=row.id,
                        asset_id=row.asset_id,
                        side=row.side,
                        requested_quantity=format(row.requested_quantity, ".6f"),
                        filled_quantity=format(row.filled_quantity, ".6f"),
                        pending_quantity=format(row.pending_quantity, ".6f"),
                        cancelled_or_skipped_quantity=format(row.closed_quantity, ".6f"),
                        earliest_fill_session=batch.eligible_open_at.date(),
                        status=row.status,
                        terminal=row.terminal,
                        reason=row.reason,
                    )
                )
                for row in orders
            ),
        )
    )
