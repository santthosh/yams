"""Owned private scenario probe, not a recommendation or public forecast endpoint.

The authored allocation/cost exercises the real worker against actual committed
SYNTHETIC_DATA_ONLY observations. Normal startup never calls this script.
"""

import json
from datetime import date
from uuid import uuid4

from sqlalchemy.orm import Session

from backend.domain.forecast import ForecastAllocation, ForecastWeight
from backend.forecasting.contracts import ForecastInputs
from backend.forecasting.service import admit_forecast
from backend.market_data.catalog import verified_snapshot
from backend.market_data.models import Calendar
from backend.persistence.database import Settings, database_engine
from backend.persistence.models.snapshot import CurrentSnapshot, DatasetSnapshot
from backend.persistence.models.strategy import StrategyVersion
from backend.persistence.readiness import read_workspace
from backend.portfolio.execution import calendar_digest
from backend.portfolio.ledger import create_portfolio
from backend.strategies.clock import decision_cutoff
from backend.strategies.registry import DEFAULT_VERSION_ID, version_view


def main() -> None:
    settings = Settings.from_environment()
    assert settings.database_url is not None
    engine = database_engine(settings.database_url)
    with Session(engine) as session:
        pointer = session.get(CurrentSnapshot, "synthetic_fixture")
        version = session.get(StrategyVersion, DEFAULT_VERSION_ID)
        assert pointer is not None and version is not None
        snapshot = session.get(DatasetSnapshot, pointer.snapshot_id)
        assert snapshot is not None
        pinned = verified_snapshot(snapshot, settings.artifact_root)
        config_hash = version_view(version).config_sha256
    calendar = Calendar.model_validate_json(
        pinned.artifacts[pinned.manifest.calendar.artifact_path]
    )
    day = date(2028, 7, 17)
    cutoff = decision_cutoff(calendar, day)
    owner = uuid4()
    create_portfolio(
        engine,
        portfolio_id=owner,
        workspace_id=read_workspace(engine).id,
        strategy_version_id=DEFAULT_VERSION_ID,
        snapshot_id=pinned.manifest.snapshot_id(),
        name="SYNTHETIC_DATA_ONLY authored scenario probe",
        created_at=cutoff,
    )
    inputs = ForecastInputs(
        portfolio_id=owner,
        portfolio_revision=1,
        strategy_version_id=DEFAULT_VERSION_ID,
        config_sha256=config_hash,
        snapshot_id=pinned.manifest.snapshot_id(),
        snapshot_sha256=pinned.manifest.manifest_hash(),
        calendar_sha256=calendar_digest(calendar),
        source_mode="synthetic_fixture",
        as_of_session=day,
        decision_cutoff_utc=cutoff,
        valuation_as_of_session=day,
        initial_value_usd="1000.00",
        current_allocation=ForecastAllocation(weights=(), cash_weight="1", upfront_cost_usd="0.00"),
        proposed_allocation=ForecastAllocation(
            weights=(
                ForecastWeight(asset_id="SYN:AAA", weight="0.2"),
                ForecastWeight(asset_id="SYN:BBB", weight="0.2"),
            ),
            cash_weight="0.6",
            upfront_cost_usd="1.00",
        ),
    )
    accepted = admit_forecast(engine, settings.artifact_root, inputs)
    print(
        json.dumps(
            {
                "label": "SYNTHETIC_DATA_ONLY",
                "probe_kind": "AUTHORED_ALLOCATION_NOT_A_RECOMMENDATION",
                "portfolio_id": str(owner),
                "forecast_id": str(accepted.forecast_id),
                "job_id": str(accepted.job_id),
            }
        )
    )
    engine.dispose()


if __name__ == "__main__":
    main()
