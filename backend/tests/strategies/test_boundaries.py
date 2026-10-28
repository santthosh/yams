import json
import shutil
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from backend.domain.strategy import StrategyConfigV1
from backend.market_data.files import PinnedSnapshot
from backend.market_data.repository import MarketRepository, MarketView
from backend.strategies.eligibility import eligible_universe
from backend.strategies.momentum import evaluate_momentum

ROOT = Path(__file__).resolve().parents[3] / "data/fixtures"


@pytest.fixture
def inputs(tmp_path: Path) -> Iterator[tuple[MarketRepository, MarketView, StrategyConfigV1]]:
    shutil.copytree(ROOT / "snapshot", tmp_path / "snapshot")
    digest = json.loads((ROOT / "manifest.json").read_text())["snapshot_sha256"]
    raw = json.loads((ROOT / "fix-01/strategy.canonical.json").read_text())
    raw["signals"]["require_positive_trend"] = False
    with MarketRepository(PinnedSnapshot.open(tmp_path / "snapshot", digest)) as repository:
        view = repository.as_of(
            datetime(2031, 1, 1, tzinfo=UTC), repository.calendar.sessions[-1].session_date
        )
        yield repository, view, StrategyConfigV1.model_validate(raw)


@pytest.mark.parametrize(
    ("price", "volume", "reason"),
    [
        ("5", 200000, None),
        ("4.99", 300000, "PRICE_BELOW_MINIMUM"),
        ("5", 199999, "LIQUIDITY_BELOW_MINIMUM"),
    ],
)
def test_exact_thresholds_and_strict_trend(
    inputs: tuple[MarketRepository, MarketView, StrategyConfigV1],
    price: str,
    volume: int,
    reason: str | None,
) -> None:
    repository, view, config = inputs
    asset = next(asset for asset in view.assets if asset.asset_id == "SYN:AAA")
    bars = tuple(
        bar.model_copy(
            update={
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "adjusted_close": price,
                "volume": volume,
            }
        )
        for bar in view.bars
        if bar.asset_id == asset.asset_id
    )
    view = replace(view, assets=(asset,), bars=bars)
    candidate = eligible_universe(view, repository.calendar, config)[0]
    assert candidate.eligible == (reason is None)
    if reason:
        assert reason in candidate.reasons
    if price == "5" and volume == 200000:
        assert candidate.median_dollar_volume == "1000000"
        assert candidate.trend_sma == "5"
        trend = config.model_copy(
            update={"signals": config.signals.model_copy(update={"require_positive_trend": True})}
        )
        assert "NONPOSITIVE_TREND" in eligible_universe(view, repository.calendar, trend)[0].reasons


def test_sector_and_metadata_availability(
    inputs: tuple[MarketRepository, MarketView, StrategyConfigV1],
) -> None:
    repository, view, config = inputs
    asset = view.assets[0]
    missing = replace(view, assets=(replace(asset, sector=None),))
    assert "MISSING_SECTOR" in eligible_universe(missing, repository.calendar, config)[0].reasons
    assert asset.sector is not None and asset.alias is not None
    unknown = replace(asset, sector=asset.sector.model_copy(update={"sector": "Unknown"}))
    assert eligible_universe(replace(view, assets=(unknown,)), repository.calendar, config)[
        0
    ].eligible
    late = replace(
        asset,
        alias=asset.alias.model_copy(
            update={"available_at": view.cutoff + timedelta(microseconds=1)}
        ),
    )
    assert (
        "MISSING_ASSET_ALIAS"
        in eligible_universe(replace(view, assets=(late,)), repository.calendar, config)[0].reasons
    )


def test_empty_future_cutoff_and_conflicts(
    inputs: tuple[MarketRepository, MarketView, StrategyConfigV1],
) -> None:
    repository, view, config = inputs
    assert (
        evaluate_momentum(
            replace(view, assets=()), repository.calendar, config, engine_version="test-v1"
        ).selected_ids
        == ()
    )
    expected = evaluate_momentum(view, repository.calendar, config, engine_version="test-v1")
    future = view.bars[0].model_copy(
        update={"available_at": view.cutoff + timedelta(microseconds=1), "adjusted_close": "999999"}
    )
    assert (
        evaluate_momentum(
            replace(view, bars=(*view.bars, future)),
            repository.calendar,
            config,
            engine_version="test-v1",
        )
        == expected
    )
    last = next(
        bar
        for bar in view.bars
        if bar.asset_id == "SYN:AAA" and bar.session_date == view.session_date
    )
    before = repository.as_of(last.available_at - timedelta(microseconds=1), view.session_date)
    assert (
        "MISSING_HISTORY"
        in next(
            row
            for row in eligible_universe(before, repository.calendar, config)
            if row.asset_id == last.asset_id
        ).reasons
    )
    conflict = last.model_copy(update={"adjusted_close": "99999"})
    bad = replace(view, bars=(*view.bars, conflict))
    reversed_bad = replace(bad, bars=tuple(reversed(bad.bars)))
    first = evaluate_momentum(bad, repository.calendar, config, engine_version="test-v1")
    assert first == evaluate_momentum(
        reversed_bad, repository.calendar, config, engine_version="test-v1"
    )
    assert (
        "CONFLICTING_BAR"
        in next(row for row in first.candidates if row.asset_id == last.asset_id).reasons
    )


def test_numerical_failure_and_blocked_evidence_are_explicit(
    inputs: tuple[MarketRepository, MarketView, StrategyConfigV1],
) -> None:
    from backend.market_data.repository import Diagnostic
    from backend.strategies.momentum import evaluate_snapshot

    repository, view, config = inputs
    baseline = evaluate_momentum(view, repository.calendar, config, engine_version="test-v1")
    assert (
        evaluate_snapshot(
            repository.snapshot, config, view.cutoff, view.session_date, engine_version="test-v1"
        )
        == baseline
    )
    # Finite provider decimals can still exceed floating statistical resolution.
    # Keep the input visibly excluded rather than allowing inf into cross-sectional math.
    huge = replace(
        view,
        bars=tuple(
            bar.model_copy(update={"adjusted_close": "1" + "0" * 400})
            if bar.asset_id == "SYN:AAA" and bar.session_date == view.session_date
            else bar
            for bar in view.bars
        ),
    )
    evaluated = evaluate_momentum(huge, repository.calendar, config, engine_version="test-v1")
    rejected = next(row for row in evaluated.candidates if row.asset_id == "SYN:AAA")
    assert "NONFINITE_FEATURE" in rejected.reasons
    assert rejected.features is None and rejected.scoring is None and rejected.rank is None
    assert not rejected.eligible and "SYN:AAA" not in evaluated.selected_ids
    blocked = evaluate_momentum(
        replace(view, diagnostics=(*view.diagnostics, Diagnostic("SNAPSHOT_BLOCKED"))),
        repository.calendar,
        config,
        engine_version="test-v1",
    )
    assert blocked.selected_ids == ()
    assert all("SNAPSHOT_BLOCKED" in row.reasons for row in blocked.candidates)
    assert any(row.reason == "SNAPSHOT_BLOCKED" for row in blocked.data_diagnostics)
    unverified = replace(
        view,
        bars=tuple(
            bar.model_copy(update={"price_basis": "provider_unverified"}) for bar in view.bars
        ),
    )
    assert all(
        "UNVERIFIED_PRICE_VOLUME_BASIS" in row.reasons
        for row in eligible_universe(unverified, repository.calendar, config)
    )
