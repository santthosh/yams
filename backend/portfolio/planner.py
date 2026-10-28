"""Coherent close valuation -> target deltas; creates intent, never synthetic fills."""

from decimal import Decimal
from fractions import Fraction
from typing import Literal

from backend.domain.strategy import PortfolioConfig
from backend.domain.types import AssetId, Contract, FractionString, Money, Quantity, Reason
from backend.market_data.models import Calendar
from backend.portfolio.execution import (
    DEFAULT_EXECUTION_POLICY,
    ExecutionContext,
    ExecutionPolicy,
    MarketEvidence,
    OrderIntent,
    PortfolioState,
    QuoteTransition,
    arithmetic,
    money,
    quantity,
    quote_order,
)
from backend.portfolio.risk import AllocationTarget, assess_targets
from backend.portfolio.valuation import value_close


class PlannedAction(Contract):
    asset_id: AssetId
    side: Literal["BUY", "SELL", "HOLD"]
    requested_quantity: Quantity
    preview_executable_quantity: Quantity
    current_weight: FractionString
    target_weight: FractionString
    estimated_gross_usd: Money
    estimated_commission_usd: Money
    estimated_slippage_usd: Money
    reason: Reason
    mandatory_risk_correction: bool


class OrderPlan(Contract):
    context: ExecutionContext
    policy: ExecutionPolicy
    status: Literal["ready", "blocked"]
    portfolio_value_usd: Money | None
    actions: tuple[PlannedAction, ...]
    orders: tuple[OrderIntent, ...]
    missing_assets: tuple[AssetId, ...]
    reason: Reason | None
    preview: tuple[QuoteTransition, ...] = ()
    projected_cash_usd: Money | None = None


def _weight_text(value: Fraction) -> str:
    with arithmetic(str(value.numerator), str(value.denominator)):
        return format(Decimal(value.numerator) / Decimal(value.denominator), "f")


def plan_orders(
    state: PortfolioState,
    targets: tuple[AllocationTarget, ...],
    cash_target_weight: FractionString,
    config: PortfolioConfig,
    context: ExecutionContext,
    calendar: Calendar,
    marks: MarketEvidence,
    *,
    policy: ExecutionPolicy = DEFAULT_EXECUTION_POLICY,
) -> OrderPlan:
    """Use one coherent decision close; actual opening affordability is checked later."""
    report = assess_targets(targets, cash_target_weight, config)
    if not report.compliant:
        raise ValueError("Cannot plan an invalid target allocation")
    positions = {row.asset_id: row for row in state.positions if Decimal(row.quantity) > 0}
    target_map = {row.asset_id: row for row in targets}
    ids = sorted(positions.keys() | target_map.keys())
    valuation = value_close(state, context, calendar, marks, required_assets=tuple(target_map))
    valid, missing = valuation.marks, valuation.missing_assets
    if valuation.nav is None:
        return OrderPlan(
            context=context,
            policy=policy,
            status="blocked",
            portfolio_value_usd=None,
            actions=(),
            orders=(),
            missing_assets=missing,
            reason="INSUFFICIENT_MARKET_DATA",
        )
    for identity in positions.keys() & target_map.keys():
        if positions[identity].sector != target_map[identity].sector:
            raise ValueError(
                "Position/target sector evidence must use the same as-of classification"
            )
    values, nav = valuation.values, valuation.nav
    if nav == 0:
        return OrderPlan(
            context=context,
            policy=policy,
            status="ready",
            portfolio_value_usd="0.00",
            actions=(),
            orders=(),
            missing_assets=(),
            reason="ZERO_PORTFOLIO_VALUE",
            projected_cash_usd="0.00",
        )
    sector_weights: dict[str, Fraction] = {}
    for identity, holding in positions.items():
        sector_weights[holding.sector] = (
            sector_weights.get(holding.sector, Fraction(0)) + values[identity] / nav
        )
    cash_breach = Fraction(state.cash_usd) / nav < Fraction(config.min_cash_weight)
    actions = []
    orders = []
    for identity in ids:
        position = positions.get(identity)
        target = target_map.get(identity)
        current = values.get(identity, Fraction(0)) / nav
        desired = Fraction(target.weight) if target else Fraction(0)
        delta = desired - current
        mandatory = delta < 0 and (
            current > Fraction(config.max_position_weight)
            or sector_weights[position.sector if position else "Unknown"]
            > Fraction(config.max_sector_weight)
            or cash_breach
            or len(positions) > config.max_positions
        )
        side: Literal["BUY", "SELL", "HOLD"] = (
            "BUY" if delta > 0 else "SELL" if delta < 0 else "HOLD"
        )
        reason = "MANDATORY_RISK_CORRECTION" if mandatory else "TARGET_REBALANCE"
        raw = valid[identity].close
        requested = "0.000000"
        gross = fee = slippage = "0.00"
        if delta == 0 or (
            abs(delta) < Fraction(config.rebalance_band_absolute_weight) and not mandatory
        ):
            side, reason = "HOLD", "WITHIN_REBALANCE_BAND"
        else:
            exact_quantity = abs(delta) * nav / Fraction(raw)
            units = (exact_quantity * 10**6).numerator // (exact_quantity * 10**6).denominator
            if position is not None and delta < 0:
                units = min(units, int(Fraction(position.quantity) * 10**6))
            with arithmetic(str(units)):
                qty = Decimal(units).scaleb(-6)
                if qty == 0:
                    side, reason = "HOLD", "BELOW_QUANTITY_PRECISION"
                else:
                    requested = quantity(qty)
        if side != "HOLD":
            orders.append(
                OrderIntent(
                    key=f"{side}:{identity}",
                    asset_id=identity,
                    sector=target.sector if target else positions[identity].sector,
                    side=side,
                    requested_quantity=requested,
                )
            )
        actions.append(
            PlannedAction(
                asset_id=identity,
                side=side,
                requested_quantity=requested,
                preview_executable_quantity="0.000000",
                current_weight=_weight_text(current),
                target_weight=_weight_text(desired),
                estimated_gross_usd=gross,
                estimated_commission_usd=fee,
                estimated_slippage_usd=slippage,
                reason=reason,
                mandatory_risk_correction=mandatory,
            )
        )
    with arithmetic(str(nav.numerator), str(nav.denominator)):
        nav_text = money(Decimal(nav.numerator) / Decimal(nav.denominator))
    ordered = tuple(sorted(orders, key=lambda o: (o.side != "SELL", o.asset_id)))
    projected = state
    preview = []
    for intent in ordered:
        transition = quote_order(
            projected,
            intent,
            valid[intent.asset_id].close,
            min_trade_usd=config.min_trade_usd,
            policy=policy,
        )
        preview.append(transition)
        projected = transition.state_after
    by_asset = {quote.order.asset_id: quote for quote in preview}
    reconciled = []
    for planned in actions:
        quoted = by_asset.get(planned.asset_id)
        if quoted is None:
            reconciled.append(planned)
            continue
        updates: dict[str, object] = {"preview_executable_quantity": quoted.executable_quantity}
        if quoted.effect is None:
            updates.update(
                side="HOLD",
                requested_quantity="0.000000",
                reason=quoted.reason,
                estimated_gross_usd="0.00",
                estimated_commission_usd="0.00",
                estimated_slippage_usd="0.00",
            )
        else:
            updates.update(
                estimated_gross_usd=quoted.effect.gross_usd,
                estimated_commission_usd=quoted.effect.commission_usd,
                estimated_slippage_usd=quoted.effect.slippage_usd,
            )
        reconciled.append(PlannedAction.model_validate(planned.model_dump() | updates))
    return OrderPlan(
        context=context,
        policy=policy,
        status="ready",
        portfolio_value_usd=nav_text,
        actions=tuple(reconciled),
        orders=tuple(o for o in ordered if by_asset[o.asset_id].effect is not None),
        missing_assets=(),
        reason=None,
        preview=tuple(preview),
        projected_cash_usd=projected.cash_usd,
    )
