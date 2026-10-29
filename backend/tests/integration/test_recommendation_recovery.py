"""Real stale-state, rollback and restart proofs over owned synthetic accounts."""

import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from multiprocessing import get_context
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.forecasting.contracts import ForecastPayload
from backend.forecasting.service import (
    ForecastAccepted,
    _enqueue_frozen_forecast,
    admit_forecast,
    read_forecast,
)
from backend.jobs.handlers.evaluate_portfolio import evaluate_portfolio
from backend.jobs.queue import Queue
from backend.jobs.worker import Worker
from backend.market_data.catalog import verified_snapshot
from backend.market_data.snapshots import PublicationFenceError
from backend.persistence.bootstrap import MIGRATIONS, bootstrap
from backend.persistence.database import database_engine
from backend.persistence.models.snapshot import DatasetSnapshot
from backend.portfolio import recommendations as recommendation_service
from backend.portfolio.batches import approve_batch
from backend.portfolio.recommendation_queries import RecommendationPending, detail
from backend.portfolio.recommendations import (
    RecommendationAdmissionError,
    admit_recommendation,
    seal_recommendation,
)
from backend.tests.integration import test_evaluations
from backend.tests.integration.test_bootstrap import database as database
from backend.tests.integration.test_bootstrap import isolated_url
from backend.tests.integration.test_forecasts import prepare
from backend.tests.integration.test_recommendations import request_for

pytestmark = pytest.mark.integration


def test_lease_expiring_during_publication_cannot_commit_partial_graph(
    database: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, request = request_for(database, tmp_path)
    accepted = admit_recommendation(database, tmp_path, owner, request)
    queue = Queue(database)
    lease = queue.claim("publication-deadline-proof")
    assert lease is not None
    encoded = evaluate_portfolio(lease.payload, get_context("spawn").Event(), root=tmp_path)
    original = _enqueue_frozen_forecast

    def expire(session: Session, controller: Queue, payload: ForecastPayload) -> ForecastAccepted:
        result = original(session, controller, payload)
        # The real DB transaction is open; advance only its controlled queue clock.
        # No long wall sleep or modification of the immutable original deadline.
        monkeypatch.setattr(queue, "clock", lambda session: lease.deadline + timedelta(seconds=1))
        return result

    monkeypatch.setattr(recommendation_service, "_enqueue_frozen_forecast", expire)
    with pytest.raises(PublicationFenceError):
        seal_recommendation(queue, lease, encoded)
    with database.connect() as connection:
        for table in ("recommendation", "recommendation_publication", "forecast"):
            assert connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0
        assert (
            connection.execute(
                text("SELECT status FROM job WHERE id=:id"), {"id": accepted.job_id}
            ).scalar_one()
            == "running"
        )


def test_populated_forecast_schema_upgrade_preserves_original_jobs_and_accounts(
    database: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prior = tmp_path / "prior-migrations"
    shutil.copytree(MIGRATIONS, prior)
    (prior / "versions/0009_portfolio_reviews.py").unlink()
    (prior / "versions/0008_recommendations.py").unlink()
    root = tmp_path / "artifacts"
    with monkeypatch.context() as scoped:
        scoped.setattr(test_evaluations, "bootstrap", lambda engine: bootstrap(engine, prior))
        inputs = prepare(database, root)
    with database.connect() as connection:
        assert (
            connection.execute(text("SELECT to_regclass('recommendation_run')")).scalar_one()
            is None
        )
    completed = admit_forecast(database, root, inputs)
    queue = Queue(database)
    assert Worker(queue, artifact_root=root).run_once()
    original = read_forecast(database, root, completed.forecast_id)
    assert original is not None and original.result is not None
    queued = admit_forecast(database, root, inputs)
    bootstrap(database)
    retained = read_forecast(database, root, completed.forecast_id)
    assert retained == original
    pending = read_forecast(database, root, queued.forecast_id)
    assert pending is not None and pending.job.status == "queued" and pending.result is None
    with database.connect() as connection:
        for table in ("recommendation_run", "recommendation_publication", "recommendation"):
            assert connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0
        assert connection.execute(
            text("SELECT cash_usd,revision,last_sequence FROM paper_portfolio")
        ).one() == (1000, 1, 1)
        assert connection.execute(text("SELECT count(*) FROM ledger_event")).scalar_one() == 1
    assert Worker(queue, artifact_root=root).run_once()
    result = read_forecast(database, root, queued.forecast_id)
    assert result is not None and result.result is not None
    assert result.result.fingerprint == original.result.fingerprint


def test_late_calendar_unavailable_preserves_recommendation_analysis(
    database: Engine, tmp_path: Path
) -> None:
    owner, request = request_for(database, tmp_path)
    request = request.model_copy(update={"as_of_session": date(2030, 12, 30)})
    accepted = admit_recommendation(database, tmp_path, owner, request)
    queue = Queue(database)
    assert Worker(queue, artifact_root=tmp_path).run_once()
    assert Worker(queue, artifact_root=tmp_path).run_once()
    result = detail(database, tmp_path, accepted.recommendation_id)
    assert result is not None and result.forecast is not None
    assert result.forecast_job.status == "completed" and result.forecast.status == "unavailable"
    assert result.forecast.unavailable_reason == "CALENDAR_UNAVAILABLE"
    assert result.forecast.proposed is None and result.forecast.hold_unchanged is None
    assert result.candidates and result.target_weights and result.actions
    assert result.is_current and result.status == "ready"
    with database.connect() as connection:
        assert (
            connection.execute(
                text("SELECT cash_usd FROM paper_portfolio WHERE id=:id"), {"id": owner}
            ).scalar_one()
            == 1000
        )


def test_revision_change_preserves_expired_evidence_and_approval_digest(
    database: Engine, tmp_path: Path
) -> None:
    owner, request = request_for(database, tmp_path)
    queue = Queue(database)
    first = admit_recommendation(database, tmp_path, owner, request)
    assert Worker(queue, artifact_root=tmp_path).run_once()
    assert Worker(queue, artifact_root=tmp_path).run_once()
    before = detail(database, tmp_path, first.recommendation_id)
    assert before is not None
    second = admit_recommendation(database, tmp_path, owner, request)
    lease = queue.claim("revision-interleaving")
    assert lease is not None and lease.job_id == second.job_id
    encoded = evaluate_portfolio(lease.payload, get_context("spawn").Event(), root=tmp_path)
    with Session(database) as session:
        source = session.get(DatasetSnapshot, before.snapshot_id)
        assert source is not None
        pinned = verified_snapshot(source, tmp_path)
    approve_batch(
        database,
        owner,
        first.recommendation_id,
        expected_revision=1,
        idempotency_key=uuid4(),
        pinned=pinned,
        approved_at=before.decision_cutoff_utc + timedelta(seconds=1),
    )
    seal_recommendation(queue, lease, encoded)
    expired = detail(database, tmp_path, second.recommendation_id)
    assert expired is not None and expired.status == "expired" and not expired.is_current
    assert expired.portfolio_revision == 1 and expired.current_portfolio_revision == 2
    assert "PORTFOLIO_REVISION_CHANGED" in expired.stale_reasons
    assert expired.actions == before.actions and expired.target_weights == before.target_weights
    assert expired.forecast is None and expired.forecast_job.status == "queued"
    with pytest.raises(RecommendationAdmissionError, match="STATE_CONFLICT"):
        admit_recommendation(database, tmp_path, owner, request)
    with database.connect() as connection:
        assert connection.execute(
            text("SELECT cash_usd,revision FROM paper_portfolio WHERE id=:id"), {"id": owner}
        ).one() == (1000, 2)
        assert connection.execute(text("SELECT count(*) FROM paper_fill")).scalar_one() == 0


def test_completion_failure_rolls_back_recommendation_and_forecast_graph(
    database: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, request = request_for(database, tmp_path)
    accepted = admit_recommendation(database, tmp_path, owner, request)
    queue = Queue(database)
    lease = queue.claim("completion-rollback")
    assert lease is not None
    encoded = evaluate_portfolio(lease.payload, get_context("spawn").Event(), root=tmp_path)

    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("CONTROLLED_COMPLETION_WRITE_FAILURE")

    with monkeypatch.context() as scoped:
        scoped.setattr(queue, "finish_attempt", fail)
        with pytest.raises(RuntimeError, match="CONTROLLED_COMPLETION_WRITE_FAILURE"):
            seal_recommendation(queue, lease, encoded)
    with database.connect() as connection:
        for table in ("recommendation", "recommendation_publication", "forecast"):
            assert connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0
        assert (
            connection.execute(
                text("SELECT status FROM job WHERE id=:id"), {"id": accepted.job_id}
            ).scalar_one()
            == "running"
        )
    seal_recommendation(queue, lease, encoded)
    with pytest.raises(PublicationFenceError):
        seal_recommendation(queue, lease, encoded)
    result = detail(database, tmp_path, accepted.recommendation_id)
    assert result is not None and result.forecast_job.status == "queued"
    with database.connect() as connection:
        for table in ("recommendation", "recommendation_publication", "forecast"):
            assert connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 1


def test_prepare_recommendation_restart() -> None:
    base = database_engine(isolated_url())
    name = "test_recommendation_restart_" + uuid4().hex[:12]
    with base.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    base.dispose()
    engine = database_engine(
        make_url(isolated_url()).set(database=name).render_as_string(hide_password=False)
    )
    try:
        root = Path("/evidence/recommendation-artifacts")
        owner, request = request_for(engine, root)
        accepted = admit_recommendation(engine, root, owner, request)
        queue = Queue(engine)
        assert Worker(queue, artifact_root=root).run_once()
        assert Worker(queue, artifact_root=root).run_once()
        original = detail(engine, root, accepted.recommendation_id)
        assert original is not None and original.forecast is not None
        queued = admit_recommendation(engine, root, owner, request)
        Path("/evidence/recommendations.json").write_text(
            json.dumps(
                {
                    "database": name,
                    "completed": str(accepted.recommendation_id),
                    "queued": str(queued.recommendation_id),
                    "result": original.model_dump(mode="json"),
                }
            )
        )
    finally:
        engine.dispose()


@pytest.mark.restart_verify
def test_recommendation_and_queued_inputs_survive_actual_restart() -> None:
    saved = json.loads(Path("/evidence/recommendations.json").read_text())
    assert saved["database"].startswith("test_recommendation_restart_")
    engine = database_engine(
        make_url(isolated_url())
        .set(database=saved["database"])
        .render_as_string(hide_password=False)
    )
    try:
        root = Path("/evidence/recommendation-artifacts")
        with ThreadPoolExecutor(max_workers=2) as executor:
            originals = list(
                executor.map(lambda _: detail(engine, root, UUID(saved["completed"])), range(2))
            )
        assert all(
            original is not None and original.model_dump(mode="json") == saved["result"]
            for original in originals
        )
        with pytest.raises(RecommendationPending):
            detail(engine, root, UUID(saved["queued"]))
        queue = Queue(engine)
        assert Worker(queue, artifact_root=root).run_once()
        assert Worker(queue, artifact_root=root).run_once()
        queued = detail(engine, root, UUID(saved["queued"]))
        assert queued is not None and queued.forecast is not None
        assert queued.forecast.fingerprint == saved["result"]["forecast"]["fingerprint"]
        assert queued.portfolio_revision == saved["result"]["portfolio_revision"] == 1
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT cash_usd FROM paper_portfolio")).scalar_one()
                == 1000
            )
            assert connection.execute(text("SELECT count(*) FROM paper_fill")).scalar_one() == 0
    finally:
        engine.dispose()
