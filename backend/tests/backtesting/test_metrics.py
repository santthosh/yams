"""FIX-07 and pre-authored independent scalar/period expectations."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.backtesting.metrics import TradeCost, calculate_metrics, metrics_periods
from backend.tests.backtesting.test_core import pinned, run

ROOT = Path(__file__).resolve().parents[3] / "data/fixtures"
FIX = json.loads((ROOT / "fix-07/case.json").read_text())
EXT = json.loads((ROOT / "metrics_extensions/case.json").read_text())


def test_independent_fix07_known_curve() -> None:
    actual = calculate_metrics(
        FIX["inputs"]["nav_usd"],
        trades=tuple(
            TradeCost(gross_usd=value, fees_usd="0.00", slippage_usd="0.00")
            for value in FIX["inputs"]["gross_trade_notionals_usd"]
        ),
    )
    pairs = {
        "cumulative_return_fraction": "cumulative_return",
        "annualized_return_fraction": "annualized_return",
        "annualized_volatility_fraction": "annualized_volatility",
        "max_drawdown_fraction": "max_drawdown",
        "sharpe_ratio": "sharpe",
        "turnover_fraction": "turnover",
    }
    for field, expected in pairs.items():
        metric = getattr(actual, field)
        assert metric.unavailable_reason is None
        assert metric.value == pytest.approx(FIX["expected"][expected], abs=1e-12, rel=0)
    assert actual.trade_count == 2 and actual.fees_usd == actual.slippage_usd == "0.00"


def test_exact_cost_attribution_is_not_subtracted_from_net_nav_again() -> None:
    actual = calculate_metrics(
        ["100.00", "90.00", "99.00"],
        trades=(
            TradeCost(gross_usd="40.00", fees_usd="1.25", slippage_usd="0.50"),
            TradeCost(gross_usd="60.00", fees_usd="2.75", slippage_usd="0.75"),
        ),
    )
    assert actual.cumulative_return_fraction.value == -0.01
    assert actual.fees_usd == "4.00" and actual.slippage_usd == "1.25"
    assert actual.trade_count == 2
    assert actual.turnover_fraction.value == pytest.approx(300 / 289, abs=1e-12)


@pytest.mark.parametrize(
    "nav,reason", [([], "NO_OBSERVATIONS"), (["100.00"], "INSUFFICIENT_RETURN_HISTORY")]
)
def test_empty_and_one_point_do_not_invent_performance(nav: list[str], reason: str) -> None:
    result = calculate_metrics(nav)
    for field in [
        "cumulative_return_fraction",
        "annualized_return_fraction",
        "annualized_volatility_fraction",
        "max_drawdown_fraction",
        "sharpe_ratio",
    ]:
        metric = getattr(result, field)
        assert metric.value is None and metric.unavailable_reason == reason
    assert result.trade_count == 0 and result.fees_usd == result.slippage_usd == "0.00"
    assert result.turnover_fraction.value == (0 if nav else None)


def test_flat_observations_and_one_return_have_defined_distinct_limits() -> None:
    flat = calculate_metrics(["100.00"] * 4)
    assert flat.cumulative_return_fraction.value == flat.annualized_return_fraction.value == 0
    assert flat.annualized_volatility_fraction.value == flat.max_drawdown_fraction.value == 0
    assert (
        flat.sharpe_ratio.value is None and flat.sharpe_ratio.unavailable_reason == "ZERO_VARIANCE"
    )
    single = calculate_metrics(["100.00", "100.00"])
    assert single.cumulative_return_fraction.value == single.max_drawdown_fraction.value == 0
    assert single.annualized_volatility_fraction.unavailable_reason == "INSUFFICIENT_RETURN_HISTORY"
    assert single.sharpe_ratio.unavailable_reason == "INSUFFICIENT_RETURN_HISTORY"


def test_zero_denominators_and_large_annualization_are_explicitly_unavailable() -> None:
    zero = calculate_metrics(["100.00", "0.00", "0.00"])
    assert zero.cumulative_return_fraction.value == zero.annualized_return_fraction.value == -1
    assert zero.max_drawdown_fraction.value == 1
    assert zero.annualized_volatility_fraction.unavailable_reason == "ZERO_RETURN_DENOMINATOR"
    assert zero.sharpe_ratio.unavailable_reason == "ZERO_RETURN_DENOMINATOR"
    assert (
        calculate_metrics(["0.00", "10.00"]).cumulative_return_fraction.unavailable_reason
        == "ZERO_START_NAV"
    )
    assert (
        calculate_metrics(["0.00", "0.00"]).turnover_fraction.unavailable_reason == "ZERO_MEAN_NAV"
    )
    large = calculate_metrics(["0.01", "9999999999999999999999.00"])
    assert large.annualized_return_fraction.value is None
    assert large.annualized_return_fraction.unavailable_reason == "NUMERICAL_RANGE"


def test_period_holdout_uses_previous_close_but_owned_nav_denominator(tmp_path: Path) -> None:
    core = run(pinned(tmp_path))
    periods = metrics_periods(core)
    expected = EXT["core_report"]["expected"]
    for field, name in [
        ("cumulative_return_fraction", "cumulative_return"),
        ("annualized_return_fraction", "annualized_return"),
        ("annualized_volatility_fraction", "annualized_volatility"),
        ("max_drawdown_fraction", "max_drawdown"),
        ("sharpe_ratio", "sharpe"),
        ("turnover_fraction", "turnover"),
    ]:
        assert getattr(periods.total.metrics, field).value == pytest.approx(
            expected[name], abs=1e-12, rel=0
        )
    assert periods.total.metrics.slippage_usd == "0.61" and periods.total.metrics.trade_count == 3
    assert periods.development.return_observations == 2 and periods.holdout.return_observations == 1
    assert periods.holdout.daily_nav_observations == 1
    assert periods.holdout.metrics.cumulative_return_fraction.value == pytest.approx(
        1000.22 / 993.66 - 1, abs=1e-12
    )
    assert (
        periods.holdout.metrics.trade_count == 0
        and periods.holdout.metrics.turnover_fraction.value == 0
    )
    half = calculate_metrics(
        EXT["half_holdout"]["holdout_owned_nav_usd"],
        previous_nav_usd="120.00",
        trades=(TradeCost(gross_usd="60.00", fees_usd="0.00", slippage_usd="0.00"),),
    )
    assert (
        half.cumulative_return_fraction.value == -0.1 and half.max_drawdown_fraction.value == 0.25
    )
    assert half.turnover_fraction.value == pytest.approx(60 / 99, abs=1e-12)


def test_owned_interval_must_match_core_sessions_and_money_is_string_only(tmp_path: Path) -> None:
    core = run(pinned(tmp_path))
    with pytest.raises(ValueError, match="exact core session"):
        metrics_periods(core, ["100.00"])
    for invalid in [[100.0], ["-1.00"], ["NaN"], ["1.001"]]:
        with pytest.raises(ValidationError):
            calculate_metrics(invalid)  # type: ignore[arg-type]


def test_full_workload_statistics_are_deterministic_and_finite() -> None:
    prices = [str(10000 + (i * 7919) % 5000) + ".00" for i in range(2520)]
    first = calculate_metrics(prices)
    assert calculate_metrics(prices) == first
    assert (
        first.sharpe_ratio.value is not None
        and first.annualized_volatility_fraction.value is not None
    )
    assert "NaN" not in first.model_dump_json() and "Infinity" not in first.model_dump_json()


def test_constant_nonzero_returns_have_zero_dispersion() -> None:
    result = calculate_metrics(["9.00", "12.00", "16.00"])
    assert result.annualized_volatility_fraction.value == 0
    assert result.sharpe_ratio.unavailable_reason == "ZERO_VARIANCE"
    assert result.cumulative_return_fraction.value == pytest.approx(7 / 9, abs=1e-12)
