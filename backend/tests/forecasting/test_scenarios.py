from datetime import date
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.domain.forecast import ForecastAllocation, ForecastWeight
from backend.forecasting.contracts import ForecastInputs, ForecastPayload
from backend.forecasting.scenarios import ScenarioBundle, compare_scenarios
from backend.market_data.files import PinnedSnapshot
from backend.market_data.repository import MarketRepository
from backend.strategies.clock import decision_cutoff


def compute(pinned: PinnedSnapshot, inputs: ForecastInputs, identity: int = 3) -> ScenarioBundle:
    with MarketRepository(pinned) as repository:
        return compare_scenarios(
            repository, inputs, forecast_id=UUID(int=identity), engine_version="e" * 64
        )


def cash(cost: str | None = "0.00") -> ForecastAllocation:
    return ForecastAllocation(weights=(), cash_weight="1", upfront_cost_usd=cost)


def test_full_pinned_forecasts_are_reproducible_and_identity_is_not_fingerprint(
    pinned: PinnedSnapshot,
    inputs: ForecastInputs,
) -> None:
    first, second = compute(pinned, inputs), compute(pinned, inputs, 4)
    assert first.forecast.status == "available"
    assert first.forecast.fingerprint == second.forecast.fingerprint
    assert first.forecast.id != second.forecast.id
    assert first.artifacts == second.artifacts
    assert first.forecast.hold_unchanged == first.forecast.proposed
    assert first.forecast.median_return_delta_fraction == 0
    assert first.reproducibility["input_shape"] == [252, 2]
    assert first.reproducibility["input_row_dates"][-1] == "2028-07-17"
    assert first.forecast.horizon_trading_sessions != 90
    assert (
        first.forecast.rng.initial_state is not None and first.forecast.sampled_indices is not None
    )
    reordered = inputs.model_copy(
        update={
            "proposed_allocation": ForecastAllocation(
                weights=tuple(reversed(inputs.proposed_allocation.weights)),
                cash_weight="0.00",
                upfront_cost_usd="0.00",
            ),
        }
    )
    assert compute(pinned, reordered).forecast.fingerprint == first.forecast.fingerprint
    changed = compute(pinned, inputs.model_copy(update={"seed": 43}))
    assert changed.forecast.sampled_indices != first.forecast.sampled_indices
    assert changed.forecast.fingerprint != first.forecast.fingerprint


def test_cash_comparison_is_numeric_without_history_or_rng(
    pinned: PinnedSnapshot,
    inputs: ForecastInputs,
) -> None:
    bundle = compute(
        pinned,
        inputs.model_copy(
            update={"current_allocation": cash(), "proposed_allocation": cash("10.00")}
        ),
    )
    result = bundle.forecast
    assert result.status == "available"
    assert result.hold_unchanged is not None and result.proposed is not None
    assert result.hold_unchanged.median_ending_value_usd == "1000.00"
    assert result.proposed.median_ending_value_usd == "990.00"
    assert result.proposed.probability_of_loss == 1
    assert result.input_array_sha256 is None and result.sampled_indices is None
    assert result.rng.initial_state is None
    assert set(bundle.artifacts) == {"paths.f64"}


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ({"initial_value_usd": None}, "VALUATION_UNAVAILABLE"),
        ({"valuation_as_of_session": date(2028, 7, 14)}, "VALUATION_UNAVAILABLE"),
        ({"proposed_allocation": cash(None)}, "COST_UNAVAILABLE"),
    ],
)
def test_unknown_inputs_never_produce_zero_or_partial_outcomes(
    pinned: PinnedSnapshot,
    inputs: ForecastInputs,
    mutation: dict[str, Any],
    reason: str,
) -> None:
    result = compute(pinned, inputs.model_copy(update=mutation)).forecast
    assert result.status == "unavailable" and result.unavailable_reason == reason
    assert result.proposed is None and result.hold_unchanged is None
    assert result.median_return_delta_fraction is None


def test_insufficient_history_does_not_stitch_older_rows_and_calendar_does_not_guess(
    pinned: PinnedSnapshot,
    inputs: ForecastInputs,
) -> None:
    for day, reason in [
        (date(2027, 6, 1), "INSUFFICIENT_ALIGNED_HISTORY"),
        (date(2030, 11, 15), "CALENDAR_UNAVAILABLE"),
    ]:
        with MarketRepository(pinned) as repository:
            changed = inputs.model_copy(
                update={
                    "as_of_session": day,
                    "valuation_as_of_session": day,
                    "decision_cutoff_utc": decision_cutoff(repository.calendar, day),
                }
            )
        result = compute(pinned, changed).forecast
        assert result.status == "unavailable" and result.unavailable_reason == reason
        assert result.proposed is None and result.hold_unchanged is None


def test_missing_asset_and_valid_oversized_union_remain_explicit_unavailable(
    pinned: PinnedSnapshot,
    inputs: ForecastInputs,
) -> None:
    for allocation, reason in [
        (
            ForecastAllocation(
                weights=(ForecastWeight(asset_id="SYN:MISSING", weight="1"),),
                cash_weight="0",
                upfront_cost_usd="0.00",
            ),
            "ASSET_UNAVAILABLE",
        ),
        (
            ForecastAllocation(
                weights=tuple(
                    ForecastWeight(asset_id=f"SYN:EXTRA{i}", weight="0.05") for i in range(20)
                ),
                cash_weight="0",
                upfront_cost_usd="0.00",
            ),
            "WORKLOAD_LIMIT",
        ),
    ]:
        result = compute(
            pinned, inputs.model_copy(update={"proposed_allocation": allocation})
        ).forecast
        assert result.status == "unavailable" and result.unavailable_reason == reason
        assert result.proposed is None and result.hold_unchanged is None


def test_malformed_money_and_noncanonical_payload_are_validation_errors(
    inputs: ForecastInputs,
) -> None:
    for mutation in (
        {"initial_value_usd": "0.00"},
        {"seed": True},
        {"simulation_count": 1},
        {"proposed_allocation": cash("1000.00")},
    ):
        with pytest.raises(ValidationError):
            ForecastInputs.model_validate({**inputs.model_dump(), **mutation})
    with pytest.raises(ValidationError):
        ForecastPayload(
            forecast_id=UUID(int=3),
            engine_version="e" * 64,
            inputs_canonical_json=inputs.model_dump_json(indent=2),
        )


def test_cent_cost_is_subtracted_before_float_conversion(
    pinned: PinnedSnapshot,
    inputs: ForecastInputs,
) -> None:
    changed = inputs.model_copy(
        update={
            "initial_value_usd": "1000000000000000000000.00",
            "current_allocation": cash(),
            "proposed_allocation": cash("999999999999999999999.99"),
        }
    )
    result = compute(pinned, changed).forecast
    assert result.status == "available" and result.proposed is not None
    assert result.proposed.median_ending_value_usd == "0.01"
    assert result.proposed.probability_of_loss == 1


def test_unsafe_adjusted_basis_and_snapshot_identity_cannot_be_silently_used(
    pinned: PinnedSnapshot,
    inputs: ForecastInputs,
) -> None:
    basis = pinned.manifest.price_basis.model_copy(update={"adjusted_close": "unverified"})
    altered = PinnedSnapshot(
        pinned.manifest.model_copy(update={"price_basis": basis}), pinned.artifacts
    )
    bound = inputs.model_copy(
        update={
            "snapshot_id": altered.manifest.snapshot_id(),
            "snapshot_sha256": altered.manifest.manifest_hash(),
        }
    )
    result = compute(altered, bound).forecast
    assert result.status == "unavailable" and result.unavailable_reason == "UNSAFE_PRICE_BASIS"
    with pytest.raises(ValueError, match="FINGERPRINT"):
        compute(altered, inputs)


def test_known_small_cash_cost_is_not_erased_at_large_valid_nav(
    pinned: PinnedSnapshot,
    inputs: ForecastInputs,
    cash_precision: dict[str, Any],
) -> None:
    changed = inputs.model_copy(
        update={
            "initial_value_usd": cash_precision["inputs"]["initial_nav_usd"],
            "current_allocation": cash(),
            "proposed_allocation": cash(cash_precision["inputs"]["proposed_upfront_cost_usd"]),
        }
    )
    result = compute(pinned, changed).forecast
    assert result.status == "available" and result.proposed is not None
    assert (
        result.proposed.probability_of_loss
        == cash_precision["expected"]["proposed_loss_probability"]
    )
    assert (
        result.proposed.median_ending_value_usd == cash_precision["expected"]["proposed_ending_usd"]
    )
    assert result.proposed.median_return_fraction == cash_precision["expected"]["proposed_return"]
