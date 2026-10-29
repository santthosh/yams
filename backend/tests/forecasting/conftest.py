import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from backend.domain.forecast import ForecastAllocation, ForecastWeight
from backend.forecasting.contracts import ForecastInputs
from backend.market_data.files import PinnedSnapshot
from backend.market_data.models import Calendar
from backend.portfolio.execution import calendar_digest
from backend.strategies.clock import decision_cutoff


@pytest.fixture
def pinned() -> PinnedSnapshot:
    root = Path(__file__).resolve().parents[3] / "data/fixtures/snapshot"
    return PinnedSnapshot.open(
        root, hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest()
    )


@pytest.fixture
def inputs(pinned: PinnedSnapshot) -> ForecastInputs:
    calendar = Calendar.model_validate_json(
        pinned.artifacts[pinned.manifest.calendar.artifact_path]
    )
    day = date(2028, 7, 17)
    allocation = ForecastAllocation(
        weights=(
            ForecastWeight(asset_id="SYN:AAA", weight="0.5"),
            ForecastWeight(asset_id="SYN:BBB", weight="0.5"),
        ),
        cash_weight="0",
        upfront_cost_usd="0.00",
    )
    return ForecastInputs(
        portfolio_id=UUID(int=1),
        portfolio_revision=1,
        strategy_version_id=UUID(int=2),
        config_sha256="b" * 64,
        snapshot_id=pinned.manifest.snapshot_id(),
        snapshot_sha256=pinned.manifest.manifest_hash(),
        calendar_sha256=calendar_digest(calendar),
        source_mode="synthetic_fixture",
        as_of_session=day,
        decision_cutoff_utc=decision_cutoff(calendar, day),
        valuation_as_of_session=day,
        initial_value_usd="1000.00",
        current_allocation=allocation,
        proposed_allocation=allocation,
    )


@pytest.fixture
def cash_precision() -> dict[str, Any]:
    case = json.loads(
        (Path(__file__).resolve().parents[3] / "data/fixtures/fix-08/case.json").read_text()
    )
    return {
        "inputs": case["inputs"]["precision_cash_probe"],
        "expected": case["expected"]["precision_cash_probe"],
    }
