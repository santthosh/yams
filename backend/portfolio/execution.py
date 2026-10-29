"""Shared synthetic raw-open execution; returns proposed effects, never posts them."""

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, Decimal, localcontext
from fractions import Fraction
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, StrictBool, TypeAdapter, model_validator

from backend.domain.market import MarketBarV1
from backend.domain.types import (
    AssetId,
    Contract,
    DecimalString,
    FractionString,
    Hash256,
    Money,
    Price,
    Quantity,
    Reason,
    SessionDate,
    SignedMoney,
    SourceMode,
    UTCTimestamp,
    canonical_json,
    decimal_text,
)
from backend.market_data.models import Calendar, Session

CENT = Decimal("0.01")
SHARE = Decimal("0.000001")


@contextmanager
def arithmetic(*values: str) -> Iterator[None]:
    """Enough precision for finite products; divisions conservatively round down."""
    with localcontext() as context:
        context.prec = max(80, sum(len(value) for value in values) + 64)
        context.rounding = ROUND_DOWN
        yield


def money(value: Decimal) -> str:
    return format(value.quantize(CENT, rounding=ROUND_HALF_EVEN), ".2f")


def quantity(value: Decimal) -> str:
    return format(value.quantize(SHARE, rounding=ROUND_DOWN), ".6f")


class Position(Contract):
    asset_id: AssetId
    sector: Annotated[str, Field(strict=True, min_length=1)]
    quantity: Quantity
    total_basis_usd: Money

    @model_validator(mode="after")
    def zero_basis(self) -> Self:
        if Decimal(self.quantity) == 0 and Decimal(self.total_basis_usd) != 0:
            raise ValueError("Zero shares require zero total basis")
        return self


class AppliedAction(Contract):
    key: str
    payload_sha256: Hash256


class DividendEntitlement(Contract):
    key: str
    asset_id: AssetId
    ex_session: SessionDate
    quantity: Quantity
    per_share: DecimalString
    evidence_sha256: Hash256


class PortfolioState(Contract):
    cash_usd: Money
    positions: tuple[Position, ...]
    applied_actions: tuple[AppliedAction, ...] = ()
    entitlements: tuple[DividendEntitlement, ...] = ()

    @model_validator(mode="after")
    def unique(self) -> Self:
        for ids in (
            [row.asset_id for row in self.positions],
            [row.key for row in self.applied_actions],
            [row.key for row in self.entitlements],
        ):
            if len(ids) != len(set(ids)):
                raise ValueError("Duplicate state identity")
        return self


class ExecutionPolicy(Contract):
    id: Literal["us_eod_next_open_v1"] = "us_eod_next_open_v1"
    slippage_fraction: FractionString = "0.001"
    commission_usd: Money = "0.00"

    @model_validator(mode="after")
    def positive_sell_price(self) -> Self:
        if Decimal(self.slippage_fraction) >= 1:
            raise ValueError("Slippage must be below one")
        return self


DEFAULT_EXECUTION_POLICY = ExecutionPolicy()


class ExecutionContext(Contract):
    snapshot_id: UUID
    snapshot_sha256: Hash256
    calendar_sha256: Hash256
    mode: SourceMode
    engine_version: Annotated[str, Field(strict=True, min_length=1)]
    execution_mode: Literal["current_paper", "historical_replay"]
    decision_session: SessionDate
    decision_cutoff: UTCTimestamp
    approved_at: UTCTimestamp


class MarketEvidence(Contract):
    snapshot_id: UUID
    snapshot_sha256: Hash256
    mode: SourceMode
    freshness: Literal["fresh", "fixture", "stale", "blocked"]
    bars: tuple[MarketBarV1, ...]

    @model_validator(mode="after")
    def unique(self) -> Self:
        ids = [(bar.asset_id, bar.session_date) for bar in self.bars]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate market evidence")
        if self.freshness == "fixture" and self.mode != "synthetic_fixture":
            raise ValueError("Fixture freshness requires synthetic source mode")
        return self


class OrderIntent(Contract):
    key: Annotated[str, Field(strict=True, min_length=1)]
    asset_id: AssetId
    sector: Annotated[str, Field(strict=True, min_length=1)]
    side: Literal["BUY", "SELL"]
    requested_quantity: Quantity

    @model_validator(mode="after")
    def positive(self) -> Self:
        if Decimal(self.requested_quantity) <= 0:
            raise ValueError("Order quantity must be positive")
        return self


class PricedEffect(Contract):
    raw_price: Price
    executed_price: Price
    quantity: Quantity
    gross_usd: Money
    commission_usd: Money
    slippage_usd: Money
    cash_delta_usd: SignedMoney
    removed_basis_usd: Money
    realized_pnl_usd: SignedMoney


class FillEffect(PricedEffect):
    execution_session: SessionDate
    execution_at: UTCTimestamp
    evidence_available_at: UTCTimestamp
    proposed_at: UTCTimestamp


class QuoteTransition(Contract):
    order: OrderIntent
    status: Literal["skipped", "feasible", "partially_feasible"]
    executable_quantity: Quantity
    shortfall_quantity: Quantity
    reason: Reason | None
    effect: PricedEffect | None
    state_after: PortfolioState


class ExecutionResult(Contract):
    order: OrderIntent
    context: ExecutionContext
    policy: ExecutionPolicy
    eligible_session: Session
    status: Literal["pending", "skipped", "filled", "partially_filled"]
    terminal: StrictBool
    filled_quantity: Quantity
    pending_quantity: Quantity
    skipped_quantity: Quantity
    reason: Reason | None
    fill: FillEffect | None
    state_after: PortfolioState

    @model_validator(mode="after")
    def consistent_transition(self) -> Self:
        filled, pending, skipped = map(
            Fraction, (self.filled_quantity, self.pending_quantity, self.skipped_quantity)
        )
        if filled + pending + skipped != Fraction(self.order.requested_quantity):
            raise ValueError("Execution quantities do not conserve requested intent")
        if self.terminal != (pending == 0) or (self.fill is not None) != (filled > 0):
            raise ValueError("Execution lifecycle disagrees with effects")
        if self.status == "pending" and (filled or self.terminal):
            raise ValueError("Pending execution cannot contain a fill")
        if self.status == "skipped" and (filled or not self.terminal):
            raise ValueError("Skipped execution must be unfilled and terminal")
        if self.status == "filled" and (skipped or pending):
            raise ValueError("Filled execution must complete all requested shares")
        if self.status == "partially_filled" and not (filled > 0 and skipped > 0 and self.terminal):
            raise ValueError("Affordability partial fill requires a terminal skipped remainder")
        if self.fill is not None and (
            Fraction(self.fill.quantity) != filled
            or self.fill.execution_session != self.eligible_session.session_date
            or self.fill.execution_at != self.eligible_session.open_at
            or self.fill.proposed_at < self.fill.evidence_available_at
        ):
            raise ValueError("Fill evidence disagrees with the eligible execution")
        return self


def calendar_digest(calendar: Calendar) -> str:
    return hashlib.sha256(canonical_json(calendar.model_dump(mode="json"))).hexdigest()


def next_eligible_session(
    calendar: Calendar, decision_cutoff: datetime, approved_at: datetime
) -> Session:
    cutoff = TypeAdapter(UTCTimestamp).validate_python(decision_cutoff)
    approval = TypeAdapter(UTCTimestamp).validate_python(approved_at)
    if not calendar.sessions or any(
        left.close_at >= right.open_at
        for left, right in zip(calendar.sessions, calendar.sessions[1:], strict=False)
    ):
        raise ValueError("A nonempty validated chronological calendar is required")
    for row in calendar.sessions:
        if row.open_at > max(cutoff, approval):
            return row
    raise ValueError("No eligible future open in pinned calendar")


def verify_context(
    context: ExecutionContext, calendar: Calendar, market: MarketEvidence
) -> Session:
    if calendar_digest(calendar) != context.calendar_sha256:
        raise ValueError("Calendar digest mismatch")
    if (market.snapshot_id, market.snapshot_sha256, market.mode) != (
        context.snapshot_id,
        context.snapshot_sha256,
        context.mode,
    ):
        raise ValueError("Execution market lineage mismatch")
    decision = next(
        (s for s in calendar.sessions if s.session_date == context.decision_session), None
    )
    if decision is None or context.decision_cutoff < decision.close_at:
        raise ValueError("Decision must follow a pinned completed session")
    return next_eligible_session(calendar, context.decision_cutoff, context.approved_at)


def replace_position(state: PortfolioState, position: Position, cash: str) -> PortfolioState:
    positions = {row.asset_id: row for row in state.positions}
    if Decimal(position.quantity) > 0:
        positions[position.asset_id] = position
    else:
        positions.pop(position.asset_id, None)
    return PortfolioState(
        cash_usd=cash,
        positions=tuple(positions[key] for key in sorted(positions)),
        applied_actions=state.applied_actions,
        entitlements=state.entitlements,
    )


def usable_evidence_bar(bar: MarketBarV1, observed_at: datetime, *, live: bool) -> bool:
    """One raw-price/availability guard for execution and read-only valuation."""
    return (
        bar.price_basis == "raw_as_traded"
        and not set(bar.quality_flags) - {"SYNTHETIC_DATA_ONLY"}
        and bar.available_at <= observed_at
        and (not live or bar.ingested_at <= observed_at)
    )


def usable_bar(bar: MarketBarV1, observed_at: datetime, context: ExecutionContext) -> bool:
    return usable_evidence_bar(bar, observed_at, live=context.execution_mode == "current_paper")


def execute_order(
    state: PortfolioState,
    order: OrderIntent,
    context: ExecutionContext,
    calendar: Calendar,
    market: MarketEvidence,
    *,
    observed_at: datetime,
    min_trade_usd: Money,
    policy: ExecutionPolicy = DEFAULT_EXECUTION_POLICY,
) -> ExecutionResult:
    """One proposed transition from POSTED state; caller must durably post before reuse."""
    observed_at = TypeAdapter(UTCTimestamp).validate_python(observed_at)
    min_trade_usd = TypeAdapter(Money).validate_python(min_trade_usd)
    eligible = verify_context(context, calendar, market)

    def unfilled(status: Literal["pending", "skipped"], reason: str) -> ExecutionResult:
        return ExecutionResult(
            order=order,
            context=context,
            policy=policy,
            eligible_session=eligible,
            status=status,
            terminal=status != "pending",
            filled_quantity="0.000000",
            pending_quantity=order.requested_quantity if status == "pending" else "0.000000",
            skipped_quantity=order.requested_quantity if status == "skipped" else "0.000000",
            reason=reason,
            fill=None,
            state_after=state,
        )

    if observed_at < eligible.open_at:
        return unfilled("pending", "WAITING_FOR_ELIGIBLE_OPEN")
    if market.freshness == "blocked" or (
        context.execution_mode == "current_paper" and market.freshness == "stale"
    ):
        return unfilled("pending", "STALE_DATA")
    bar = next(
        (
            b
            for b in market.bars
            if b.asset_id == order.asset_id and b.session_date == eligible.session_date
        ),
        None,
    )
    if (
        bar is None
        or not usable_bar(bar, observed_at, context)
        or bar.available_at < eligible.open_at
    ):
        return unfilled("pending", "PENDING_DATA")
    quoted = quote_order(state, order, bar.open, min_trade_usd=min_trade_usd, policy=policy)
    if quoted.effect is None:
        assert quoted.reason is not None
        return unfilled("skipped", quoted.reason)
    return ExecutionResult(
        order=order,
        context=context,
        policy=policy,
        eligible_session=eligible,
        status="partially_filled" if quoted.status == "partially_feasible" else "filled",
        terminal=True,
        filled_quantity=quoted.executable_quantity,
        pending_quantity="0.000000",
        skipped_quantity=quoted.shortfall_quantity,
        reason=quoted.reason,
        fill=FillEffect(
            **quoted.effect.model_dump(),
            execution_session=eligible.session_date,
            execution_at=eligible.open_at,
            evidence_available_at=bar.available_at,
            proposed_at=observed_at,
        ),
        state_after=quoted.state_after,
    )


def quote_order(
    state: PortfolioState,
    order: OrderIntent,
    raw_price: Price,
    *,
    min_trade_usd: Money,
    policy: ExecutionPolicy = DEFAULT_EXECUTION_POLICY,
) -> QuoteTransition:
    """Hypothetical price/affordability only: this result is never a posted fill."""
    raw_price = TypeAdapter(Price).validate_python(raw_price)
    min_trade_usd = TypeAdapter(Money).validate_python(min_trade_usd)

    def unfilled(reason: str) -> QuoteTransition:
        return QuoteTransition(
            order=order,
            status="skipped",
            executable_quantity="0.000000",
            shortfall_quantity=order.requested_quantity,
            reason=reason,
            effect=None,
            state_after=state,
        )

    held = next((row for row in state.positions if row.asset_id == order.asset_id), None)
    if held is not None and held.sector != order.sector:
        raise ValueError("Order and position sector evidence disagree")
    position = held or Position(
        asset_id=order.asset_id, sector=order.sector, quantity="0.000000", total_basis_usd="0.00"
    )
    values = [
        state.cash_usd,
        position.quantity,
        position.total_basis_usd,
        order.requested_quantity,
        raw_price,
        policy.slippage_fraction,
        policy.commission_usd,
        min_trade_usd,
    ]
    with arithmetic(*values):
        cash, shares, basis = map(
            Decimal, (state.cash_usd, position.quantity, position.total_basis_usd)
        )
        requested = Decimal(order.requested_quantity)
        raw, slip, fee = map(Decimal, (raw_price, policy.slippage_fraction, policy.commission_usd))
        price = raw * (1 + slip if order.side == "BUY" else 1 - slip)
        if order.side == "BUY":
            affordable = max(Decimal(0), cash - fee) / price
            filled = min(requested, Decimal(quantity(affordable)))
        else:
            filled = min(requested, shares)
        if filled == 0:
            return unfilled("INSUFFICIENT_CASH" if order.side == "BUY" else "NO_POSITION")
        notional = filled * price
        if notional < Decimal(min_trade_usd):
            return unfilled("BELOW_MIN_TRADE")
        gross = Decimal(money(notional))
        delta = -(gross + fee) if order.side == "BUY" else gross - fee
        if cash + delta < 0:
            return unfilled("INSUFFICIENT_CASH")
        removed = Decimal(0)
        realized = Decimal(0)
        if order.side == "BUY":
            after_shares, after_basis = shares + filled, basis - delta
        else:
            removed = basis if filled == shares else Decimal(money(basis * filled / shares))
            realized = delta - removed
            after_shares, after_basis = shares - filled, basis - removed
        updated = replace_position(
            state,
            Position(
                asset_id=position.asset_id,
                sector=position.sector,
                quantity=quantity(after_shares),
                total_basis_usd=money(after_basis),
            ),
            money(cash + delta),
        )
        shortfall = requested - filled
        return QuoteTransition(
            order=order,
            status="partially_feasible" if shortfall else "feasible",
            executable_quantity=quantity(filled),
            shortfall_quantity=quantity(shortfall),
            reason=("INSUFFICIENT_CASH" if order.side == "BUY" else "INSUFFICIENT_HOLDINGS")
            if shortfall
            else None,
            effect=PricedEffect(
                raw_price=raw_price,
                executed_price=decimal_text(price),
                quantity=quantity(filled),
                gross_usd=money(gross),
                commission_usd=money(fee),
                slippage_usd=money(abs(price - raw) * filled),
                cash_delta_usd=money(delta),
                removed_basis_usd=money(removed),
                realized_pnl_usd=money(realized),
            ),
            state_after=updated,
        )


def simulate_batch(
    state: PortfolioState,
    orders: tuple[OrderIntent, ...],
    context: ExecutionContext,
    calendar: Calendar,
    market: MarketEvidence,
    *,
    observed_at: datetime,
    min_trade_usd: Money,
    policy: ExecutionPolicy = DEFAULT_EXECUTION_POLICY,
) -> tuple[ExecutionResult, ...]:
    """Conditional replay trace, NOT spendable preview cash or durable authorization."""
    if len({o.key for o in orders}) != len(orders) or len({o.asset_id for o in orders}) != len(
        orders
    ):
        raise ValueError("Duplicate batch order identity/asset")
    results = []
    for order in sorted(orders, key=lambda row: (row.side != "SELL", row.asset_id, row.key)):
        result = execute_order(
            state,
            order,
            context,
            calendar,
            market,
            observed_at=observed_at,
            min_trade_usd=min_trade_usd,
            policy=policy,
        )
        results.append(result)
        state = result.state_after
    return tuple(results)
