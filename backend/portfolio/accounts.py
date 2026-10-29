"""Paper account transport composition over the shared immutable ledger/market store."""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_EVEN, Decimal
from fractions import Fraction
from pathlib import Path
from uuid import UUID, uuid5

from pydantic import TypeAdapter
from sqlalchemy import Engine, or_, select
from sqlalchemy.orm import Session

from backend.domain.common import ErrorCode
from backend.domain.portfolio import (
    PaperPortfolioV1,
    PortfolioCreateRequest,
    PortfolioFillV1,
    PortfolioHoldingV1,
    PortfolioPositionChangeV1,
    PortfolioTransactionPageV1,
    PortfolioTransactionV1,
    PortfolioValuationV1,
)
from backend.domain.strategy import StrategyConfigV1
from backend.domain.types import SourceMode, decimal_text, load_json
from backend.market_data.catalog import verified_snapshot
from backend.market_data.models import Calendar
from backend.market_data.repository import MarketRepository
from backend.persistence.models.ledger import CashEntry, LedgerEvent, PaperFill, PositionEvent
from backend.persistence.models.portfolio import PaperPortfolio
from backend.persistence.models.snapshot import CurrentSnapshot, DatasetSnapshot
from backend.persistence.models.strategy import StrategyVersion
from backend.persistence.models.workspace import LocalWorkspace
from backend.portfolio.execution import MarketEvidence, PortfolioState, arithmetic, money
from backend.portfolio.ledger import (
    LedgerConflict,
    ReconciliationFailure,
    _check_projection,
    _locked,
    create_portfolio,
)
from backend.portfolio.valuation import value_close_at


class AccountError(ValueError):
    def __init__(self, code: ErrorCode, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class AccountRecord:
    id: UUID
    name: str
    mode: SourceMode
    strategy_version_id: UUID
    opening_cash_usd: str
    opening_snapshot_id: UUID | None
    revision: int
    last_sequence: int
    status: str
    created_at: datetime
    state: PortfolioState
    config: StrategyConfigV1
    valuation_snapshot_id: UUID | None


def _record(session: Session, identity: UUID) -> AccountRecord:
    account = _locked(session, identity)
    state = _check_projection(session, account)
    version = session.get(StrategyVersion, account.strategy_version_id)
    opening = session.get(LedgerEvent, account.opening_event_id)
    if version is None or opening is None:
        raise ReconciliationFailure("Account immutable references are unavailable")
    config = StrategyConfigV1.model_validate(version.config)
    if config.config_hash() != version.config_sha256:
        raise ReconciliationFailure("Account strategy content differs from its identity")
    pointer = session.get(CurrentSnapshot, account.source_mode)
    # The immutable creation source remains usable before another same-mode
    # publication; a different source mode can never be selected implicitly.
    snapshot_id = pointer.snapshot_id if pointer is not None else opening.snapshot_id
    return AccountRecord(
        id=account.id,
        name=account.name,
        mode=TypeAdapter(SourceMode).validate_python(account.source_mode),
        strategy_version_id=account.strategy_version_id,
        opening_cash_usd=format(account.opening_cash_usd, ".2f"),
        opening_snapshot_id=opening.snapshot_id,
        revision=account.revision,
        last_sequence=account.last_sequence,
        status=account.status,
        created_at=account.created_at,
        state=state,
        config=config,
        valuation_snapshot_id=snapshot_id,
    )


def account_record(engine: Engine, identity: UUID) -> AccountRecord:
    # Copy one coherent posted state while its writer is excluded, then release
    # the lock before reading any artifact or invoking DuckDB.
    with Session(engine) as session, session.begin():
        return _record(session, identity)


def create_account(
    engine: Engine,
    root: Path,
    request: PortfolioCreateRequest,
    key: UUID,
) -> AccountRecord:
    with Session(engine) as session:
        workspace = session.scalar(select(LocalWorkspace).where(LocalWorkspace.singleton == 1))
        if workspace is None:
            raise AccountError("NOT_READY", "Local workspace is unavailable.")
        workspace_id = workspace.id
        identity = uuid5(workspace_id, "portfolio-create:" + str(key))
        existing = session.get(PaperPortfolio, identity)
        if existing is not None:
            opening = session.get(LedgerEvent, existing.opening_event_id)
            if opening is None:
                raise ReconciliationFailure("Opening account evidence is unavailable")
            command = opening.payload["command"]
            original = PortfolioCreateRequest(
                name=command["name"],
                strategy_version_id=UUID(command["strategy_version_id"]),
                opening_cash_usd=command["opening_cash_usd"],
                mode=command["source_mode"],
                snapshot_id=UUID(command["snapshot_id"]) if command.get("snapshot_id") else None,
            )
            if original.model_dump(exclude={"opening_cash_usd"}) != request.model_dump(
                exclude={"opening_cash_usd"}
            ) or Decimal(original.opening_cash_usd) != Decimal(request.opening_cash_usd):
                raise AccountError("IDEMPOTENCY_CONFLICT", "Creation key has different inputs.")
            # Resolve retry before checking today's data/version availability.
            # Release this read connection before taking the account lock; two
            # concurrent retries must not exhaust the bounded two-slot pool.
            session.close()
            return account_record(engine, identity)
        version = session.get(StrategyVersion, request.strategy_version_id)
        if version is None or version.status != "published":
            raise AccountError("NOT_FOUND", "Published strategy version was not found.")
        if request.snapshot_id is not None:
            row = session.get(DatasetSnapshot, request.snapshot_id)
            if row is None:
                raise AccountError("NOT_FOUND", "Starting snapshot was not found.")
            if row.source_mode != request.mode:
                raise AccountError(
                    "STATE_CONFLICT", "Starting snapshot has a different source mode."
                )
            if row.quality == "blocked":
                raise AccountError("STALE_DATA", "Starting snapshot is blocked.")
            verified_snapshot(row, root)  # No financial row lock held here.
    try:
        create_portfolio(
            engine,
            portfolio_id=identity,
            workspace_id=workspace_id,
            strategy_version_id=request.strategy_version_id,
            name=request.name,
            opening_cash_usd=request.opening_cash_usd,
            source_mode=request.mode,
            snapshot_id=request.snapshot_id,
            created_at=datetime.now(UTC),
        )
    except LedgerConflict:
        raise AccountError("IDEMPOTENCY_CONFLICT", "Creation key has different inputs.") from None
    return account_record(engine, identity)


def list_accounts(
    engine: Engine,
    *,
    limit: int = 25,
    cursor: UUID | None = None,
    mode: SourceMode | None = None,
) -> tuple[tuple[AccountRecord, ...], str | None]:
    if type(limit) is not int or not 1 <= limit <= 100:
        raise AccountError("VALIDATION_ERROR", "Account page size is invalid.")
    with Session(engine) as session, session.begin():
        statement = select(PaperPortfolio.id)
        if mode is not None:
            statement = statement.where(PaperPortfolio.source_mode == mode)
        if cursor is not None:
            previous = session.get(PaperPortfolio, cursor)
            if previous is None or (mode is not None and previous.source_mode != mode):
                raise AccountError("VALIDATION_ERROR", "Portfolio cursor is invalid for this list.")
            statement = statement.where(
                or_(
                    PaperPortfolio.created_at < previous.created_at,
                    (PaperPortfolio.created_at == previous.created_at)
                    & (PaperPortfolio.id < previous.id),
                )
            )
        rows = list(
            session.scalars(
                statement.order_by(
                    PaperPortfolio.created_at.desc(), PaperPortfolio.id.desc()
                ).limit(limit + 1)
            )
        )
        records = tuple(_record(session, identity) for identity in rows[:limit])
        return records, str(rows[limit - 1]) if len(rows) > limit else None


def _weight(value: Fraction, nav: Fraction) -> str:
    with arithmetic(str(value), str(nav)):
        result = (Decimal(value.numerator) / Decimal(value.denominator)) / (
            Decimal(nav.numerator) / Decimal(nav.denominator)
        )
        return decimal_text(
            result.quantize(Decimal("0.000000000000000001"), rounding=ROUND_HALF_EVEN)
        )


def _unavailable(
    record: AccountRecord,
    now: datetime,
    reason: str,
    *,
    snapshot: DatasetSnapshot | None = None,
    stale: bool = False,
) -> tuple[tuple[PortfolioHoldingV1, ...], PortfolioValuationV1]:
    return tuple(
        PortfolioHoldingV1(
            asset_id=p.asset_id,
            sector=p.sector,
            quantity=p.quantity,
            total_basis_usd=p.total_basis_usd,
            mark_price_usd=None,
            price_as_of_session=None,
            market_value_usd=None,
            weight=None,
            reason=reason,
        )
        for p in record.state.positions
    ), PortfolioValuationV1(
        status="stale" if stale else "unavailable",
        total_value_usd=None,
        cash_weight=None,
        snapshot_id=snapshot.id if snapshot else None,
        snapshot_sha256=snapshot.manifest_hash if snapshot else None,
        as_of_session=None,
        checked_at=now,
        reason=reason,
        missing_assets=tuple(p.asset_id for p in record.state.positions),
        warnings=("SYNTHETIC_DATA_ONLY",) if record.mode == "synthetic_fixture" else (),
    )


@dataclass(frozen=True)
class ValuationInputs:
    snapshot: DatasetSnapshot
    calendar: Calendar
    marks: MarketEvidence
    session: date
    cutoff: datetime
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class UnavailableInputs:
    reason: str
    snapshot: DatasetSnapshot | None = None
    stale: bool = False


PriceCache = dict[UUID, ValuationInputs | UnavailableInputs]


def _prices(
    engine: Engine,
    root: Path,
    identity: UUID,
    mode: SourceMode,
    now: datetime,
) -> ValuationInputs | UnavailableInputs:
    with Session(engine) as session:
        snapshot = session.get(DatasetSnapshot, identity)
    if snapshot is None or snapshot.source_mode != mode:
        return UnavailableInputs("SNAPSHOT_UNAVAILABLE")
    if snapshot.quality == "blocked":
        return UnavailableInputs("SNAPSHOT_BLOCKED", snapshot)
    try:
        pinned = verified_snapshot(snapshot, root)
        manifest = pinned.manifest
        supported = manifest.price_basis.ohlc == "raw_as_traded"
        if mode == "research_market_data":
            provenance = next(
                (
                    a
                    for a in manifest.artifacts
                    if a.role == "provenance" and a.sha256 == manifest.source.capabilities_sha256
                ),
                None,
            )
            capabilities = load_json(pinned.artifacts[provenance.path]) if provenance else None
            supported = supported and (
                manifest.source.rights_status == "verified_local_use"
                and bool(manifest.source.rights_reference)
                and isinstance(capabilities, dict)
                and capabilities.get("raw_execution_prices") is True
                and capabilities.get("complete_action_accounting") is True
            )
        if not supported:
            return UnavailableInputs("UNSUPPORTED_ACCOUNTING_SOURCE", snapshot)
        latest = manifest.coverage.latest_completed_session
        if latest is None:
            return UnavailableInputs("PRICE_UNAVAILABLE", snapshot)
        with MarketRepository(pinned) as repository:
            scheduled = next(
                (item for item in repository.calendar.sessions if item.session_date == latest), None
            )
            if scheduled is None:
                return UnavailableInputs("CALENDAR_UNAVAILABLE", snapshot)
            if mode == "research_market_data" and scheduled.close_at > now:
                return UnavailableInputs("SESSION_NOT_COMPLETE", snapshot)
            cutoff = (
                repository.fixture_observation_at(latest) if mode == "synthetic_fixture" else now
            )
            view = repository.accounting_as_of(cutoff, latest)
            completed = [
                item.session_date for item in repository.calendar.sessions if item.close_at <= now
            ]
            fresh = mode == "synthetic_fixture" or (
                bool(completed)
                and max(completed) == latest
                and any(item.open_at > now for item in repository.calendar.sessions)
            )
            marks = MarketEvidence(
                snapshot_id=snapshot.id,
                snapshot_sha256=snapshot.manifest_hash,
                mode=mode,
                freshness="fixture"
                if mode == "synthetic_fixture"
                else "fresh"
                if fresh
                else "stale",
                bars=view.bars,
            )
            return ValuationInputs(
                snapshot, repository.calendar, marks, latest, cutoff, manifest.warnings
            )
    except (ValueError, OSError):
        return UnavailableInputs("SNAPSHOT_UNAVAILABLE", snapshot)


def render_account(
    engine: Engine,
    root: Path,
    record: AccountRecord,
    *,
    price_cache: PriceCache | None = None,
) -> PaperPortfolioV1:
    now = datetime.now(UTC)
    if not record.state.positions:
        holdings: tuple[PortfolioHoldingV1, ...] = ()
        valuation = PortfolioValuationV1(
            status="available",
            total_value_usd=record.state.cash_usd,
            cash_weight="1" if Decimal(record.state.cash_usd) > 0 else None,
            snapshot_id=None,
            snapshot_sha256=None,
            as_of_session=None,
            checked_at=now,
            reason="CASH_ONLY" if Decimal(record.state.cash_usd) > 0 else "ZERO_PORTFOLIO_VALUE",
            missing_assets=(),
            warnings=("SYNTHETIC_DATA_ONLY",) if record.mode == "synthetic_fixture" else (),
        )
    elif record.valuation_snapshot_id is None:
        holdings, valuation = _unavailable(record, now, "SNAPSHOT_UNAVAILABLE")
    else:
        cache = price_cache if price_cache is not None else {}
        identity = record.valuation_snapshot_id
        if identity not in cache:
            # Immutable source inputs are shared within this response only. A
            # 100-account page must not open DuckDB 100 times for the same source.
            cache[identity] = _prices(engine, root, identity, record.mode, now)
        inputs = cache[identity]
        if isinstance(inputs, UnavailableInputs):
            holdings, valuation = _unavailable(
                record, now, inputs.reason, snapshot=inputs.snapshot, stale=inputs.stale
            )
        else:
            if inputs.snapshot.source_mode != record.mode:
                raise ReconciliationFailure("Portfolio source mode differs from cached evidence")
            valued = value_close_at(
                record.state,
                inputs.calendar,
                inputs.marks,
                session_date=inputs.session,
                cutoff=inputs.cutoff,
                live=record.mode != "synthetic_fixture",
            )
            if valued.nav is None:
                stale = inputs.marks.freshness == "stale"
                holdings, valuation = _unavailable(
                    record,
                    now,
                    "STALE_DATA" if stale else "PRICE_UNAVAILABLE",
                    snapshot=inputs.snapshot,
                    stale=stale,
                )
                valuation = valuation.model_copy(
                    update={
                        "as_of_session": inputs.session,
                        "missing_assets": valued.missing_assets,
                    }
                )
            else:
                lines = []
                for position in record.state.positions:
                    raw_value = valued.values[position.asset_id]
                    with arithmetic(str(raw_value)):
                        value = money(Decimal(raw_value.numerator) / Decimal(raw_value.denominator))
                    lines.append(
                        PortfolioHoldingV1(
                            asset_id=position.asset_id,
                            sector=position.sector,
                            quantity=position.quantity,
                            total_basis_usd=position.total_basis_usd,
                            mark_price_usd=valued.marks[position.asset_id].close,
                            price_as_of_session=inputs.session,
                            market_value_usd=value,
                            weight=_weight(raw_value, valued.nav) if valued.nav else None,
                            reason=None if valued.nav else "ZERO_PORTFOLIO_VALUE",
                        )
                    )
                holdings = tuple(lines)
                valuation = PortfolioValuationV1(
                    status="available",
                    total_value_usd=valued.money_value(),
                    cash_weight=_weight(Fraction(record.state.cash_usd), valued.nav)
                    if valued.nav
                    else None,
                    snapshot_id=inputs.snapshot.id,
                    snapshot_sha256=inputs.snapshot.manifest_hash,
                    as_of_session=inputs.session,
                    checked_at=now,
                    reason=None if valued.nav else "ZERO_PORTFOLIO_VALUE",
                    missing_assets=(),
                    warnings=inputs.warnings,
                )
    return PaperPortfolioV1.model_validate(
        dict(
            id=record.id,
            name=record.name,
            valuation_mode=record.mode,
            total_value_usd=valuation.total_value_usd,
            valuation_as_of_session=valuation.as_of_session,
            strategy_version_id=record.strategy_version_id,
            opening_cash_usd=record.opening_cash_usd,
            opening_snapshot_id=record.opening_snapshot_id,
            cash_usd=record.state.cash_usd,
            revision=record.revision,
            last_sequence=record.last_sequence,
            state=record.status,
            reconciliation_failed=False,
            risk_policy=record.config.portfolio,
            created_at=record.created_at,
            holdings=holdings,
            valuation=valuation,
        )
    )


def account_transactions(
    engine: Engine,
    identity: UUID,
    *,
    limit: int = 25,
    cursor: UUID | None = None,
) -> PortfolioTransactionPageV1:
    """Immutable event pages: neither projections nor jobs can change on read."""
    if type(limit) is not int or not 1 <= limit <= 100:
        raise AccountError("VALIDATION_ERROR", "Transaction page size is invalid.")
    with Session(engine) as session:
        account = session.get(PaperPortfolio, identity)
        if account is None:
            raise LookupError("Paper account does not exist")
        statement = select(LedgerEvent).where(LedgerEvent.portfolio_id == identity)
        if cursor is not None:
            previous = session.get(LedgerEvent, cursor)
            if previous is None or previous.portfolio_id != identity:
                raise AccountError(
                    "VALIDATION_ERROR", "Transaction cursor belongs to another page."
                )
            statement = statement.where(LedgerEvent.sequence < previous.sequence)
        events = list(
            session.scalars(statement.order_by(LedgerEvent.sequence.desc()).limit(limit + 1))
        )
        items = []
        for event in events[:limit]:
            cash_entries = list(
                session.scalars(select(CashEntry).where(CashEntry.event_id == event.id))
            )
            with arithmetic(*(str(entry.delta_usd) for entry in cash_entries)):
                cash_delta = money(sum((entry.delta_usd for entry in cash_entries), Decimal(0)))
            changes = tuple(
                PortfolioPositionChangeV1(
                    asset_id=entry.asset_id,
                    quantity_delta=format(entry.quantity_delta, ".6f"),
                    total_basis_delta_usd=format(entry.basis_delta_usd, ".2f"),
                )
                for entry in session.scalars(
                    select(PositionEvent)
                    .where(PositionEvent.event_id == event.id)
                    .order_by(PositionEvent.asset_id)
                )
            )
            fill = session.scalar(select(PaperFill).where(PaperFill.event_id == event.id))
            posted_fill = (
                PortfolioFillV1(
                    id=fill.id,
                    order_id=fill.order_id,
                    execution_session=fill.execution_session,
                    raw_price_usd=decimal_text(fill.raw_price),
                    executed_price_usd=decimal_text(fill.executed_price),
                    quantity=format(fill.quantity, ".6f"),
                    gross_usd=format(fill.gross_usd, ".2f"),
                    commission_usd=format(fill.fee_usd, ".2f"),
                    slippage_usd=format(fill.slippage_usd, ".2f"),
                    removed_basis_usd=format(fill.removed_basis_usd, ".2f"),
                    realized_pnl_usd=format(fill.realized_pnl_usd, ".2f"),
                )
                if fill is not None
                else None
            )
            items.append(
                PortfolioTransactionV1.model_validate(
                    dict(
                        id=event.id,
                        sequence=event.sequence,
                        portfolio_revision=event.portfolio_revision,
                        kind=event.kind,
                        event_key=event.event_key,
                        recorded_at=event.recorded_at,
                        effective_at=event.effective_at,
                        strategy_version_id=event.strategy_version_id,
                        snapshot_id=event.snapshot_id,
                        cash_delta_usd=cash_delta,
                        position_changes=changes,
                        correction_target_id=event.correction_target_id,
                        fill=posted_fill,
                    )
                )
            )
        return PortfolioTransactionPageV1(
            portfolio_id=identity,
            mode=TypeAdapter(SourceMode).validate_python(account.source_mode),
            warnings=("SYNTHETIC_DATA_ONLY",) if account.source_mode == "synthetic_fixture" else (),
            items=tuple(items),
            next_cursor=str(events[limit - 1].id) if len(events) > limit else None,
        )
