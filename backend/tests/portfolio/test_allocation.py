"""Independent synthetic allocation tables and invariant tests (FIX-01/03)."""

import json
import math
import random
import shutil
from datetime import UTC, datetime
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.domain.strategy import PortfolioConfig, StrategyConfigV1
from backend.market_data.files import PinnedSnapshot
from backend.portfolio.allocation import (
    AllocatedMomentum,
    AllocationCandidate,
    AllocationResult,
    allocate,
    allocate_momentum,
)
from backend.portfolio.risk import AllocationTarget, assess_targets
from backend.strategies.momentum import evaluate_snapshot

ROOT = Path(__file__).resolve().parents[3] / "data/fixtures"


def policy(**updates: object) -> PortfolioConfig:
    values = json.loads((ROOT / "fix-01/strategy.canonical.json").read_text())["portfolio"]
    return PortfolioConfig.model_validate(values | updates)


def candidate(
    identity: str, sector: str = "Unknown", volatility: float = 0.1, score: float = 0
) -> AllocationCandidate:
    return AllocationCandidate(asset_id=identity, sector=sector, score=score, volatility=volatility)


def weights(result: AllocationResult) -> dict[str, Fraction]:
    return {row.asset_id: Fraction(row.weight) for row in result.targets}


@pytest.mark.parametrize(
    ("count", "same_sector", "case"),
    [
        (8, False, "eight_distinct_sectors"),
        (8, True, "eight_same_sector"),
        (2, False, "two_distinct_sectors"),
    ],
)
def test_fix01_committed_equal_rate_tables(count: int, same_sector: bool, case: str) -> None:
    expected = json.loads((ROOT / "fix-01/case.json").read_text())["expected"][case]
    result = allocate(
        [candidate(str(index), "Unknown" if same_sector else str(index)) for index in range(count)],
        policy(),
    )
    assert set(weights(result).values()) == {Fraction(expected["per_asset_weight"])}
    assert Fraction(result.cash_weight) == Fraction(expected["cash_weight"])
    assert result.risk.compliant


def test_sparse_empty_and_five_unknown_sector() -> None:
    one = allocate([candidate("A")], policy())
    assert weights(one) == {"A": Fraction("0.2")}
    assert one.cash_weight == "0.8"
    assert one.risk.capped_positions == ("A",)
    assert one.risk.unmet_investable_weight == "0.75"
    empty = allocate([], policy())
    assert empty.targets == () and empty.cash_weight == "1"
    assert "EMPTY_ELIGIBLE_UNIVERSE" in empty.reasons
    five = allocate([candidate(str(i)) for i in range(5)], policy())
    assert set(weights(five).values()) == {Fraction("0.08")}
    assert five.cash_weight == "0.6"
    assert five.risk.sectors[0].at_cap


def test_independent_unequal_rate_simultaneous_caps_and_redistribution() -> None:
    # Rates A:B:C:D=2:1:1:1. At t=.1 A hits .2 position and
    # A+B hits .3 sector simultaneously; C/D then each rise from .1 to .2.
    # All remaining positions bind, leaving .3 cash. A must never steal B's .1.
    result = allocate(
        [
            candidate("A", "Tech", 1),
            candidate("B", "Tech", 2),
            candidate("C", "Other", 2),
            candidate("D", "Third", 2),
        ],
        policy(max_sector_weight="0.3"),
    )
    assert weights(result) == {
        "A": Fraction(1, 5),
        "B": Fraction(1, 10),
        "C": Fraction(1, 5),
        "D": Fraction(1, 5),
    }
    assert result.cash_weight == "0.3"
    assert result.risk.capped_positions == ("A", "C", "D")
    assert [(row.sector, row.at_cap) for row in result.risk.sectors] == [
        ("Other", False),
        ("Tech", True),
        ("Third", False),
    ]


def test_budget_exhaustion_unequal_inverse_rates() -> None:
    # No binding caps: inverse rates 1:1/2:1/4 = 4:2:1.
    # Budget .7 gives .4,.2,.1 exactly and .3 cash.
    result = allocate(
        [candidate("A", "A", 1), candidate("B", "B", 2), candidate("C", "C", 4)],
        policy(max_position_weight="0.8", max_sector_weight="0.9", min_cash_weight="0.3"),
    )
    assert weights(result) == {"A": Fraction("0.4"), "B": Fraction("0.2"), "C": Fraction("0.1")}
    assert result.cash_weight == "0.3" and result.risk.unmet_investable_weight == "0"


def test_joint_decimal_boundary_conserves_investment_and_simultaneous_sector_cap() -> None:
    # .4 / 3 repeats. Joint serialization must retain exactly .4 in this
    # sector, not silently assign three truncation remainders to cash.
    result = allocate([candidate(identity) for identity in "ABC"], policy())
    actual = weights(result)
    assert sum(actual.values()) == Fraction("0.4")
    assert result.cash_weight == "0.6"
    assert actual["A"] > actual["B"] == actual["C"]
    assert actual["A"] - actual["B"] == Fraction(1, 10**36)
    assert all(abs(value - Fraction(2, 15)) < Fraction(1, 10**36) for value in actual.values())
    assert result.risk.sectors[0].at_cap
    # Ambient Decimal precision must not change or break the financial result.
    with localcontext() as context:
        context.prec = 6
        assert allocate([candidate(identity) for identity in "CBA"], policy()) == result


def test_zero_volatility_ineligible_and_rank_limit_do_not_consume_slots() -> None:
    result = allocate(
        [
            candidate("ZERO", volatility=0, score=100),
            candidate("B", score=1),
            candidate("A", score=1),
            candidate("C", score=0),
            candidate("NO", score=99).model_copy(update={"eligible": False}),
        ],
        policy(max_positions=2),
    )
    assert result.selected_ids == ("A", "B")
    assert {row.asset_id: row.reason for row in result.exclusions} == {
        "ZERO": "ZERO_VOLATILITY",
        "NO": "INELIGIBLE",
        "C": "OUTSIDE_TOP_N",
    }
    zero = allocate([candidate("A", volatility=0)], policy())
    assert zero.cash_weight == "1" and not zero.targets
    full = allocate([candidate("A")], policy(min_cash_weight="1.000000"))
    assert full.cash_weight == "1" and "CASH_FLOOR_FULL_CAPITAL" in full.reasons


def test_small_positive_volatility_has_no_epsilon_and_extreme_ratio_is_finite() -> None:
    # Reciprocal of the minimum positive float would overflow; exact rates do not.
    result = allocate(
        [candidate("SMALL", "S", math.nextafter(0.0, 1.0)), candidate("LARGE", "L", 1e308)],
        policy(max_positions=1),
    )
    # Tie-order selects LARGE; raise SMALL's score to establish positive selection.
    assert result.selected_ids == ("LARGE",)
    result = allocate(
        [candidate("SMALL", "S", math.nextafter(0.0, 1.0), 1), candidate("LARGE", "L", 1e308)],
        policy(),
    )
    assert result.selected_ids == ("SMALL", "LARGE")
    assert weights(result) == {"LARGE": Fraction("0.2"), "SMALL": Fraction("0.2")}
    uncapped = allocate(
        [candidate("SMALL", "S", math.nextafter(0.0, 1.0)), candidate("LARGE", "L", 1e308)],
        policy(min_cash_weight="0.9"),
    )
    assert 0 < weights(uncapped)["LARGE"] < Fraction(1, 10**600)
    assert sum(weights(uncapped).values()) == Fraction("0.1")
    assert uncapped.cash_weight == "0.9"


@pytest.mark.parametrize(
    "updates",
    [
        {"max_position_weight": "0"},
        {"max_sector_weight": "0"},
        {"min_cash_weight": "1.01"},
        {"max_positions": True},
        {"max_positions": 0},
        {"weighting": "equal"},
    ],
)
def test_invalid_policy_rejected(updates: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        policy(**updates)


def test_invalid_candidate_and_duplicate_rejected() -> None:
    for volatility in [float("nan"), float("inf"), -0.1]:
        with pytest.raises(ValidationError):
            candidate("A", volatility=volatility)
    with pytest.raises(ValidationError):
        candidate("A", sector="")
    with pytest.raises(ValueError, match="Duplicate"):
        allocate([candidate("A"), candidate("A")], policy())


def test_risk_reports_external_breaches_without_repair() -> None:
    report = assess_targets(
        (
            AllocationTarget(asset_id="A", sector="Unknown", weight="0.3"),
            AllocationTarget(asset_id="B", sector="Unknown", weight="0.3"),
        ),
        "0.01",
        policy(),
    )
    assert not report.compliant
    assert set(report.violations) == {
        "POSITION_CAP",
        "SECTOR_CAP",
        "CASH_FLOOR",
        "INCOMPLETE_ALLOCATION",
    }
    assert report.max_position_weight == "0.3" and report.max_sector_weight == "0.6"


def test_arbitrary_policies_ranks_sectors_and_permutations() -> None:
    rng = random.Random(3301)
    for _ in range(120):
        config = policy(
            max_positions=rng.randint(1, 30),
            max_position_weight=f"0.{rng.randint(1, 99):02}",
            max_sector_weight=f"0.{rng.randint(1, 99):02}",
            min_cash_weight=f"0.{rng.randint(0, 99):02}",
        )
        rows = [
            candidate(
                str(i),
                rng.choice(["Tech", "Energy", "Unknown", "Other"]),
                rng.choice([0, 0.00001, 0.1, 0.2, 0.7, 100]),
                rng.randint(-5, 5),
            )
            for i in range(rng.randint(0, 35))
        ]
        result = allocate(rows, config)
        actual = weights(result)
        cash = Fraction(result.cash_weight)
        assert sum(actual.values()) + cash == 1
        assert all(0 < weight <= Fraction(config.max_position_weight) for weight in actual.values())
        assert cash >= Fraction(config.min_cash_weight)
        assert len(actual) <= config.max_positions and result.risk.compliant
        sector_weights: dict[str, Fraction] = {}
        for row in result.targets:
            sector_weights[row.sector] = sector_weights.get(row.sector, Fraction(0)) + Fraction(
                row.weight
            )
        assert all(
            weight <= Fraction(config.max_sector_weight) for weight in sector_weights.values()
        )
        # If investment fell short, every selected position or its sector is full.
        if cash > Fraction(config.min_cash_weight):
            assert all(
                actual.get(row.asset_id, 0) == Fraction(config.max_position_weight)
                or sector_weights.get(row.sector, 0) == Fraction(config.max_sector_weight)
                for row in rows
                if row.asset_id in result.selected_ids
            )
        rng.shuffle(rows)
        assert allocate(rows, config) == result
        assert AllocationResult.model_validate_json(result.model_dump_json()) == result


def test_fix03_precision_handoff_does_not_size_or_round_trades() -> None:
    fixture = json.loads((ROOT / "fix-03/case.json").read_text())
    assert fixture["label"] == "SYNTHETIC_DATA_ONLY"
    result = allocate([candidate("A")], policy())
    # $1,000 capital * .2 = $200 target, not 2 shares at the $100 raw
    # price: FIX-03 independently declares the slippage-adjusted buy at100.1.
    # Allocation leaves those execution/affordability calculations to #35.
    assert Decimal(result.targets[0].weight) * Decimal(fixture["inputs"]["cash"]) == Decimal("200")
    assert "quantity" not in result.targets[0].model_dump()


def test_pinned_snapshot_momentum_adapter_retains_lineage_and_rejections(tmp_path: Path) -> None:
    config = StrategyConfigV1.from_json((ROOT / "fix-01/strategy.canonical.json").read_bytes())
    digest = json.loads((ROOT / "manifest.json").read_text())["snapshot_sha256"]
    shutil.copytree(ROOT / "snapshot", tmp_path / "snapshot")
    pinned = PinnedSnapshot.open(tmp_path / "snapshot", digest)
    from backend.market_data.repository import MarketRepository

    with MarketRepository(pinned) as repository:
        session = repository.calendar.sessions[-1].session_date
    momentum = evaluate_snapshot(
        pinned, config, datetime(2031, 1, 1, tzinfo=UTC), session, engine_version="allocation-test"
    )
    result = allocate_momentum(momentum, config)
    assert result.momentum == momentum
    assert result.allocation.selected_ids == momentum.selected_ids
    assert result.allocation.risk.compliant
    assert AllocatedMomentum.model_validate_json(result.model_dump_json()) == result
    altered = json.loads(config.model_dump_json())
    altered["portfolio"]["max_positions"] = 1
    with pytest.raises(ValueError, match="config"):
        allocate_momentum(momentum, StrategyConfigV1.model_validate(altered))
