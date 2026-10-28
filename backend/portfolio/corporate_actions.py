"""Chronological, repeat-safe proposed split/dividend effects on posted state."""

import hashlib
from datetime import date, datetime
from decimal import Decimal
from fractions import Fraction
from typing import Literal

from pydantic import TypeAdapter

from backend.domain.types import (
    Contract,
    Hash256,
    Money,
    Reason,
    SessionDate,
    UTCTimestamp,
    canonical_json,
    decimal_text,
)
from backend.market_data.models import Calendar, CorporateAction
from backend.portfolio.execution import (
    AppliedAction,
    DividendEntitlement,
    PortfolioState,
    Position,
    arithmetic,
    calendar_digest,
    money,
    quantity,
    replace_position,
)


class ActionResult(Contract):
    action: CorporateAction
    calendar_sha256: Hash256
    session: SessionDate
    observed_at: UTCTimestamp
    status: Literal["applied", "already_applied", "pending"]
    reason: Reason | None
    cash_delta_usd: Money
    state_after: PortfolioState


def action_key(action: CorporateAction) -> str:
    # Canonical tuple avoids ambiguous concatenations of provider-controlled IDs.
    return canonical_json([action.provider, action.event_id]).decode()


def action_hash(action: CorporateAction) -> str:
    payload = action.model_dump(mode="json")
    # Observation refreshes are not new distributions. Substantive revisions
    # conflict; a correction requires the durable ledger's explicit policy.
    payload.pop("available_at")
    payload.pop("ingested_at")
    for field in ("per_share", "ratio_numerator", "ratio_denominator"):
        if payload[field] is not None:
            payload[field] = decimal_text(Decimal(payload[field]))
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def apply_action(
    state: PortfolioState,
    action: CorporateAction,
    *,
    session: date,
    observed_at: datetime,
    live: bool,
    calendar: Calendar,
) -> ActionResult:
    observed_at = TypeAdapter(UTCTimestamp).validate_python(observed_at)
    session = TypeAdapter(SessionDate).validate_python(session)
    key, digest = action_key(action), action_hash(action)

    def result(
        status: Literal["applied", "already_applied", "pending"],
        reason: str | None,
        after: PortfolioState = state,
        delta: str = "0.00",
    ) -> ActionResult:
        return ActionResult(
            action=action,
            calendar_sha256=calendar_digest(calendar),
            session=session,
            observed_at=observed_at,
            status=status,
            reason=reason,
            cash_delta_usd=delta,
            state_after=after,
        )

    scheduled = next((row for row in calendar.sessions if row.session_date == session), None)
    if scheduled is None:
        raise ValueError("Corporate-action session is outside the pinned calendar")
    if observed_at < scheduled.open_at:
        return result("pending", "ACTION_NOT_DUE")
    existing = next((row for row in state.applied_actions if row.key == key), None)
    if existing:
        if existing.payload_sha256 != digest:
            raise ValueError(
                "Applied corporate-action payload conflict; explicit correction required"
            )
        return result("already_applied", "ALREADY_APPLIED")
    if not action.visible(observed_at, live) or session < action.effective_session:
        return result("pending", "ACTION_NOT_AVAILABLE")
    position = next((row for row in state.positions if row.asset_id == action.asset_id), None)
    updated = state
    delta = "0.00"
    if action.kind == "split":
        if session != action.effective_session:
            return result("pending", "CHRONOLOGICAL_REPLAY_REQUIRED")
        assert action.ratio_numerator is not None and action.ratio_denominator is not None
        if position is not None:
            exact = (
                Fraction(position.quantity)
                * Fraction(action.ratio_numerator)
                / Fraction(action.ratio_denominator)
            )
            units = exact * 10**6
            if units.denominator != 1:
                return result("pending", "UNSUPPORTED_SPLIT_PRECISION")
            with arithmetic(position.quantity, action.ratio_numerator, action.ratio_denominator):
                shares = Decimal(units.numerator).scaleb(-6)
                updated = replace_position(
                    state,
                    Position(
                        asset_id=position.asset_id,
                        sector=position.sector,
                        quantity=quantity(shares),
                        total_basis_usd=position.total_basis_usd,
                    ),
                    state.cash_usd,
                )
    else:
        assert action.per_share is not None
        entitlements = {row.key: row for row in state.entitlements}
        entitlement = entitlements.get(key)
        if entitlement is None:
            if session != action.effective_session:
                return result("pending", "MISSING_DIVIDEND_ENTITLEMENT")
            entitlement = DividendEntitlement(
                key=key,
                asset_id=action.asset_id,
                ex_session=action.effective_session,
                quantity=position.quantity if position is not None else "0.000000",
                per_share=action.per_share,
                evidence_sha256=digest,
            )
            entitlements[key] = entitlement
        elif (
            entitlement.asset_id != action.asset_id
            or entitlement.ex_session != action.effective_session
            or Decimal(entitlement.per_share) != Decimal(action.per_share)
        ):
            raise ValueError("Dividend entitlement conflicts with action evidence")
        updated = PortfolioState(
            cash_usd=state.cash_usd,
            positions=state.positions,
            applied_actions=state.applied_actions,
            entitlements=tuple(entitlements[k] for k in sorted(entitlements)),
        )
        if action.payable_session is None:
            return result("pending", "PAYABLE_DATE_UNAVAILABLE", updated)
        if session < action.payable_session:
            return result("pending", "WAITING_FOR_PAYABLE_SESSION", updated)
        with arithmetic(state.cash_usd, entitlement.quantity, action.per_share):
            delta = money(Decimal(entitlement.quantity) * Decimal(action.per_share))
            updated = PortfolioState(
                cash_usd=money(Decimal(state.cash_usd) + Decimal(delta)),
                positions=updated.positions,
                applied_actions=updated.applied_actions,
                entitlements=updated.entitlements,
            )
    applied = {row.key: row for row in updated.applied_actions}
    applied[key] = AppliedAction(key=key, payload_sha256=digest)
    updated = PortfolioState(
        cash_usd=updated.cash_usd,
        positions=updated.positions,
        applied_actions=tuple(applied[k] for k in sorted(applied)),
        entitlements=updated.entitlements,
    )
    return result("applied", None, updated, delta)
