import json
import shutil
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from backend.domain.strategy import StrategyConfigV1
from backend.market_data.files import PinnedSnapshot
from backend.market_data.repository import MarketRepository
from backend.strategies.momentum import MomentumEvaluation, ScoreEvidence, evaluate_momentum

ROOT = Path(__file__).resolve().parents[3] / "data/fixtures"


def test_ties_and_zero_volatility_do_not_consume_selection_slot(tmp_path: Path) -> None:
    shutil.copytree(ROOT / "snapshot", tmp_path / "snapshot")
    digest = json.loads((ROOT / "manifest.json").read_text())["snapshot_sha256"]
    raw = json.loads((ROOT / "fix-01/strategy.canonical.json").read_text())
    raw["signals"]["require_positive_trend"] = False
    raw["portfolio"]["max_positions"] = 1
    config = StrategyConfigV1.model_validate(raw)
    with MarketRepository(PinnedSnapshot.open(tmp_path / "snapshot", digest)) as repository:
        view = repository.as_of(
            datetime(2031, 1, 1, tzinfo=UTC), repository.calendar.sessions[-1].session_date
        )
        source = [bar for bar in view.bars if bar.asset_id == "SYN:AAA"]
        # Two identical authored synthetic price paths tie; immutable ID breaks the tie.
        tied = replace(
            view,
            assets=tuple(
                asset for asset in view.assets if asset.asset_id in {"SYN:AAA", "SYN:BBB"}
            ),
            bars=tuple(
                bar.model_copy(update={"asset_id": identity})
                for identity in ["SYN:BBB", "SYN:AAA"]
                for bar in source
            ),
        )
        first = evaluate_momentum(tied, repository.calendar, config, engine_version="test-v1")
        assert first.selected_ids == ("SYN:AAA",)
        assert [row.rank for row in first.candidates] == [1, 2]
        assert all(row.scoring is not None and row.scoring.score == 0 for row in first.candidates)
        assert (
            evaluate_momentum(
                replace(tied, bars=tuple(reversed(tied.bars)), assets=tuple(reversed(tied.assets))),
                repository.calendar,
                config,
                engine_version="test-v1",
            )
            == first
        )
        assert MomentumEvaluation.model_validate_json(first.model_dump_json()) == first
        # A flat zero-volatility path outranks a declining path diagnostically, but
        # the single allocation slot must go to the positive-volatility candidate.
        declining = tuple(
            bar.model_copy(update={"adjusted_close": str(10000 - index)})
            for index, bar in enumerate(source)
        )
        zeros = tuple(bar for bar in view.bars if bar.asset_id == "SYN:ZERO")
        mixed = replace(
            view,
            assets=tuple(
                asset for asset in view.assets if asset.asset_id in {"SYN:AAA", "SYN:ZERO"}
            ),
            bars=declining + zeros,
        )
        result = evaluate_momentum(mixed, repository.calendar, config, engine_version="test-v1")
        rows = {row.asset_id: row for row in result.candidates}
        assert rows["SYN:ZERO"].rank == 1
        assert rows["SYN:ZERO"].eligible and not rows["SYN:ZERO"].allocation_eligible
        assert "ZERO_VOLATILITY" in rows["SYN:ZERO"].reasons
        assert result.selected_ids == ("SYN:AAA",)


def test_independent_two_asset_score_contributions(tmp_path: Path) -> None:
    import pytest

    shutil.copytree(ROOT / "snapshot", tmp_path / "snapshot")
    digest = json.loads((ROOT / "manifest.json").read_text())["snapshot_sha256"]
    raw = json.loads((ROOT / "fix-01/strategy.canonical.json").read_text())
    raw["signals"]["require_positive_trend"] = False
    config = StrategyConfigV1.model_validate(raw)
    with MarketRepository(PinnedSnapshot.open(tmp_path / "snapshot", digest)) as repository:
        view = repository.as_of(
            datetime(2031, 1, 1, tzinfo=UTC), repository.calendar.sessions[-1].session_date
        )
        source = [bar for bar in view.bars if bar.asset_id == "SYN:AAA"]
        bars = tuple(
            bar.model_copy(
                update={
                    "asset_id": identity,
                    "adjusted_close": "60"
                    if identity == "SYN:AAA" and bar.session_date == view.session_date
                    else "50",
                }
            )
            for identity in ("SYN:AAA", "SYN:BBB")
            for bar in source
        )
        result = evaluate_momentum(
            replace(
                view,
                assets=tuple(
                    asset for asset in view.assets if asset.asset_id in {"SYN:AAA", "SYN:BBB"}
                ),
                bars=bars,
            ),
            repository.calendar,
            config,
            engine_version="test-v1",
        )
        rows = {row.asset_id: row for row in result.candidates}
        # Two unequal observations have population z-scores +1/-1 in each feature.
        # Rising path: .60 + .25 - .15 = .70; flat path has the opposite score.
        score = rows["SYN:AAA"].scoring
        assert score is not None
        assert isinstance(score, ScoreEvidence)
        assert score.momentum_long_contribution == pytest.approx(0.60, abs=1e-12)
        assert score.momentum_short_contribution == pytest.approx(0.25, abs=1e-12)
        assert score.volatility_contribution == pytest.approx(-0.15, abs=1e-12)
        assert score.score == pytest.approx(0.70, abs=1e-12)
        assert rows["SYN:BBB"].scoring is not None
        assert rows["SYN:BBB"].scoring.score == pytest.approx(-0.70, abs=1e-12)
        assert result.selected_ids == ("SYN:AAA",)
