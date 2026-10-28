"""Transactional paper ledger. Private services; no HTTP approval or price inputs.

Every writer locks the account first. Immutable transitions and exact signed
entries are committed with projections; replay starts at zero, never at funding.
"""

import hashlib
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID, uuid5

from pydantic import TypeAdapter
from sqlalchemy import Engine, delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.domain.market import SnapshotManifestV1
from backend.domain.strategy import StrategyConfigV1
from backend.domain.types import Money, UTCTimestamp, canonical_json
from backend.market_data.models import Calendar, CorporateAction
from backend.persistence.models.ledger import (
    ActionEvidence,
    CashEntry,
    LedgerEvent,
    PaperFill,
    PaperOrder,
    PaperOrderBatch,
    PositionEvent,
    RecommendationReference,
)
from backend.persistence.models.portfolio import PaperPortfolio, PaperPosition
from backend.persistence.models.snapshot import DatasetSnapshot
from backend.persistence.models.strategy import StrategyVersion
from backend.portfolio.corporate_actions import action_hash, action_key, apply_action
from backend.portfolio.execution import (
    ExecutionContext,
    ExecutionPolicy,
    MarketEvidence,
    OrderIntent,
    PortfolioState,
    Position,
    arithmetic,
    calendar_digest,
    execute_order,
    money,
    quantity,
    verify_context,
)


class LedgerConflict(ValueError):
    """An immutable command identity was reused with different intent."""


class ReconciliationFailure(ValueError):
    """Evidence or projections differ. New posting is blocked until verified repair."""


@dataclass(frozen=True)
class LedgerView:
    portfolio_id: UUID
    revision: int
    last_sequence: int
    state: PortfolioState
    reconciliation_failed: bool


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _metadata(state: PortfolioState) -> dict[str, Any]:
    payload = state.model_dump(mode="json")
    return {key: payload[key] for key in ("applied_actions", "entitlements")}


def _projection(session: Session, account: PaperPortfolio) -> PortfolioState:
    rows = session.scalars(
        select(PaperPosition)
        .where(PaperPosition.portfolio_id == account.id)
        .order_by(PaperPosition.asset_id)
    )
    return PortfolioState.model_validate(
        {
            "cash_usd": format(account.cash_usd, ".2f"),
            "positions": [
                {
                    "asset_id": row.asset_id,
                    "sector": row.sector,
                    "quantity": format(row.quantity, ".6f"),
                    "total_basis_usd": format(row.total_basis_usd, ".2f"),
                }
                for row in rows
            ],
            **account.state_metadata,
        }
    )


def _locked(session: Session, identity: UUID) -> PaperPortfolio:
    account = session.scalar(
        select(PaperPortfolio).where(PaperPortfolio.id == identity).with_for_update()
    )
    if account is None:
        raise LookupError("Paper portfolio does not exist")
    return account


def _view(session: Session, account: PaperPortfolio) -> LedgerView:
    return LedgerView(
        account.id,
        account.revision,
        account.last_sequence,
        _projection(session, account),
        account.reconciliation_failed,
    )


def _check_projection(session: Session, account: PaperPortfolio) -> PortfolioState:
    if account.reconciliation_failed:
        raise ReconciliationFailure("Paper portfolio requires reconciliation")
    state = _projection(session, account)
    latest = session.scalar(
        select(LedgerEvent).where(
            LedgerEvent.portfolio_id == account.id,
            LedgerEvent.sequence == account.last_sequence,
        )
    )
    if (
        latest is None
        or digest(latest.payload) != latest.payload_sha256
        or latest.payload["after"] != state.model_dump(mode="json")
        or latest.portfolio_revision != account.revision
    ):
        raise ReconciliationFailure("Projection differs from immutable ledger boundary")
    return state


def _existing(
    session: Session, identity: UUID, key: str, command_sha256: str
) -> LedgerEvent | None:
    event = session.scalar(
        select(LedgerEvent).where(
            LedgerEvent.portfolio_id == identity, LedgerEvent.event_key == key
        )
    )
    if event is not None and event.payload["command_sha256"] != command_sha256:
        raise LedgerConflict("Event identity already has different immutable intent")
    return event


def _project(
    session: Session, account: PaperPortfolio, state: PortfolioState, sequence: int
) -> None:
    # Projections are replaceable. Posted entries/evidence are never modified.
    session.execute(delete(PaperPosition).where(PaperPosition.portfolio_id == account.id))
    for position in state.positions:
        session.add(
            PaperPosition(
                portfolio_id=account.id,
                asset_id=position.asset_id,
                sector=position.sector,
                quantity=Decimal(position.quantity),
                total_basis_usd=Decimal(position.total_basis_usd),
                last_sequence=sequence,
            )
        )
    account.cash_usd = Decimal(state.cash_usd)
    account.state_metadata = _metadata(state)
    account.last_sequence = sequence


def _append(
    session: Session,
    account: PaperPortfolio,
    *,
    key: str,
    kind: str,
    before: PortfolioState,
    after: PortfolioState,
    command: dict[str, Any],
    recorded_at: datetime,
    effective_at: datetime,
    cash_entry: bool = False,
    order_id: UUID | None = None,
    action_evidence_id: UUID | None = None,
    correction_target_id: UUID | None = None,
    snapshot_id: UUID | None = None,
    details: dict[str, Any] | None = None,
) -> LedgerEvent:
    """Caller owns lock, semantic authorization and surrounding transaction."""
    payload = {
        "before": before.model_dump(mode="json"),
        "after": after.model_dump(mode="json"),
        "command_sha256": digest(command),
        "command": command,
        "details": details or {},
    }
    event = LedgerEvent(
        id=uuid5(account.id, key),
        portfolio_id=account.id,
        sequence=account.last_sequence + 1,
        portfolio_revision=account.revision + 1,
        kind=kind,
        event_key=key,
        payload_sha256=digest(payload),
        recorded_at=recorded_at,
        effective_at=effective_at,
        order_id=order_id,
        action_evidence_id=action_evidence_id,
        correction_target_id=correction_target_id,
        snapshot_id=snapshot_id,
        strategy_version_id=account.strategy_version_id,
        payload=payload,
    )
    session.add(event)
    session.flush()
    with arithmetic(before.cash_usd, after.cash_usd):
        if cash_entry:
            session.add(
                CashEntry(
                    id=uuid5(event.id, "cash"),
                    event_id=event.id,
                    purpose=kind,
                    delta_usd=Decimal(after.cash_usd) - Decimal(before.cash_usd),
                )
            )
        prior = {row.asset_id: row for row in before.positions}
        following = {row.asset_id: row for row in after.positions}
        for asset in sorted(prior.keys() | following.keys()):
            old, new = prior.get(asset), following.get(asset)
            qty = Decimal(new.quantity if new else "0") - Decimal(old.quantity if old else "0")
            basis = Decimal(new.total_basis_usd if new else "0") - Decimal(
                old.total_basis_usd if old else "0"
            )
            if qty or basis:
                position = new or old
                assert position is not None
                session.add(
                    PositionEvent(
                        id=uuid5(event.id, asset),
                        event_id=event.id,
                        asset_id=asset,
                        sector=position.sector,
                        quantity_delta=qty,
                        basis_delta_usd=basis,
                    )
                )
    account.revision = event.portfolio_revision
    _project(session, account, after, event.sequence)
    session.flush()
    return event


def create_portfolio(
    engine: Engine,
    *,
    portfolio_id: UUID,
    workspace_id: UUID,
    strategy_version_id: UUID,
    name: str,
    opening_cash_usd: str = "1000.00",
    created_at: datetime,
) -> LedgerView:
    """Fund an independently identified account exactly once, without holdings."""
    amount = TypeAdapter(Money).validate_python(opening_cash_usd)
    timestamp = TypeAdapter(UTCTimestamp).validate_python(created_at)
    if Decimal(amount) <= 0:
        raise ValueError("Opening paper cash must be positive")
    if (
        not isinstance(name, str)
        or name != name.strip()
        or not 1 <= len(name) <= 120
        or any(unicodedata.category(char) in {"Cc", "Cs"} for char in name)
    ):
        raise ValueError("Portfolio name must be trimmed text of 1–120 characters")
    after = PortfolioState(cash_usd=format(Decimal(amount), ".2f"), positions=())
    command = {
        "workspace_id": str(workspace_id),
        "strategy_version_id": str(strategy_version_id),
        "name": name,
        "opening_cash_usd": after.cash_usd,
    }
    fingerprint = digest(command)
    with Session(engine) as session, session.begin():
        if session.get(StrategyVersion, strategy_version_id) is None:
            raise LookupError("Published strategy version does not exist")
        # INSERT serializes concurrent first delivery on the account PK. Losing
        # delivery locks the committed row and resolves semantic retry first.
        inserted = session.execute(
            insert(PaperPortfolio)
            .values(
                id=portfolio_id,
                workspace_id=workspace_id,
                name=name,
                currency="USD",
                strategy_version_id=strategy_version_id,
                opening_cash_usd=Decimal(after.cash_usd),
                opening_event_id=uuid5(portfolio_id, "opening_funding"),
                opening_sha256=fingerprint,
                cash_usd=Decimal(after.cash_usd),
                revision=0,
                last_sequence=0,
                status="active",
                reconciliation_failed=False,
                state_metadata=_metadata(after),
                created_at=timestamp,
            )
            .on_conflict_do_nothing(index_elements=[PaperPortfolio.id])
            .returning(PaperPortfolio.id)
        ).scalar_one_or_none()
        account = _locked(session, portfolio_id)
        if account.opening_sha256 != fingerprint:
            raise LedgerConflict("Portfolio identity already has different opening intent")
        if inserted is not None:
            _append(
                session,
                account,
                key="opening_funding",
                kind="opening_funding",
                before=PortfolioState(cash_usd="0.00", positions=()),
                after=after,
                command=command,
                recorded_at=timestamp,
                effective_at=timestamp,
                cash_entry=True,
            )
        else:
            _check_projection(session, account)
        return _view(session, account)


def read_portfolio(engine: Engine, identity: UUID) -> LedgerView:
    with Session(engine) as session, session.begin():
        account = _locked(session, identity)
        return _view(session, account)


def _fold(session: Session, account: PaperPortfolio) -> PortfolioState:
    """Reconstruct from immutable signed effects, validating each sealed boundary."""
    state = PortfolioState(cash_usd="0.00", positions=())
    expected_sequence = 1
    prior_revision = 0
    for event in session.scalars(
        select(LedgerEvent)
        .where(LedgerEvent.portfolio_id == account.id)
        .order_by(LedgerEvent.sequence)
    ):
        if (
            event.sequence != expected_sequence
            or event.portfolio_revision <= prior_revision
            or event.payload_sha256 != digest(event.payload)
            or event.payload["before"] != state.model_dump(mode="json")
            or (event.sequence == 1 and event.kind != "opening_funding")
        ):
            raise ReconciliationFailure("Immutable ledger sequence/hash/transition differs")
        cash = Decimal(state.cash_usd)
        positions = {row.asset_id: row for row in state.positions}
        with arithmetic(state.cash_usd):
            for entry in session.scalars(select(CashEntry).where(CashEntry.event_id == event.id)):
                cash += entry.delta_usd
            for effect in session.scalars(
                select(PositionEvent).where(PositionEvent.event_id == event.id)
            ):
                old = positions.get(effect.asset_id)
                shares = Decimal(old.quantity if old else "0") + effect.quantity_delta
                basis = Decimal(old.total_basis_usd if old else "0") + effect.basis_delta_usd
                if shares < 0 or basis < 0 or (not shares and basis):
                    raise ReconciliationFailure("Replay creates invalid shares or basis")
                if shares:
                    positions[effect.asset_id] = Position(
                        asset_id=effect.asset_id,
                        sector=effect.sector,
                        quantity=quantity(shares),
                        total_basis_usd=money(basis),
                    )
                else:
                    positions.pop(effect.asset_id, None)
            if cash < 0:
                raise ReconciliationFailure("Replay creates negative cash")
            after = PortfolioState.model_validate(event.payload["after"])
            rebuilt = PortfolioState(
                cash_usd=money(cash),
                positions=tuple(positions[key] for key in sorted(positions)),
                applied_actions=after.applied_actions,
                entitlements=after.entitlements,
            )
        if rebuilt != after:
            raise ReconciliationFailure("Signed entries differ from sealed transition")
        state = rebuilt
        prior_revision = event.portfolio_revision
        expected_sequence += 1
    if expected_sequence == 1:
        raise ReconciliationFailure("Opening funding is missing")
    return state


def reconcile(engine: Engine, identity: UUID, *, rebuild: bool = False) -> LedgerView:
    """Mark mismatch durably; repair projections only after full evidence validation."""
    failure: ReconciliationFailure | None = None
    with Session(engine) as session, session.begin():
        account = _locked(session, identity)
        try:
            state = _fold(session, account)
            latest = session.scalar(
                select(LedgerEvent)
                .where(LedgerEvent.portfolio_id == identity)
                .order_by(LedgerEvent.sequence.desc())
                .limit(1)
            )
            assert latest is not None
            matches = (
                state == _projection(session, account)
                and account.last_sequence == latest.sequence
                and account.revision == latest.portfolio_revision
            )
            if not matches and not rebuild:
                raise ReconciliationFailure("Projection differs from full ledger replay")
            if rebuild:
                _project(session, account, state, latest.sequence)
                account.revision = latest.portfolio_revision
            account.reconciliation_failed = False
        except (ReconciliationFailure, ValueError) as exc:
            account.reconciliation_failed = True
            failure = ReconciliationFailure(str(exc))
        session.flush()
        result = _view(session, account)
    if failure is not None:
        raise failure
    return result


def post_order(
    engine: Engine,
    order_id: UUID,
    *,
    calendar: Calendar,
    market: MarketEvidence,
    observed_at: datetime,
    actions: tuple[CorporateAction, ...] = (),
) -> UUID | None:
    """Post one authorized order using preloaded, verified backend evidence.

    The worker must obtain calendar/bars from its pinned MarketRepository, never
    HTTP prices. This boundary binds that evidence to durable snapshot/approval
    lineage and recalculates effects on the locked state. No I/O under the lock.
    Missing evidence remains pending; terminal outcomes return their stable event.
    """
    timestamp = TypeAdapter(UTCTimestamp).validate_python(observed_at)
    with Session(engine) as session:
        row = session.get(PaperOrder, order_id)
        if row is None:
            raise LookupError("Paper order does not exist")
        owner = session.scalar(
            select(PaperOrderBatch.portfolio_id).where(PaperOrderBatch.id == row.batch_id)
        )
        assert owner is not None
    with Session(engine) as session, session.begin():
        account = _locked(session, owner)
        batch = session.scalar(
            select(PaperOrderBatch).where(PaperOrderBatch.id == row.batch_id).with_for_update()
        )
        order = session.scalar(
            select(PaperOrder).where(PaperOrder.id == order_id).with_for_update()
        )
        assert batch is not None and order is not None
        context = ExecutionContext.model_validate(batch.context)
        policy = ExecutionPolicy.model_validate(batch.policy)
        eligible = verify_context(context, calendar, market)
        key = "execution:" + digest(
            [str(order_id), policy.id, eligible.session_date.isoformat(), 0]
        )
        # Refresh observation time and additional unrelated bars are not new
        # economic commands. Only the order's eligible raw bar is fingerprinted.
        bar = next(
            (
                b
                for b in market.bars
                if b.asset_id == order.asset_id and b.session_date == eligible.session_date
            ),
            None,
        )
        command = {
            "order_id": str(order_id),
            "intent_sha256": batch.intent_sha256,
            "context": batch.context,
            "policy": batch.policy,
            "bar": bar.model_dump(mode="json") if bar else None,
        }
        previous = _existing(session, account.id, key, digest(command))
        if previous is not None:
            return previous.id
        if order.terminal or batch.terminal:
            return None  # Cancellation/rejection is retained; never resurrect intent.
        before = _check_projection(session, account)
        if account.status != "active":
            raise LedgerConflict("Paper portfolio is not active")
        snapshot = session.get(DatasetSnapshot, batch.snapshot_id)
        recommendation = session.get(RecommendationReference, batch.recommendation_id)
        version = session.get(StrategyVersion, batch.strategy_version_id)
        if (
            snapshot is None
            or recommendation is None
            or version is None
            or snapshot.manifest_hash != context.snapshot_sha256
            or snapshot.id != context.snapshot_id
            or snapshot.source_mode != context.mode
            or snapshot.quality == "blocked"
            or batch.snapshot_sha256 != context.snapshot_sha256
            or batch.calendar_sha256 != context.calendar_sha256
            or batch.approved_at != context.approved_at
            or batch.decision_cutoff != context.decision_cutoff
            or batch.eligible_open_at != eligible.open_at
            or batch.strategy_version_id != account.strategy_version_id
            or recommendation.disposition != "applied"
            or recommendation.portfolio_revision != batch.approved_revision
            or recommendation.decision_cutoff != context.decision_cutoff
            or recommendation.as_of_session != context.decision_session
            or recommendation.source_mode != context.mode
            or digest(batch.intent) != batch.intent_sha256
            or digest(recommendation.content) != recommendation.content_sha256
        ):
            raise LedgerConflict("Approved execution lineage does not match pinned evidence")
        manifest = SnapshotManifestV1.model_validate(snapshot.manifest)
        if (
            manifest.manifest_hash() != snapshot.manifest_hash
            or manifest.snapshot_id() != snapshot.id
            or manifest.calendar.version != calendar_digest(calendar)
            or order.asset_id not in manifest.coverage.asset_ids
        ):
            raise LedgerConflict("Registered snapshot identity/calendar/asset differs")
        authorized = TypeAdapter(tuple[OrderIntent, ...]).validate_python(batch.intent["orders"])
        stored = list(
            session.scalars(
                select(PaperOrder)
                .where(PaperOrder.batch_id == batch.id)
                .order_by(PaperOrder.ordinal)
            )
        )
        actual = tuple(
            OrderIntent.model_validate(
                {
                    "key": item.intent_key,
                    "asset_id": item.asset_id,
                    "sector": item.sector,
                    "side": item.side,
                    "requested_quantity": format(item.requested_quantity, ".6f"),
                }
            )
            for item in stored
        )
        if (
            len({item.key for item in authorized}) != len(authorized)
            or any(
                a.model_dump(exclude={"requested_quantity"})
                != b.model_dump(exclude={"requested_quantity"})
                or Decimal(a.requested_quantity) != Decimal(b.requested_quantity)
                for a, b in zip(actual, authorized, strict=False)
            )
            or len(actual) != len(authorized)
        ):
            raise LedgerConflict("Persisted orders differ from immutable approved intent")
        # Proceeds are usable only after the sell stage has durably resolved.
        if (
            order.side == "BUY"
            and session.scalar(
                select(PaperOrder.id)
                .where(
                    PaperOrder.batch_id == batch.id, PaperOrder.side == "SELL", ~PaperOrder.terminal
                )
                .limit(1)
            )
            is not None
        ):
            return None
        # Caller supplies the complete verified action set for this snapshot.
        # An unprocessed action must not be skipped just because a raw open exists.
        applied = {item.key: item.payload_sha256 for item in before.applied_actions}
        for action in actions:
            if (
                action.asset_id == order.asset_id
                and action.effective_session <= eligible.session_date
                and action.visible(timestamp, context.execution_mode == "current_paper")
            ):
                key_hash = applied.get(action_key(action))
                if key_hash is not None and key_hash != action_hash(action):
                    raise LedgerConflict("Revised action requires explicit correction")
                if action.kind == "split" and key_hash is None:
                    return None
                if action.kind == "dividend" and (
                    not any(item.key == action_key(action) for item in before.entitlements)
                    or (
                        action.payable_session is not None
                        and action.payable_session <= eligible.session_date
                        and key_hash is None
                    )
                ):
                    return None
        phase = sorted(
            session.scalars(
                select(PaperOrder).where(PaperOrder.batch_id == batch.id, ~PaperOrder.terminal)
            ),
            key=lambda item: (0 if item.side == "SELL" else 1, item.asset_id, item.ordinal),
        )
        if phase and phase[0].id != order.id:
            return None
        config = StrategyConfigV1.model_validate(version.config)
        result = execute_order(
            before,
            OrderIntent(
                key=order.intent_key,
                asset_id=order.asset_id,
                sector=order.sector,
                side=TypeAdapter(Literal["BUY", "SELL"]).validate_python(order.side),
                requested_quantity=format(order.requested_quantity, ".6f"),
            ),
            context,
            calendar,
            market,
            observed_at=timestamp,
            min_trade_usd=config.portfolio.min_trade_usd,
            policy=policy,
        )
        if not result.terminal:
            order.reason = result.reason
            return None
        event = _append(
            session,
            account,
            key=key,
            kind="fill" if result.fill else "order_closed",
            before=before,
            after=result.state_after,
            command=command,
            recorded_at=timestamp,
            effective_at=result.fill.execution_at if result.fill else timestamp,
            cash_entry=result.fill is not None,
            order_id=order.id,
            snapshot_id=batch.snapshot_id,
            details={"execution": result.model_dump(mode="json")},
        )
        if result.fill is not None:
            fill = result.fill
            session.add(
                PaperFill(
                    id=uuid5(event.id, "fill"),
                    order_id=order.id,
                    event_id=event.id,
                    fill_event_key=key,
                    execution_session=fill.execution_session,
                    raw_price=Decimal(fill.raw_price),
                    executed_price=Decimal(fill.executed_price),
                    quantity=Decimal(fill.quantity),
                    gross_usd=Decimal(fill.gross_usd),
                    fee_usd=Decimal(fill.commission_usd),
                    slippage_usd=Decimal(fill.slippage_usd),
                    cash_delta_usd=Decimal(fill.cash_delta_usd),
                    removed_basis_usd=Decimal(fill.removed_basis_usd),
                    realized_pnl_usd=Decimal(fill.realized_pnl_usd),
                    posted_at=timestamp,
                )
            )
        order.filled_quantity = Decimal(result.filled_quantity)
        order.pending_quantity = Decimal(result.pending_quantity)
        order.closed_quantity = Decimal(result.skipped_quantity)
        order.terminal = result.terminal
        order.status = "rejected" if result.status == "skipped" else result.status
        order.reason = result.reason
        session.flush()
        orders = list(session.scalars(select(PaperOrder).where(PaperOrder.batch_id == batch.id)))
        batch.terminal = all(item.terminal for item in orders)
        if batch.terminal:
            batch.status = (
                "filled"
                if all(item.status == "filled" for item in orders)
                else "partially_filled"
                if any(item.filled_quantity > 0 for item in orders)
                else "rejected"
            )
        elif any(item.filled_quantity > 0 for item in orders):
            batch.status = "partially_filled"
        session.flush()
        return event.id


def post_action(
    engine: Engine,
    identity: UUID,
    *,
    snapshot_id: UUID,
    action: CorporateAction,
    calendar: Calendar,
    session_date: date,
    observed_at: datetime,
    live: bool,
) -> UUID | None:
    """Apply a verified source action; preserve entitlement before payable day.

    Source adapters preload verified actions/calendar outside this transaction.
    Revised economic evidence is never implicitly paid as another distribution.
    """
    timestamp = TypeAdapter(UTCTimestamp).validate_python(observed_at)
    fingerprint = action_hash(action)
    source_key = action_key(action)
    with Session(engine) as session, session.begin():
        account = _locked(session, identity)
        source = session.get(DatasetSnapshot, snapshot_id)
        if source is None or source.quality == "blocked":
            raise LedgerConflict("Usable corporate-action snapshot is required")
        if source.manifest["calendar"]["version"] != calendar_digest(calendar):
            raise LedgerConflict("Corporate-action calendar differs from snapshot")
        before = _check_projection(session, account)
        if account.status == "closed":
            raise LedgerConflict("Paper portfolio is closed")
        needs_capture = action.kind == "split" or not any(
            item.key == source_key for item in before.entitlements
        )
        already_applied = any(item.key == source_key for item in before.applied_actions)
        if (
            needs_capture
            and not already_applied
            and session.scalar(
                select(PaperFill.id)
                .join(LedgerEvent, PaperFill.event_id == LedgerEvent.id)
                .where(
                    LedgerEvent.portfolio_id == identity,
                    PaperFill.execution_session >= action.effective_session,
                )
                .limit(1)
            )
            is not None
        ):
            raise LedgerConflict("Chronological replay required before affected-session trades")
        result = apply_action(
            before,
            action,
            session=session_date,
            observed_at=timestamp,
            live=live,
            calendar=calendar,
        )
        if result.state_after == before:
            if result.status == "already_applied":
                posted = session.scalar(
                    select(LedgerEvent.id)
                    .join(ActionEvidence, LedgerEvent.action_evidence_id == ActionEvidence.id)
                    .where(
                        LedgerEvent.portfolio_id == identity,
                        ActionEvidence.source_key == source_key,
                        ActionEvidence.payload_sha256 == fingerprint,
                        LedgerEvent.kind.in_(("split", "dividend")),
                    )
                )
                return posted
            return None
        # Unadjusted pending intent needs explicit audited transformation (#46).
        # Freeze execution instead of silently resizing authorized shares.
        if (
            action.kind == "split"
            and session.scalar(
                select(PaperOrderBatch.id)
                .where(PaperOrderBatch.portfolio_id == identity, ~PaperOrderBatch.terminal)
                .limit(1)
            )
            is not None
        ):
            raise LedgerConflict("Pending order adjustment requires reevaluation")
        evidence = session.scalar(
            select(ActionEvidence).where(
                ActionEvidence.portfolio_id == identity,
                ActionEvidence.source_key == source_key,
                ActionEvidence.payload_sha256 == fingerprint,
            )
        )
        if evidence is None:
            evidence = ActionEvidence(
                id=uuid5(identity, "action:" + fingerprint + digest(source_key)),
                portfolio_id=identity,
                source_key=source_key,
                payload_sha256=fingerprint,
                payload=action.model_dump(mode="json"),
                recorded_at=timestamp,
            )
            session.add(evidence)
            session.flush()
        kind = action.kind if result.status == "applied" else "entitlement"
        command = {
            "source_key": source_key,
            "payload_sha256": fingerprint,
            "phase": kind,
            "snapshot_id": str(snapshot_id),
            "calendar_sha256": calendar_digest(calendar),
        }
        key = "action:" + digest([source_key, kind])
        existing = _existing(session, identity, key, digest(command))
        if existing is not None:
            return existing.id
        event = _append(
            session,
            account,
            key=key,
            kind=kind,
            before=before,
            after=result.state_after,
            command=command,
            recorded_at=timestamp,
            effective_at=timestamp,
            cash_entry=kind == "dividend",
            action_evidence_id=evidence.id,
            snapshot_id=snapshot_id,
            details={
                "action": result.model_dump(mode="json"),
                "recognized_cash_usd": result.cash_delta_usd,
            },
        )
        return event.id


def correct_dividend(
    engine: Engine,
    identity: UUID,
    *,
    target_event_id: UUID,
    command_id: UUID,
    revised_action: CorporateAction,
    reason: str,
    observed_at: datetime,
) -> UUID:
    """Append a supported cash-only dividend correction; never rewrite a fill.

    Revised source evidence must already be verified by the backend adapter.
    Corrections to splits/trades or unsupported/negative results need explicit
    reconciliation and cannot be represented as unexplained funding.
    """
    timestamp = TypeAdapter(UTCTimestamp).validate_python(observed_at)
    if not reason.strip() or len(reason) > 2000:
        raise ValueError("Correction requires a bounded explanatory reason")
    command = {
        "target_event_id": str(target_event_id),
        "revised_action": revised_action.model_dump(mode="json"),
        "reason": reason,
    }
    failure: str | None = None
    event_id: UUID | None = None
    with Session(engine) as session, session.begin():
        account = _locked(session, identity)
        key = "correction:" + str(command_id)
        existing = _existing(session, identity, key, digest(command))
        if existing is not None:
            return existing.id
        before = _check_projection(session, account)
        target = session.get(LedgerEvent, target_event_id)
        if target is None or target.portfolio_id != identity:
            raise LookupError("Correction target does not belong to portfolio")
        if (
            session.scalar(
                select(LedgerEvent.id)
                .where(LedgerEvent.correction_target_id == target_event_id)
                .limit(1)
            )
            is not None
        ):
            raise LedgerConflict(
                "Correction target is already superseded; reference its correction"
            )
        evidence = (
            session.get(ActionEvidence, target.action_evidence_id)
            if target.action_evidence_id
            else None
        )
        if (
            target.kind not in {"dividend", "correction"}
            or evidence is None
            or revised_action.kind != "dividend"
            or revised_action.asset_id != CorporateAction.model_validate(evidence.payload).asset_id
            or revised_action.payable_session
            != CorporateAction.model_validate(evidence.payload).payable_session
            or action_key(revised_action) != evidence.source_key
            or revised_action.effective_session
            != CorporateAction.model_validate(evidence.payload).effective_session
            or not revised_action.visible(timestamp, True)
        ):
            failure = "Unsupported correction requires explicit reconciliation"
        else:
            entitlement = next(
                (row for row in before.entitlements if row.key == evidence.source_key), None
            )
            if entitlement is None or revised_action.per_share is None:
                failure = "Correction lacks original dividend entitlement"
            else:
                with arithmetic(before.cash_usd, entitlement.quantity, revised_action.per_share):
                    corrected = money(
                        Decimal(entitlement.quantity) * Decimal(revised_action.per_share)
                    )
                    delta = Decimal(corrected) - Decimal(
                        target.payload["details"]["recognized_cash_usd"]
                    )
                    balance = Decimal(before.cash_usd) + delta
                    if balance < 0:
                        failure = "Correction would create negative cash"
                    else:
                        after = PortfolioState(
                            cash_usd=money(balance),
                            positions=before.positions,
                            applied_actions=before.applied_actions,
                            entitlements=before.entitlements,
                        )
                        event = _append(
                            session,
                            account,
                            key=key,
                            kind="correction",
                            before=before,
                            after=after,
                            command=command,
                            recorded_at=timestamp,
                            effective_at=timestamp,
                            cash_entry=True,
                            action_evidence_id=evidence.id,
                            correction_target_id=target.id,
                            snapshot_id=target.snapshot_id,
                            details={
                                "recognized_cash_usd": corrected,
                                "revised_payload_sha256": action_hash(revised_action),
                            },
                        )
                        event_id = event.id
        if failure:
            account.reconciliation_failed = True
    if failure:
        raise ReconciliationFailure(failure)
    assert event_id is not None
    return event_id
