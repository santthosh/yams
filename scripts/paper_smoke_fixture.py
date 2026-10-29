"""Owned SYNTHETIC_DATA_ONLY input for disposable source/release smoke projects."""

import json
from datetime import date, timedelta
from uuid import uuid4

from sqlalchemy.orm import Session

from backend.jobs.queue import Queue
from backend.market_data.catalog import verified_snapshot
from backend.market_data.models import Calendar
from backend.persistence.database import Settings, database_engine
from backend.persistence.models.ledger import RecommendationReference
from backend.persistence.models.snapshot import CurrentSnapshot, DatasetSnapshot
from backend.persistence.readiness import read_workspace
from backend.portfolio.batches import approve_batch
from backend.portfolio.fills import enqueue_batch_attempt
from backend.portfolio.ledger import create_portfolio, digest
from backend.strategies.clock import decision_cutoff
from backend.strategies.registry import DEFAULT_VERSION_ID


def main() -> None:
    settings = Settings.from_environment()
    assert settings.database_url is not None
    engine = database_engine(settings.database_url)
    with Session(engine) as session:
        pointer = session.get(CurrentSnapshot, "synthetic_fixture")
        assert pointer is not None
        source = session.get(DatasetSnapshot, pointer.snapshot_id)
        assert source is not None
        pinned = verified_snapshot(source, settings.artifact_root)
    calendar = Calendar.model_validate_json(
        pinned.artifacts[pinned.manifest.calendar.artifact_path]
    )
    decision = date(2028, 7, 17)
    cutoff = decision_cutoff(calendar, decision)
    owner, rec = uuid4(), uuid4()
    create_portfolio(
        engine,
        portfolio_id=owner,
        workspace_id=read_workspace(engine).id,
        strategy_version_id=DEFAULT_VERSION_ID,
        name="SYNTHETIC_DATA_ONLY execution smoke",
        created_at=cutoff,
    )
    content = {
        "label": "SYNTHETIC_DATA_ONLY",
        "execution_intent": {
            "schema_version": 1,
            "engine_version": "smoke-fixture-v1",
            "orders": [
                {
                    "key": "BUY:SYN:AAA",
                    "asset_id": "SYN:AAA",
                    "sector": "Technology",
                    "side": "BUY",
                    "requested_quantity": "2.000000",
                }
            ],
        },
    }
    with Session(engine) as session, session.begin():
        session.add(
            RecommendationReference(
                id=rec,
                portfolio_id=owner,
                strategy_version_id=DEFAULT_VERSION_ID,
                snapshot_id=source.id,
                as_of_session=decision,
                decision_cutoff=cutoff,
                portfolio_revision=1,
                source_mode="synthetic_fixture",
                content=content,
                content_sha256=digest(content),
                disposition="ready",
                created_at=cutoff,
            )
        )
    batch = approve_batch(
        engine,
        owner,
        rec,
        expected_revision=1,
        idempotency_key=uuid4(),
        pinned=pinned,
        approved_at=cutoff,
    )
    eligible = next(row for row in calendar.sessions if row.open_at > cutoff)
    job = enqueue_batch_attempt(
        Queue(engine), batch, fixture_observed_at=eligible.close_at + timedelta(seconds=1)
    )
    print(json.dumps({"portfolio_id": str(owner), "batch_id": str(batch), "job_id": str(job)}))
    engine.dispose()


if __name__ == "__main__":
    main()
