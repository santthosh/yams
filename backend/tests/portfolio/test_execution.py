"""Authored SYNTHETIC_DATA_ONLY traces; independent FIX-03/05/06 expectations."""

import json
import random
from datetime import UTC, date, datetime
from decimal import Decimal, localcontext
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.domain.market import MarketBarV1
from backend.domain.strategy import PortfolioConfig, StrategyConfigV1
from backend.market_data.models import Calendar, CorporateAction, Session
from backend.portfolio.corporate_actions import apply_action
from backend.portfolio.execution import (
    ExecutionContext,
    ExecutionPolicy,
    ExecutionResult,
    MarketEvidence,
    OrderIntent,
    PortfolioState,
    Position,
    calendar_digest,
    execute_order,
    next_eligible_session,
    simulate_batch,
)
from backend.portfolio.planner import plan_orders
from backend.portfolio.risk import AllocationTarget

ROOT = Path(__file__).resolve().parents[3] / "data/fixtures"
IDENTITY = UUID("11111111-1111-4111-8111-111111111111")
DIGEST = "a" * 64


def at(day: int, hour: int = 21, minute: int = 0, second: int = 0) -> datetime:
    return datetime(2030, 1, day, hour, minute, second, tzinfo=UTC)


def calendar() -> Calendar:
    return Calendar(
        schema_version=1,
        label="SYNTHETIC_DATA_ONLY",
        id="SYNTHETIC",
        timezone="America/New_York",
        generator_version="authored-test-1",
        timezone_rules_version="synthetic-pinned",
        limitations=("SYNTHETIC_DATA_ONLY",),
        sessions=tuple(
            Session(session_date=date(2030, 1, day), open_at=at(day, 14, 30), close_at=at(day))
            for day in [3, 4, 8, 9, 15]
        ),
    )


def context(
    decision: int = 3, approval: datetime | None = None, **updates: object
) -> ExecutionContext:
    values = dict(
        snapshot_id=IDENTITY,
        snapshot_sha256=DIGEST,
        calendar_sha256=calendar_digest(calendar()),
        mode="synthetic_fixture",
        engine_version="synthetic-test-1",
        execution_mode="historical_replay",
        decision_session=date(2030, 1, decision),
        decision_cutoff=at(decision),
        approved_at=approval or at(decision),
    )
    return ExecutionContext.model_validate(values | updates)


def bar(asset: str = "A", day: int = 4, price: str = "100") -> MarketBarV1:
    return MarketBarV1(
        schema_version=1,
        asset_id=asset,
        session_date=date(2030, 1, day),
        open=price,
        high=price,
        low=price,
        close=price,
        adjusted_close=price,
        volume=1000,
        currency="USD",
        provider="SYNTHETIC_DATA_ONLY",
        published_at=at(day),
        available_at=at(day),
        ingested_at=at(day),
        availability_basis="synthetic",
        price_basis="raw_as_traded",
        volume_basis="raw_as_traded",
        quality_flags=(),
    )


def market(*bars: MarketBarV1, **updates: object) -> MarketEvidence:
    return MarketEvidence.model_validate(
        dict(
            snapshot_id=IDENTITY,
            snapshot_sha256=DIGEST,
            mode="synthetic_fixture",
            freshness="fixture",
            bars=bars,
        )
        | updates
    )


def order(asset: str = "A", side: str = "BUY", qty: str = "2.000000") -> OrderIntent:
    return OrderIntent.model_validate(
        dict(
            key=f"{side}:{asset}",
            asset_id=asset,
            sector="Unknown",
            side=side,
            requested_quantity=qty,
        )
    )


def state(cash: str = "1000.00", qty: str = "0.000000", basis: str = "0.00") -> PortfolioState:
    positions = (
        ()
        if Decimal(qty) == 0
        else (Position(asset_id="A", sector="Unknown", quantity=qty, total_basis_usd=basis),)
    )
    return PortfolioState(cash_usd=cash, positions=positions)


def execute(
    s: PortfolioState,
    o: OrderIntent,
    *,
    ctx: ExecutionContext | None = None,
    evidence: MarketEvidence | None = None,
    observed_at: datetime | None = None,
    min_trade_usd: str = "5.00",
    policy: ExecutionPolicy | None = None,
) -> ExecutionResult:
    return execute_order(
        s,
        o,
        ctx or context(),
        calendar(),
        evidence or market(bar()),
        observed_at=observed_at or at(4),
        min_trade_usd=min_trade_usd,
        policy=policy or ExecutionPolicy(),
    )


def test_fix06_strict_future_open_equality_and_holidays() -> None:
    fixture = json.loads((ROOT / "fix-06/case.json").read_text())
    schedule = calendar().model_copy(
        update={
            "sessions": tuple(
                Session.model_validate(value) for value in fixture["inputs"]["schedule"]
            )
        }
    )
    cutoff = datetime.fromisoformat(fixture["inputs"]["cutoff"])
    actual = [
        next_eligible_session(
            schedule, cutoff, datetime.fromisoformat(value)
        ).session_date.isoformat()
        for value in fixture["inputs"]["approvals"]
    ]
    assert actual == fixture["expected"]["eligible_sessions"]
    with pytest.raises(ValueError, match="No eligible"):
        next_eligible_session(schedule, at(15), at(15))
    with pytest.raises(ValueError, match="nonempty"):
        next_eligible_session(schedule.model_copy(update={"sessions": ()}), at(3), at(3))
    with pytest.raises(ValidationError):
        next_eligible_session(schedule, datetime(2030, 1, 3), at(3))


def test_fix03_buy_sell_trace_and_input_immutability() -> None:
    fixture = json.loads((ROOT / "fix-03/case.json").read_text())
    expected = fixture["expected"]
    initial = state()
    buy = execute(initial, order())
    assert buy.fill is not None
    assert Decimal(buy.fill.executed_price) == Decimal(expected["buy_price"])
    assert buy.fill.cash_delta_usd == "-" + expected["buy_debit"]
    assert buy.state_after.cash_usd == expected["cash_after_buy"]
    assert initial == state()
    sell = execute(
        buy.state_after,
        order(side="SELL"),
        ctx=context(4),
        evidence=market(bar(day=8)),
        observed_at=at(8),
    )
    assert sell.fill is not None
    assert sell.fill.cash_delta_usd == expected["sell_credit"]
    assert sell.state_after.cash_usd == expected["cash_after_sell"]
    assert sell.state_after.positions == ()
    assert sell.fill.removed_basis_usd == "200.20" and sell.fill.realized_pnl_usd == "-0.40"
    assert ExecutionResult.model_validate_json(sell.model_dump_json()) == sell


def test_fix03_affordability_minimum_and_price_gap() -> None:
    expected = json.loads((ROOT / "fix-03/case.json").read_text())["expected"]
    result = execute(state("100.00"), order(qty="1.000000"))
    assert result.filled_quantity == expected["affordable_quantity"]
    assert result.skipped_quantity == expected["closed_shortfall_quantity"]
    assert result.pending_quantity == "0.000000" and result.terminal
    assert result.status == "partially_filled" and result.reason == "INSUFFICIENT_CASH"
    assert result.state_after.cash_usd == expected["affordable_remaining_cash"]
    assert result.fill is not None and result.fill.cash_delta_usd == "-100.00"
    below = execute(state("4.99"), order(qty="1.000000"))
    assert below.fill is None and below.reason == expected["below_minimum_reason"]
    gap = execute(state("100.00"), order(qty="1.000000"), evidence=market(bar(price="200")))
    # Independently: floor_6(100/200.2)=.499500; *200.2=99.9999 ->100.00.
    assert gap.filled_quantity == "0.499500" and gap.state_after.cash_usd == "0.00"


def test_fees_and_average_cost_partial_full_sale() -> None:
    fee = execute(
        state("100.00"), order(qty="1.000000"), policy=ExecutionPolicy(commission_usd="1.00")
    )
    # floor_6(99/100.1)=.989010; rounded gross99 +fee1 =100.
    assert fee.filled_quantity == "0.989010" and fee.state_after.cash_usd == "0.00"
    assert fee.state_after.positions[0].total_basis_usd == "100.00"
    partial = execute(state("0.00", "3.000000", "100.00"), order(side="SELL", qty="1.000000"))
    assert partial.fill is not None and partial.fill.removed_basis_usd == "33.33"
    assert partial.fill.realized_pnl_usd == "66.57"
    assert partial.state_after.positions[0].total_basis_usd == "66.67"
    full = execute(partial.state_after, order(side="SELL"))
    assert full.fill is not None and full.fill.removed_basis_usd == "66.67"
    assert full.state_after.cash_usd == "299.70" and full.state_after.positions == ()


@pytest.mark.parametrize(("price", "debit"), [("1.005", "1.00"), ("1.015", "1.02")])
def test_half_even_cents_and_ambient_precision(price: str, debit: str) -> None:
    with localcontext() as ctx:
        ctx.prec = 6
        result = execute(
            state("1000000.00"),
            order(qty="1.000000"),
            evidence=market(bar(price=price)),
            min_trade_usd="0.00",
            policy=ExecutionPolicy(slippage_fraction="0"),
        )
    assert result.fill is not None and result.fill.cash_delta_usd == "-" + debit
    assert result.state_after.cash_usd == format(Decimal("1000000") - Decimal(debit), ".2f")


def test_missing_stale_future_and_unverified_open_never_substitutes() -> None:
    intent = order()
    for evidence in [
        market(),
        market(bar(day=3), bar(day=8)),
        market(bar().model_copy(update={"price_basis": "provider_unverified"})),
        market(bar().model_copy(update={"quality_flags": ("PRICE_JUMP",)})),
    ]:
        result = execute(state(), intent, evidence=evidence)
        assert result.status == "pending" and result.reason == "PENDING_DATA"
        assert result.fill is None and result.state_after == state()
    before = execute(state(), intent, observed_at=at(4, 14, 29))
    assert before.reason == "WAITING_FOR_ELIGIBLE_OPEN"
    unavailable = execute(state(), intent, observed_at=at(4, 15))
    assert unavailable.reason == "PENDING_DATA"
    stale = execute(
        state(),
        intent,
        ctx=context(execution_mode="current_paper"),
        evidence=market(bar(), freshness="stale"),
    )
    assert stale.fill is None and stale.reason == "STALE_DATA"
    late_ingestion = market(bar().model_copy(update={"ingested_at": at(8)}))
    live = execute(
        state(), intent, ctx=context(execution_mode="current_paper"), evidence=late_ingestion
    )
    replay = execute(state(), intent, evidence=late_ingestion)
    assert live.fill is None and replay.fill is not None
    late_approval = execute(
        state(),
        intent,
        ctx=context(approval=at(4, 14, 30)),
        evidence=market(bar(day=4)),
        observed_at=at(8),
    )
    assert late_approval.eligible_session.session_date == date(2030, 1, 8)
    assert late_approval.fill is None


def test_sell_before_buy_and_no_unposted_sale_proceeds() -> None:
    initial = PortfolioState(
        cash_usd="0.00",
        positions=(
            Position(asset_id="B", sector="Unknown", quantity="2.000000", total_basis_usd="200.00"),
        ),
    )
    intents = (order("A", qty="1.000000"), order("B", "SELL"))
    trace = simulate_batch(
        initial,
        intents,
        context(),
        calendar(),
        market(bar("A"), bar("B")),
        observed_at=at(4),
        min_trade_usd="5.00",
    )
    expected = json.loads((ROOT / "fix-03/case.json").read_text())["expected"]
    assert [result.order.side for result in trace] == ["SELL", "BUY"]
    assert trace[0].state_after.cash_usd == expected["same_batch_cash_after_sell"]
    assert trace[1].state_after.cash_usd == expected["same_batch_cash_after_buy"]
    assert initial.cash_usd == "0.00" and initial.positions[0].quantity == "2.000000"
    missing = simulate_batch(
        initial,
        intents,
        context(),
        calendar(),
        market(bar("A")),
        observed_at=at(4),
        min_trade_usd="5.00",
    )
    assert missing[0].status == "pending"
    assert missing[1].fill is None and missing[1].reason == "INSUFFICIENT_CASH"
    assert missing[1].state_after == initial
    assert (
        simulate_batch(
            initial,
            tuple(reversed(intents)),
            context(),
            calendar(),
            market(bar("B"), bar("A")),
            observed_at=at(4),
            min_trade_usd="5.00",
        )
        == trace
    )
    with pytest.raises(ValueError, match="Duplicate"):
        simulate_batch(
            initial,
            (intents[0], intents[0]),
            context(),
            calendar(),
            market(bar("A")),
            observed_at=at(4),
            min_trade_usd="5.00",
        )


def test_long_only_and_invalid_lineage_or_policy() -> None:
    no_position = execute(state(), order(side="SELL"))
    assert no_position.fill is None and no_position.reason == "NO_POSITION"
    limited = execute(state("0.00", "1.000000", "80.00"), order(side="SELL"))
    assert limited.filled_quantity == "1.000000" and limited.skipped_quantity == "1.000000"
    assert limited.reason == "INSUFFICIENT_HOLDINGS" and limited.state_after.positions == ()
    with pytest.raises(ValueError, match="lineage"):
        execute(state(), order(), evidence=market(bar(), snapshot_sha256="b" * 64))
    with pytest.raises(ValueError, match="Calendar"):
        execute(state(), order(), ctx=context(calendar_sha256="b" * 64))
    with pytest.raises(ValidationError):
        ExecutionPolicy(slippage_fraction="1")
    with pytest.raises(ValidationError):
        state("-1.00")
    with pytest.raises(ValidationError):
        order(qty="0.000000")
    with pytest.raises(ValidationError):
        market(bar(), bar())


def config(**updates: object) -> PortfolioConfig:
    value = StrategyConfigV1.from_json((ROOT / "fix-01/strategy.canonical.json").read_bytes())
    return type(value.portfolio).model_validate(value.portfolio.model_dump() | updates)


def target(weight: str) -> tuple[AllocationTarget, ...]:
    return (AllocationTarget(asset_id="A", sector="Unknown", weight=weight),)


def test_planner_band_equality_and_mandatory_position_correction() -> None:
    marks = market(bar(day=3))
    held = state("800.00", "2.000000", "200.00")
    small = plan_orders(held, target("0.19"), "0.81", config(), context(), calendar(), marks)
    assert small.actions[0].side == "HOLD" and small.actions[0].reason == "WITHIN_REBALANCE_BAND"
    equal = plan_orders(held, target("0.18"), "0.82", config(), context(), calendar(), marks)
    assert equal.orders[0].requested_quantity == "0.200000"
    assert equal.orders[0].side == "SELL"
    breach = plan_orders(
        state("790.00", "2.100000", "210.00"),
        target("0.2"),
        "0.8",
        config(),
        context(),
        calendar(),
        marks,
    )
    assert breach.actions[0].mandatory_risk_correction
    assert breach.orders[0].requested_quantity == "0.100000"
    # Even mandatory corrections cannot invent an under-minimum trade.
    tiny = plan_orders(
        state("799.00", "2.010000", "201.00"),
        target("0.2"),
        "0.8",
        config(),
        context(),
        calendar(),
        marks,
    )
    assert tiny.actions[0].side == "HOLD" and tiny.actions[0].reason == "BELOW_MIN_TRADE"
    assert tiny.actions[0].mandatory_risk_correction


def test_planner_coherent_valuation_empty_missing_and_target_validation() -> None:
    plan = plan_orders(
        state(), target("0.2"), "0.8", config(), context(), calendar(), market(bar(day=3))
    )
    assert plan.portfolio_value_usd == "1000.00" and plan.orders[0].requested_quantity == "2.000000"
    assert plan.actions[0].estimated_gross_usd == "200.20"
    assert plan.actions[0].estimated_slippage_usd == "0.20"
    missing = plan_orders(
        state("800.00", "2.000000", "200.00"),
        target("0.2"),
        "0.8",
        config(),
        context(),
        calendar(),
        market(),
    )
    assert missing.status == "blocked" and missing.missing_assets == ("A",)
    assert missing.portfolio_value_usd is None and not missing.orders
    empty = plan_orders(state(), (), "1", config(), context(), calendar(), market())
    assert empty.status == "ready" and empty.actions == () and empty.orders == ()
    zero = plan_orders(state("0.00"), (), "1", config(), context(), calendar(), market())
    assert zero.reason == "ZERO_PORTFOLIO_VALUE" and zero.portfolio_value_usd == "0.00"
    with pytest.raises(ValueError, match="invalid target"):
        plan_orders(
            state(), target("0.9"), "0.1", config(), context(), calendar(), market(bar(day=3))
        )


def action(kind: str = "split", **updates: object) -> CorporateAction:
    values = dict(
        asset_id="A",
        event_id="split-A" if kind == "split" else "dividend-A",
        kind=kind,
        effective_session=date(2030, 1, 4 if kind == "split" else 8),
        provider="SYNTHETIC_DATA_ONLY",
        currency="USD",
        available_at=at(3),
        ingested_at=at(3),
        ratio_numerator="2" if kind == "split" else None,
        ratio_denominator="1" if kind == "split" else None,
        per_share=None if kind == "split" else "1.25",
        payable_session=None if kind == "split" else date(2030, 1, 15),
    )
    return CorporateAction.model_validate(values | updates)


def test_fix05_split_entitlement_survives_sale_and_dividend_once() -> None:
    expected = json.loads((ROOT / "fix-05/case.json").read_text())["expected"]
    initial = state("0.00", "2.000000", "200.00")
    split = apply_action(
        initial,
        action(),
        session=date(2030, 1, 4),
        observed_at=at(4),
        live=False,
        calendar=calendar(),
    )
    assert split.status == "applied" and split.cash_delta_usd == expected["split_cash_delta"]
    assert split.state_after.positions[0].quantity == expected["quantity_after_split"]
    assert split.state_after.positions[0].total_basis_usd == expected["total_basis_after_split"]
    assert initial.positions[0].quantity == "2.000000"
    again = apply_action(
        split.state_after,
        action(),
        session=date(2030, 1, 4),
        observed_at=at(4),
        live=False,
        calendar=calendar(),
    )
    assert again.status == "already_applied" and again.state_after == split.state_after
    captured = apply_action(
        split.state_after,
        action("dividend"),
        session=date(2030, 1, 8),
        observed_at=at(8),
        live=False,
        calendar=calendar(),
    )
    assert (
        captured.status == "pending"
        and captured.cash_delta_usd == expected["cash_dividend_before_payable"]
    )
    assert captured.state_after.entitlements[0].quantity == "4.000000"
    sold = execute(
        captured.state_after,
        order(side="SELL", qty="4.000000"),
        ctx=context(8),
        evidence=market(bar(day=9, price="48.75")),
        observed_at=at(9),
    )
    assert sold.state_after.positions == ()
    paid = apply_action(
        sold.state_after,
        action("dividend"),
        session=date(2030, 1, 15),
        observed_at=at(15),
        live=False,
        calendar=calendar(),
    )
    assert paid.cash_delta_usd == expected["cash_dividend_on_payable"]
    assert Decimal(paid.state_after.cash_usd) - Decimal(sold.state_after.cash_usd) == Decimal(
        "5.00"
    )
    repeated = apply_action(
        paid.state_after,
        action("dividend"),
        session=date(2030, 1, 15),
        observed_at=at(15),
        live=False,
        calendar=calendar(),
    )
    assert repeated.status == "already_applied" and repeated.state_after == paid.state_after


def test_missing_payable_entitlement_split_precision_and_payload_conflict() -> None:
    initial = state("0.00", "1.000000", "100.00")
    missing = apply_action(
        initial,
        action("dividend", payable_session=None),
        session=date(2030, 1, 8),
        observed_at=at(8),
        live=False,
        calendar=calendar(),
    )
    assert missing.reason == "PAYABLE_DATE_UNAVAILABLE" and missing.cash_delta_usd == "0.00"
    missing_entitlement = apply_action(
        initial,
        action("dividend"),
        session=date(2030, 1, 15),
        observed_at=at(15),
        live=False,
        calendar=calendar(),
    )
    assert missing_entitlement.reason == "MISSING_DIVIDEND_ENTITLEMENT"
    resolved = apply_action(
        missing.state_after,
        action("dividend"),
        session=date(2030, 1, 15),
        observed_at=at(15),
        live=False,
        calendar=calendar(),
    )
    assert resolved.cash_delta_usd == "1.25"
    third = apply_action(
        initial,
        action(ratio_numerator="1", ratio_denominator="3"),
        session=date(2030, 1, 4),
        observed_at=at(4),
        live=False,
        calendar=calendar(),
    )
    assert third.reason == "UNSUPPORTED_SPLIT_PRECISION" and third.state_after == initial
    late = apply_action(
        initial,
        action(),
        session=date(2030, 1, 8),
        observed_at=at(8),
        live=False,
        calendar=calendar(),
    )
    assert late.reason == "CHRONOLOGICAL_REPLAY_REQUIRED"
    invisible = apply_action(
        initial,
        action(available_at=at(8)),
        session=date(2030, 1, 4),
        observed_at=at(4),
        live=False,
        calendar=calendar(),
    )
    assert invisible.reason == "ACTION_NOT_AVAILABLE"
    split = apply_action(
        initial,
        action(),
        session=date(2030, 1, 4),
        observed_at=at(4),
        live=False,
        calendar=calendar(),
    )
    with pytest.raises(ValueError, match="conflict"):
        apply_action(
            split.state_after,
            action(ratio_numerator="3"),
            session=date(2030, 1, 4),
            observed_at=at(4),
            live=False,
            calendar=calendar(),
        )


def test_randomized_cash_basis_share_conservation() -> None:
    rng = random.Random(3503)
    for _ in range(100):
        cash = f"{rng.randint(0, 10000)}.00"
        shares = f"{rng.randint(0, 100)}.000000"
        initial = state(cash, shares, "0.00" if Decimal(shares) == 0 else "500.00")
        intent = order(side=rng.choice(["BUY", "SELL"]), qty=f"{rng.randint(1, 150)}.123456")
        result = execute(initial, intent, evidence=market(bar(price=f"{rng.randint(1, 1000)}.01")))
        assert Decimal(result.state_after.cash_usd) >= 0
        assert all(
            Decimal(p.quantity) >= 0 and Decimal(p.total_basis_usd) >= 0
            for p in result.state_after.positions
        )
        assert (
            Decimal(result.filled_quantity)
            + Decimal(result.pending_quantity)
            + Decimal(result.skipped_quantity)
        ) == Decimal(intent.requested_quantity)
        if result.fill:
            assert Decimal(result.state_after.cash_usd) == Decimal(cash) + Decimal(
                result.fill.cash_delta_usd
            )
            before_basis = sum((Decimal(p.total_basis_usd) for p in initial.positions), Decimal(0))
            after_basis = sum(
                (Decimal(p.total_basis_usd) for p in result.state_after.positions), Decimal(0)
            )
            if intent.side == "BUY":
                assert after_basis == before_basis - Decimal(result.fill.cash_delta_usd)
            else:
                assert after_basis == before_basis - Decimal(result.fill.removed_basis_usd)
        assert initial == state(cash, shares, "0.00" if Decimal(shares) == 0 else "500.00")


def test_minimum_uses_executable_unrounded_notional_and_cannot_spend_fees() -> None:
    exact = execute(
        state(),
        order(qty="1.000000"),
        evidence=market(bar(price="5")),
        policy=ExecutionPolicy(slippage_fraction="0"),
    )
    assert exact.fill is not None and exact.fill.gross_usd == "5.00"
    # Sell5 * .999 =4.995, below minimum even though cash rounding would give5.00.
    below = execute(
        state("0.00", "1.000000", "5.00"),
        order(side="SELL", qty="1.000000"),
        evidence=market(bar(price="5")),
    )
    assert below.fill is None and below.reason == "BELOW_MIN_TRADE"
    fees = execute(
        state("0.00", "1.000000", "100.00"),
        order(side="SELL", qty="1.000000"),
        policy=ExecutionPolicy(commission_usd="200.00"),
    )
    assert fees.fill is None and fees.reason == "INSUFFICIENT_CASH"
    assert (
        fees.state_after.cash_usd == "0.00" and fees.state_after.positions[0].quantity == "1.000000"
    )


def test_sector_and_cash_floor_corrections_bypass_band_with_executable_minimum() -> None:
    # $10,000 NAV: two20.5% holdings in one sector breach40%, neither breaches30%.
    # Reducing each to20% changes only0.5pp; both must still sell0.5 shares at100.
    held = PortfolioState(
        cash_usd="5900.00",
        positions=tuple(
            Position(
                asset_id=identity, sector="Unknown", quantity="20.500000", total_basis_usd="2000.00"
            )
            for identity in "AB"
        ),
    )
    targets = tuple(
        AllocationTarget(asset_id=identity, sector="Unknown", weight="0.2") for identity in "AB"
    )
    marks = market(bar("A", day=3), bar("B", day=3))
    plan = plan_orders(
        held, targets, "0.6", config(max_position_weight="0.3"), context(), calendar(), marks
    )
    assert all(row.mandatory_risk_correction and row.side == "SELL" for row in plan.actions)
    assert [row.requested_quantity for row in plan.orders] == ["0.500000", "0.500000"]
    reversed_state = PortfolioState(
        cash_usd=held.cash_usd, positions=tuple(reversed(held.positions))
    )
    assert (
        plan_orders(
            reversed_state,
            tuple(reversed(targets)),
            "0.6",
            config(max_position_weight="0.3"),
            context(),
            calendar(),
            market(bar("B", day=3), bar("A", day=3)),
        )
        == plan
    )
    # Position/sector caps1 do not bind; cash4% <5% alone makes a1pp sell mandatory.
    cash_only = plan_orders(
        state("40.00", "9.600000", "960.00"),
        target("0.95"),
        "0.05",
        config(max_position_weight="1", max_sector_weight="1"),
        context(),
        calendar(),
        market(bar(day=3)),
    )
    assert cash_only.actions[0].mandatory_risk_correction
    assert cash_only.orders[0].requested_quantity == "0.100000"


def test_future_or_incomplete_close_cannot_value_a_plan() -> None:
    for mark in [
        bar(day=4),
        bar(day=3).model_copy(
            update={"available_at": at(3, 14, 30), "published_at": at(3, 14, 30)}
        ),
        bar(day=3).model_copy(update={"available_at": at(4)}),
    ]:
        result = plan_orders(
            state(), target("0.2"), "0.8", config(), context(), calendar(), market(mark)
        )
        assert result.status == "blocked" and result.orders == ()
    with pytest.raises(ValueError, match="completed session"):
        execute(state(), order(), ctx=context(decision_cutoff=at(3, 20)))
    with pytest.raises(ValueError, match="classification"):
        plan_orders(
            state("800.00", "2.000000", "200.00"),
            (AllocationTarget(asset_id="A", sector="Tech", weight="0.2"),),
            "0.8",
            config(),
            context(),
            calendar(),
            market(bar(day=3)),
        )


def test_corporate_action_observation_refresh_is_not_a_second_distribution() -> None:
    initial = state("0.00", "2.000000", "200.00")
    split = apply_action(
        initial,
        action(),
        session=date(2030, 1, 4),
        observed_at=at(4),
        live=True,
        calendar=calendar(),
    )
    observed_again = action(ratio_numerator="2.00", ratio_denominator="1.0", ingested_at=at(8))
    again = apply_action(
        split.state_after,
        observed_again,
        session=date(2030, 1, 8),
        observed_at=at(8),
        live=True,
        calendar=calendar(),
    )
    assert again.status == "already_applied" and again.state_after == split.state_after
    invisible = apply_action(
        initial,
        action(ingested_at=at(8)),
        session=date(2030, 1, 4),
        observed_at=at(4),
        live=True,
        calendar=calendar(),
    )
    assert invisible.reason == "ACTION_NOT_AVAILABLE"


def test_known_future_payable_date_cannot_credit_early() -> None:
    initial = state("0.00", "2.000000", "200.00")
    captured = apply_action(
        initial,
        action("dividend"),
        session=date(2030, 1, 8),
        observed_at=at(8),
        live=False,
        calendar=calendar(),
    )
    early = apply_action(
        captured.state_after,
        action("dividend"),
        session=date(2030, 1, 15),
        observed_at=at(9),
        live=False,
        calendar=calendar(),
    )
    assert early.reason == "ACTION_NOT_DUE" and early.cash_delta_usd == "0.00"
    assert early.state_after == captured.state_after
    with pytest.raises(ValueError, match="outside the pinned calendar"):
        apply_action(
            initial,
            action(),
            session=date(2030, 1, 5),
            observed_at=at(8),
            live=False,
            calendar=calendar(),
        )


def test_planner_feasible_preview_is_not_a_fill_or_spendable_proceeds() -> None:
    initial = PortfolioState(
        cash_usd="0.00",
        positions=(
            Position(asset_id="B", sector="Unknown", quantity="2.000000", total_basis_usd="200.00"),
        ),
    )
    plan = plan_orders(
        initial,
        target("0.5"),
        "0.5",
        config(max_position_weight="1", max_sector_weight="1"),
        context(),
        calendar(),
        market(bar("A", day=3), bar("B", day=3)),
    )
    assert [step.order.side for step in plan.preview] == ["SELL", "BUY"]
    assert plan.projected_cash_usd == "99.70"
    assert initial.cash_usd == "0.00" and initial.positions[0].quantity == "2.000000"
    assert all("execution_at" not in step.model_dump() for step in plan.preview)
    assert all(
        step.effect is None or "execution_at" not in step.effect.model_dump()
        for step in plan.preview
    )
    # The actual opening path still sees POSTED zero cash if the sell has no bar.
    attempted = simulate_batch(
        initial,
        plan.orders,
        context(),
        calendar(),
        market(bar("A")),
        observed_at=at(4),
        min_trade_usd="5.00",
    )
    assert attempted[0].status == "pending" and attempted[1].fill is None
    # With both eligible bars, shared pricing gives the same amounts at equal prices.
    actual = simulate_batch(
        initial,
        plan.orders,
        context(),
        calendar(),
        market(bar("A"), bar("B")),
        observed_at=at(4),
        min_trade_usd="5.00",
    )
    assert actual[-1].state_after.cash_usd == plan.projected_cash_usd
    assert actual[-1].fill is not None and plan.preview[-1].effect is not None
    assert actual[-1].fill.cash_delta_usd == plan.preview[-1].effect.cash_delta_usd
