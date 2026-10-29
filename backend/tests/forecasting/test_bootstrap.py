"""Authored FIX-08 oracles, independent of production scenario functions."""

import json
from pathlib import Path

import numpy as np
import pytest

from backend.forecasting.bootstrap import (
    ForecastCancelled,
    array_digest,
    draw_starts,
    expand_blocks,
    linear_quantile,
    money_from_float,
    outcome,
    simulate,
)

FIXTURE = json.loads(
    (Path(__file__).resolve().parents[3] / "data/fixtures/fix-08/case.json").read_text()
)


def test_pinned_sampling_matches_committed_independent_index_stream() -> None:
    sampled = draw_starts(63, 42)
    assert sampled.starts.shape == (5000, 13)
    assert sampled.starts[0].tolist() == FIXTURE["expected"]["first_path_starts"]
    assert array_digest(sampled.starts, integer=True) == FIXTURE["expected"]["indices_sha256"]
    state = json.loads(
        (Path(__file__).resolve().parents[3] / "data/fixtures/fix-08/sampling.json").read_text()
    )["initial_state"]
    assert sampled.initial_state == state
    assert not sampled.starts.flags.writeable


def test_whole_vectors_and_nonwrapping_tail_match_small_arithmetic_oracle() -> None:
    probe = FIXTURE["inputs"]["small_operator_probe"]
    selected = expand_blocks(
        np.array(probe["vectors"], dtype=np.float64),
        np.array([probe["starts"]], dtype=np.int64),
        2,
        3,
    )
    assert selected[0].tolist() == FIXTURE["expected"]["small_sampled_vectors"]
    assert np.array_equal(selected.sum(axis=2), np.zeros((1, 3)))
    with pytest.raises(ValueError, match="noncircular"):
        expand_blocks(np.zeros((3, 2)), np.array([[2, 0]], dtype=np.int64), 2, 3)


def test_actual_5000_constant_vector_paths_match_independent_compounding() -> None:
    history = np.tile(np.array([[0.01, -0.01]], dtype=np.float64), (252, 1))
    assert array_digest(history, integer=False) == FIXTURE["expected"]["array_sha256"]
    sampled = draw_starts(63, 42)
    paths = simulate(history, sampled.starts, np.array([[0.5, 0.5], [0.75, 0.25]]), 63)
    assert np.array_equal(paths[0], np.ones((5000, 64)))
    proposed = outcome(paths[1, :, -1], 1000)
    assert proposed.median_return_fraction == pytest.approx((1.005**63) - 1, abs=1e-12)
    assert proposed.median_ending_value_usd == "1369.18"
    assert proposed.probability_of_loss == 0
    assert not paths.flags.writeable


def test_equal_allocations_share_exact_shocks_and_cost_is_charged_only_once() -> None:
    series = np.arange(252, dtype=np.float64) / 100000
    history = np.column_stack((series, -series / 2))
    sampled = draw_starts(17, 18446744073709551615)
    weights = np.array([[0.4, 0.4], [0.4, 0.4]])
    paths = simulate(history, sampled.starts, weights, 17)
    assert np.array_equal(paths[0], paths[1])
    neutral = np.tile([[0.01, -0.01]], (252, 1))
    paths = simulate(neutral, sampled.starts, np.full((2, 2), 0.5), 17)
    assert np.array_equal(paths[0], np.ones((5000, 18)))
    assert np.array_equal(paths[1], np.ones((5000, 18)))
    assert outcome(paths[1, :, -1], 1000, 10).median_ending_value_usd == "990.00"


def test_cash_needs_no_history_or_rng_and_preserves_original_nav_denominator() -> None:
    paths = simulate(None, None, np.empty((2, 0)), 3)
    hold, proposed = outcome(paths[0, :, -1], 1000), outcome(paths[1, :, -1], 1000, 10)
    assert hold.median_ending_value_usd == "1000.00" and hold.probability_of_loss == 0
    assert proposed.median_ending_value_usd == "990.00"
    assert proposed.median_return_fraction == pytest.approx(-0.01, abs=1e-12)
    assert proposed.probability_of_loss == 1


def test_sorted_quantiles_and_exact_half_even_display_oracles() -> None:
    returns = np.array([-0.2, -0.1, 0, 0.1, 0.2])
    assert linear_quantile(returns, 0.1) == pytest.approx(-0.16, abs=1e-12)
    assert linear_quantile(returns, 0.5) == 0
    assert linear_quantile(returns, 0.9) == pytest.approx(0.16, abs=1e-12)
    measured = outcome(np.array([0.8, 0.9, 1, 1.1, 1.2], dtype=np.float64), 1000)
    assert measured.probability_of_loss == 0.4
    assert money_from_float(1.125) == "1.12"
    assert money_from_float(1.375) == "1.38"


def test_cancellation_and_invalid_sampling_do_not_produce_partial_paths() -> None:
    with pytest.raises(ForecastCancelled):
        simulate(None, None, np.empty((2, 0)), 90, cancelled=lambda: True)
    for seed in (-1, 18446744073709551616, True):
        with pytest.raises(ValueError, match="seed"):
            draw_starts(63, seed)
    with pytest.raises(ValueError, match="horizon"):
        draw_starts(0, 42)
    with pytest.raises(ValueError, match="quantile"):
        linear_quantile(np.array([np.nan]), 0.5)


def test_unrepresentable_money_is_unavailable_instead_of_an_invalid_wire_scalar() -> None:
    with pytest.raises(ValueError, match="NONFINITE_RESULT"):
        money_from_float(1e22)


def test_nearly_complete_cost_preserves_small_remaining_capital_under_large_growth() -> None:
    measured = outcome(
        np.full(5, 7000000000000000.0), "1000000000000000000000.00", "999999999999999999999.99"
    )
    assert measured.median_ending_value_usd == "70000000000000.00"
    assert measured.median_return_fraction == pytest.approx(-0.99999993, abs=1e-12)
    assert measured.probability_of_loss == 1
