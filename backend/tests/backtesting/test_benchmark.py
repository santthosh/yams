"""Aligned synthetic SPY and cash references; no benchmark gap/subset substitution."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.backtesting.benchmark import (
    BenchmarkCurve,
    benchmark_curve,
    comparison_terms,
    exposure_series,
)
from backend.backtesting.metrics import metrics_periods
from backend.market_data.repository import MarketRepository
from backend.portfolio.execution import DEFAULT_EXECUTION_POLICY
from backend.strategies.registry import template_config
from backend.tests.backtesting.test_core import action, altered, pinned, run

ROOT = Path(__file__).resolve().parents[3] / "data/fixtures"


def test_actual_benchmark_uses_adjusted_closes_and_exact_original_dates(tmp_path: Path) -> None:
    snapshot = pinned(tmp_path)
    core = run(snapshot)
    with MarketRepository(snapshot) as repository:
        benchmark = benchmark_curve(repository, core)
        assert benchmark.available and benchmark.periods is not None
        assert benchmark.sessions == tuple(point.session_date for point in core.points)
        # Committed independent fixture formula: SPY=100+index/40 for indices401..404.
        assert benchmark.nav_usd == ("1000.00", "1000.23", "1000.45", "1000.68")
        assert benchmark.periods.total.metrics.cumulative_return_fraction.value == 0.00068
        assert {
            "BENCHMARK_FRICTION_FREE_FULLY_INVESTED",
            "BENCHMARK_DIVIDEND_RECOGNITION_DIFFERS",
            "BENCHMARK_INITIAL_CLOSE_DIFFERS_FROM_NEXT_OPEN",
        } <= set(benchmark.warnings)
        cash = metrics_periods(core, ["1000.00"] * 4, include_trades=False)
        assert cash.total.metrics.cumulative_return_fraction.value == 0
        assert cash.total.metrics.annualized_volatility_fraction.value == 0
        assert cash.total.metrics.sharpe_ratio.unavailable_reason == "ZERO_VARIANCE"
        assert (
            cash.total.metrics.trade_count == 0 and cash.total.metrics.turnover_fraction.value == 0
        )


@pytest.mark.parametrize("mutation", ["missing", "late", "flagged"])
def test_missing_late_or_invalid_benchmark_never_drops_sessions(
    tmp_path: Path, mutation: str
) -> None:
    snapshot = pinned(tmp_path)
    rows = json.loads((ROOT / "snapshot/bars.json").read_bytes())
    for row in rows:
        if row["asset_id"] == "SYN:SPY" and row["session_date"] == "2028-07-20":
            if mutation == "missing":
                rows.remove(row)
            elif mutation == "late":
                row["available_at"] = row["ingested_at"] = "2028-07-21T14:30:00Z"
            else:
                row["quality_flags"].append("UNVERIFIED_BAR")
            break
    changed = altered(snapshot, bars=rows)
    core = run(changed)
    with MarketRepository(changed) as repository:
        benchmark = benchmark_curve(repository, core)
    assert not benchmark.available and benchmark.unavailable_reason == "INSUFFICIENT_MARKET_DATA"
    assert benchmark.periods is None and len(benchmark.nav_usd) == 4
    assert benchmark.nav_usd[2] is None and benchmark.nav_usd[-1] == "1000.68"
    assert len(benchmark.sessions) == len(core.points)  # no common-row alignment


def test_raw_split_does_not_double_adjust_benchmark_or_credit_dividends(tmp_path: Path) -> None:
    snapshot = pinned(tmp_path)
    rows = json.loads((ROOT / "snapshot/bars.json").read_bytes())
    for row in rows:
        if row["asset_id"] == "SYN:SPY" and row["session_date"] >= "2028-07-20":
            for field in ["open", "high", "low", "close"]:
                row[field] = str(Decimal(row[field]) / 2)
    split = action("split", "2028-07-20") | {"asset_id": "SYN:SPY"}
    changed = altered(snapshot, bars=rows, **{"actions.json": [split]})
    core = run(changed)
    with MarketRepository(changed) as repository:
        assert benchmark_curve(repository, core).nav_usd == (
            "1000.00",
            "1000.23",
            "1000.45",
            "1000.68",
        )


def test_stock_identity_is_not_a_passive_spy_strategy(tmp_path: Path) -> None:
    snapshot = pinned(tmp_path)
    core = run(snapshot, benchmark_asset_id="SYN:AAA")
    with MarketRepository(snapshot) as repository:
        result = benchmark_curve(repository, core)
    assert not result.available and result.unavailable_reason == "UNSUPPORTED_BENCHMARK"
    assert result.nav_usd == (None,) * 4 and result.periods is None


def test_exposure_uses_shared_raw_close_valuation_and_preserves_source(tmp_path: Path) -> None:
    snapshot = pinned(tmp_path)
    core = run(snapshot)
    with MarketRepository(snapshot) as repository:
        series = exposure_series(repository, core)
    assert series[0].cash_weight.value == 1 and series[0].max_position_weight.value == 0
    # Independent exact mark formula for index404; exposure uses shared unrounded NAV.
    from fractions import Fraction

    value_a = Fraction("2.855103") * Fraction("70.20")
    value_c = Fraction("3.075030") * Fraction("67.16")
    nav = Fraction("392.84") + 2 * value_a + value_c
    assert series[-1].cash_weight.value == pytest.approx(float(Fraction("392.84") / nav), abs=1e-12)
    assert series[-1].max_position_weight.value == pytest.approx(float(value_c / nav), abs=1e-12)
    assert core.points[0].state.positions == () and core.points[1].state.cash_usd == "392.84"
    other = core.model_copy(update={"snapshot_sha256": "a" * 64})
    with (
        MarketRepository(snapshot) as repository,
        pytest.raises(ValueError, match="source differs"),
    ):
        exposure_series(repository, other)


def test_comparison_terms_expose_incompatible_controls_but_allow_strategy_parameters(
    tmp_path: Path,
) -> None:
    snapshot = pinned(tmp_path)
    core = run(snapshot)
    config = template_config("mean_reversion")
    terms = comparison_terms(core, config)
    assert (
        terms.differences(terms) == ()
        and terms.fingerprint() == comparison_terms(core, config).fingerprint()
    )
    other_config = template_config("low_volatility")
    different_strategy = core.model_copy(update={"config_sha256": other_config.config_hash()})
    assert terms.differences(comparison_terms(different_strategy, other_config)) == ()
    for field, value in [
        ("reporting_engine_version", "a" * 64),
        ("initial_capital_usd", "2000.00"),
        ("start_session", date(2028, 7, 17)),
        ("benchmark_asset_id", "OTHER:ETF"),
        ("universe_canonical_json", "{}"),
        (
            "execution_policy",
            DEFAULT_EXECUTION_POLICY.model_copy(update={"commission_usd": "1.00"}),
        ),
    ]:
        changed = terms.model_copy(update={field: value})
        assert terms.differences(changed) == ("INCOMPARABLE_" + field.upper(),)
        assert changed.fingerprint() != terms.fingerprint()
    with pytest.raises(ValueError, match="config differs"):
        comparison_terms(core, other_config)


def test_unavailable_benchmark_requires_a_reason_and_cannot_publish_statistics(
    tmp_path: Path,
) -> None:
    snapshot = pinned(tmp_path)
    core = run(snapshot)
    with MarketRepository(snapshot) as repository:
        valid = benchmark_curve(repository, core).model_dump(mode="json")
    variants: list[dict[str, object]] = [
        {"available": False},
        {"available": False, "unavailable_reason": "MISSING"},
        {"available": True, "unavailable_reason": "MISSING"},
    ]
    for changes in variants:
        with pytest.raises(ValidationError):
            BenchmarkCurve.model_validate(valid | changes)
