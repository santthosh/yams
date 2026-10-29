import hashlib
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID

import pytest

from backend.domain.recommendation_api import RecommendationRequest
from backend.market_data.files import PinnedSnapshot
from backend.market_data.models import Calendar
from backend.portfolio.execution import PortfolioState, calendar_digest
from backend.portfolio.recommendation_contracts import RecommendationPayload
from backend.strategies.clock import decision_cutoff
from backend.strategies.registry import DEFAULT_VERSION_ID, default_config


@pytest.fixture
def pinned() -> PinnedSnapshot:
    root = Path(__file__).resolve().parents[3] / "data/fixtures/snapshot"
    return PinnedSnapshot.open(
        root, hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest()
    )


@pytest.fixture
def payload(pinned: PinnedSnapshot) -> RecommendationPayload:
    config = default_config()
    calendar = Calendar.model_validate_json(
        pinned.artifacts[pinned.manifest.calendar.artifact_path]
    )
    day = date(2028, 7, 17)
    return RecommendationPayload(
        recommendation_id=UUID(int=1),
        forecast_id=UUID(int=2),
        portfolio_id=UUID(int=3),
        portfolio_revision=1,
        last_sequence=1,
        state_observed_at=datetime(2026, 10, 29, tzinfo=UTC),
        state=PortfolioState(cash_usd="1000.00", positions=()),
        inputs=RecommendationRequest(as_of_session=day, clock_mode="synthetic_replay"),
        strategy_version_id=DEFAULT_VERSION_ID,
        config_canonical_json=config.canonical_bytes().decode(),
        config_sha256=config.config_hash(),
        snapshot_id=pinned.manifest.snapshot_id(),
        snapshot_sha256=pinned.manifest.manifest_hash(),
        calendar_sha256=calendar_digest(calendar),
        source_mode="synthetic_fixture",
        decision_cutoff_utc=decision_cutoff(calendar, day),
        engine_version="a" * 64,
        requested_at=datetime(2026, 10, 29, tzinfo=UTC),
    )
