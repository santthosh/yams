import json
import shutil
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from backend.domain.strategy import StrategyConfigV1
from backend.market_data.files import PinnedSnapshot
from backend.market_data.repository import MarketRepository
from backend.strategies.eligibility import eligible_universe

ROOT = Path(__file__).resolve().parents[3] / "data/fixtures"


def test_fixture_eligibility_is_order_independent_and_future_safe(tmp_path: Path) -> None:
    shutil.copytree(ROOT / "snapshot", tmp_path / "snapshot")
    digest = json.loads((ROOT / "manifest.json").read_text())["snapshot_sha256"]
    config_data = json.loads((ROOT / "fix-01/strategy.canonical.json").read_text())
    config_data["signals"]["require_positive_trend"] = False
    config = StrategyConfigV1.model_validate(config_data)
    with MarketRepository(PinnedSnapshot.open(tmp_path / "snapshot", digest)) as repository:
        view = repository.as_of(
            datetime(2031, 1, 1, tzinfo=UTC), repository.calendar.sessions[-1].session_date
        )
        expected = eligible_universe(view, repository.calendar, config)
        assert {row.asset_id for row in expected if row.eligible} == {
            "SYN:AAA",
            "SYN:BBB",
            "SYN:CCC",
            "SYN:ZERO",
        }
        assert (
            eligible_universe(
                replace(view, bars=tuple(reversed(view.bars))), repository.calendar, config
            )
            == expected
        )
        future = view.bars[-1].model_copy(
            update={
                "available_at": view.cutoff + timedelta(microseconds=1),
                "adjusted_close": "999999",
            }
        )
        assert (
            eligible_universe(replace(view, bars=(*view.bars, future)), repository.calendar, config)
            == expected
        )
        without = replace(
            view,
            bars=tuple(
                bar
                for bar in view.bars
                if not (bar.asset_id == "SYN:AAA" and bar.session_date == view.session_date)
            ),
        )
        rejected = {
            row.asset_id: row for row in eligible_universe(without, repository.calendar, config)
        }
        assert "MISSING_HISTORY" in rejected["SYN:AAA"].reasons
        assert not rejected["SYN:AAA"].eligible
