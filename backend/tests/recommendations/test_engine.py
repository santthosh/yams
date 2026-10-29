import json
from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal

import pytest
from pydantic import ValidationError

from backend.domain.recommendation_api import RecommendationRequest
from backend.domain.strategy import StrategyConfigV1
from backend.market_data.files import PinnedSnapshot
from backend.market_data.models import Calendar, CorporateAction
from backend.market_data.repository import MarketRepository, MarketView
from backend.portfolio.corporate_actions import action_hash, action_key
from backend.portfolio.execution import DividendEntitlement, PortfolioState, Position
from backend.portfolio.recommendation_contracts import RecommendationPayload
from backend.portfolio.recommendation_engine import compose_recommendation, prepare_recommendation


def test_complete_measured_evidence_and_independent_preview_costs(
    pinned: PinnedSnapshot, payload: RecommendationPayload
) -> None:
    before = payload.state.model_dump_json()
    prepared = prepare_recommendation(pinned, payload)
    result, forecast = compose_recommendation(payload, prepared, pinned)
    oracle = json.loads(Path(__file__).with_name("expected_cases.json").read_text())[
        "cash_account_authored_target_preview"
    ]
    assert {x.asset_id: x.weight for x in result.target_weights} == oracle["targets"]
    assert result.cash_target_weight == oracle["cash_target_weight"]
    assert result.summary_action == "BUY" and len(result.candidates) == 5
    assert {x.asset_id: x.estimated_quantity for x in result.actions} == oracle[
        "estimated_quantity"
    ]
    assert {x.asset_id: x.estimated_notional_usd for x in result.actions} == dict.fromkeys(
        oracle["targets"], "200.00"
    )
    assert result.estimated_total_trade_cost_usd == oracle["estimated_total_trade_cost_usd"]
    assert prepared.plan.projected_cash_usd == oracle["preview_cash_usd"]
    assert all(row.side == "BUY" and row.label == "INCREASE" for row in result.actions)
    assert all(row.explanation and row.reason_codes for row in result.actions)
    assert all(row.score is not None or row.exclusion_reasons for row in result.candidates)
    assert any(row.exclusion_reasons for row in result.candidates)
    assert all(row.contributions for row in result.candidates if row.score is not None)
    assert payload.state.model_dump_json() == before and not payload.state.positions
    assert forecast.initial_value_usd == "1000.00"
    assert forecast.current_allocation.cash_weight == "1"
    assert forecast.proposed_allocation.upfront_cost_usd == "0.60"
    assert sum(map(Decimal, [x.weight for x in forecast.proposed_allocation.weights])) + Decimal(
        forecast.proposed_allocation.cash_weight
    ) == pytest.approx(Decimal(1), abs=Decimal("1e-8"))
    assert (
        result.created_at == payload.decision_cutoff_utc
    )  # explicit future-dated synthetic replay


def test_empty_universe_is_cash_with_all_rejections_retained(
    pinned: PinnedSnapshot, payload: RecommendationPayload
) -> None:
    rules = payload.config.model_dump(mode="json")
    rules["universe"]["min_price_usd"] = "1000000"
    config = StrategyConfigV1.model_validate(rules)
    payload = payload.model_copy(
        update={
            "config_canonical_json": config.canonical_bytes().decode(),
            "config_sha256": config.config_hash(),
        }
    )
    result, forecast = compose_recommendation(
        payload, prepare_recommendation(pinned, payload), pinned
    )
    assert result.summary_action == "ALLOCATE_TO_CASH"
    assert result.target_weights == () and Decimal(result.cash_target_weight) == 1
    assert result.actions == () and result.estimated_total_trade_cost_usd == "0.00"
    assert len(result.candidates) == 5 and all(row.exclusion_reasons for row in result.candidates)
    assert forecast.current_allocation == forecast.proposed_allocation


def test_under_band_hold_has_zero_orders_cost_and_identical_forecast_allocations(
    pinned: PinnedSnapshot, payload: RecommendationPayload
) -> None:
    state = PortfolioState(
        cash_usd="410.00",
        positions=tuple(
            Position(asset_id=asset, sector=sector, quantity=quantity, total_basis_usd="100.00")
            for asset, sector, quantity in [
                ("SYN:AAA", "Technology", "2.714285"),
                ("SYN:BBB", "Technology", "2.857142"),
                ("SYN:CCC", "Unknown", "2.985074"),
            ]
        ),
    )
    payload = payload.model_copy(update={"state": state})
    prepared = prepare_recommendation(pinned, payload)
    result, forecast = compose_recommendation(payload, prepared, pinned)
    assert result.summary_action == "HOLD" and prepared.plan.orders == ()
    assert all(
        row.side == "HOLD"
        and row.estimated_quantity == "0.000000"
        and row.estimated_notional_usd == "0.00"
        for row in result.actions
    )
    assert result.estimated_total_trade_cost_usd == "0.00"
    assert forecast.current_allocation == forecast.proposed_allocation
    assert payload.state == state


def test_mandatory_position_correction_overrides_the_band(
    pinned: PinnedSnapshot, payload: RecommendationPayload
) -> None:
    state = PortfolioState(
        cash_usd="790.00",
        positions=(
            Position(
                asset_id="SYN:AAA",
                sector="Technology",
                quantity="3.000000",
                total_basis_usd="200.00",
            ),
        ),
    )
    payload = payload.model_copy(update={"state": state})
    prepared = prepare_recommendation(pinned, payload)
    result, _ = compose_recommendation(payload, prepared, pinned)
    row = next(x for x in result.actions if x.asset_id == "SYN:AAA")
    # 210/1000 -> .20: floor((10/70)*1e6)/1e6; raw notional rounds10.00, credit9.99.
    assert row.side == "SELL" and row.label == "REDUCE"
    assert row.estimated_quantity == "0.142857" and row.estimated_notional_usd == "10.00"
    assert row.reason_codes == ("MANDATORY_RISK_CORRECTION",)
    assert result.summary_action == "REBALANCE"
    assert prepared.plan.preview[0].effect is not None
    assert prepared.plan.preview[0].effect.cash_delta_usd == "9.99"
    assert payload.state == state


def test_missing_held_mark_is_a_failure_not_a_fabricated_zero(
    pinned: PinnedSnapshot, payload: RecommendationPayload
) -> None:
    payload = payload.model_copy(
        update={
            "state": PortfolioState(
                cash_usd="10.00",
                positions=(
                    Position(
                        asset_id="SYN:MISSING",
                        sector="Unknown",
                        quantity="1.000000",
                        total_basis_usd="10.00",
                    ),
                ),
            )
        }
    )
    with pytest.raises(ValueError, match="VALUATION_UNAVAILABLE"):
        prepare_recommendation(pinned, payload)


def test_input_identity_and_cancel_fences(
    pinned: PinnedSnapshot, payload: RecommendationPayload
) -> None:
    with pytest.raises(InterruptedError):
        prepare_recommendation(pinned, payload, cancelled=lambda: True)
    prepared = prepare_recommendation(pinned, payload)
    changed = payload.model_copy(update={"engine_version": "b" * 64})
    with pytest.raises(ValueError, match="INPUT_FINGERPRINT_MISMATCH"):
        compose_recommendation(changed, prepared, pinned)


def test_public_request_is_explicit_and_keeps_maximum_uint64(
    payload: RecommendationPayload,
) -> None:
    request = RecommendationRequest.model_validate_json(
        '{"as_of_session":"2028-07-17","clock_mode":"synthetic_replay","seed":18446744073709551615}'
    )
    assert (
        request.seed == 18446744073709551615
        and b"18446744073709551615" in request.canonical_bytes()
    )
    updates: list[dict[str, object]] = [
        {"seed": True},
        {"seed": -1},
        {"seed": 18446744073709551616},
        {"initial_value_usd": "1.00"},
        {"approved_at": "2028-07-18T12:30:00Z"},
    ]
    for update in updates:
        with pytest.raises(ValidationError):
            RecommendationRequest.model_validate(request.model_dump() | update)
    with pytest.raises(ValidationError):
        RecommendationRequest.model_validate({"as_of_session": "2028-07-17"})
    with pytest.raises(ValidationError):
        RecommendationPayload.model_validate(
            payload.model_dump()
            | {"inputs": request.model_dump() | {"clock_mode": "current_paper"}}
        )


def test_posted_state_cannot_be_used_before_its_observation(payload: RecommendationPayload) -> None:
    with pytest.raises(ValidationError, match="not known"):
        RecommendationPayload.model_validate(
            payload.model_dump()
            | {"state_observed_at": payload.decision_cutoff_utc + timedelta(seconds=1)}
        )


def test_held_asset_sector_lookup_does_not_expand_eligibility(
    pinned: PinnedSnapshot, payload: RecommendationPayload
) -> None:
    with MarketRepository(pinned) as repository:
        repository._universe = repository._universe.model_copy(
            update={
                "memberships": tuple(
                    row for row in repository._universe.memberships if row.asset_id != "SYN:AAA"
                )
            }
        )
        view = repository.accounting_as_of(
            payload.decision_cutoff_utc, payload.inputs.as_of_session
        )
        assert "SYN:AAA" not in {row.asset_id for row in view.assets}
        assert "SYN:AAA" in {row.asset_id for row in view.bars}
        assert repository.accounting_sectors(
            ("SYN:AAA",), payload.decision_cutoff_utc, payload.inputs.as_of_session
        ) == {"SYN:AAA": "Technology"}
        sectors = tuple(row for row in repository._context.sectors if row.asset_id == "SYN:AAA")
        assert sectors
        repository._context = repository._context.model_copy(
            update={
                "sectors": tuple(
                    row.model_copy(
                        update={"available_at": payload.decision_cutoff_utc + timedelta(seconds=1)}
                    )
                    if row.asset_id == "SYN:AAA"
                    else row
                    for row in repository._context.sectors
                )
            }
        )
        assert repository.accounting_sectors(
            ("SYN:AAA",), payload.decision_cutoff_utc, payload.inputs.as_of_session
        ) == {"SYN:AAA": "Unknown"}


@pytest.mark.parametrize("kind", ["split", "dividend"])
def test_unposted_actions_block_readonly_planning_but_future_payable_does_not(
    pinned: PinnedSnapshot,
    payload: RecommendationPayload,
    monkeypatch: pytest.MonkeyPatch,
    kind: Literal["split", "dividend"],
) -> None:
    payload = payload.model_copy(
        update={
            "state": PortfolioState(
                cash_usd="790.00",
                positions=(
                    Position(
                        asset_id="SYN:AAA",
                        sector="Technology",
                        quantity="3.000000",
                        total_basis_usd="200.00",
                    ),
                ),
            )
        }
    )
    calendar = Calendar.model_validate_json(
        pinned.artifacts[pinned.manifest.calendar.artifact_path]
    )
    days = [row.session_date for row in calendar.sessions]
    payable = days[days.index(payload.inputs.as_of_session) + 1]
    action = CorporateAction(
        asset_id="SYN:AAA",
        available_at=payload.decision_cutoff_utc,
        ingested_at=payload.decision_cutoff_utc,
        event_id="AUTHORED_ACTION_GUARD",
        kind=kind,
        effective_session=payload.inputs.as_of_session,
        provider="SYNTHETIC_DATA_ONLY",
        currency="USD",
        ratio_numerator="2" if kind == "split" else None,
        ratio_denominator="1" if kind == "split" else None,
        per_share="1.00" if kind == "dividend" else None,
        payable_session=payable if kind == "dividend" else None,
    )
    original = MarketRepository.accounting_as_of

    def with_action(repository: MarketRepository, cutoff: datetime, day: date) -> MarketView:
        return replace(original(repository, cutoff, day), actions=(action,))

    monkeypatch.setattr(MarketRepository, "accounting_as_of", with_action)
    before = payload.state.model_dump_json()
    with pytest.raises(ValueError, match="RECONCILIATION_REQUIRED"):
        prepare_recommendation(pinned, payload)
    assert payload.state.model_dump_json() == before
    if kind == "dividend":
        entitlement = DividendEntitlement(
            key=action_key(action),
            asset_id="SYN:AAA",
            ex_session=payload.inputs.as_of_session,
            quantity="3.000000",
            per_share="1.00",
            evidence_sha256=action_hash(action),
        )
        payload = payload.model_copy(
            update={"state": payload.state.model_copy(update={"entitlements": (entitlement,)})}
        )
        prepared = prepare_recommendation(pinned, payload)
        assert prepared.plan.portfolio_value_usd == "1000.00" and payload.state.cash_usd == "790.00"
