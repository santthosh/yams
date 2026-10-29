"""Real PostgreSQL/worker/fence/restart proofs over owned SYNTHETIC_DATA_ONLY inputs."""

import json
import multiprocessing as mp
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from backend.domain.forecast import ForecastAllocation, ForecastWeight
from backend.forecasting import service
from backend.forecasting.contracts import ForecastInputs
from backend.forecasting.service import admit_forecast, read_forecast, seal_forecast
from backend.jobs.handlers.forecast import forecast
from backend.jobs.queue import Queue
from backend.jobs.worker import Worker
from backend.market_data.catalog import verified_snapshot
from backend.market_data.models import Calendar
from backend.market_data.snapshots import PublicationFenceError
from backend.persistence.bootstrap import MIGRATIONS, bootstrap
from backend.persistence.database import database_engine
from backend.persistence.models.snapshot import DatasetSnapshot
from backend.persistence.models.strategy import StrategyVersion
from backend.persistence.readiness import read_workspace
from backend.portfolio.execution import calendar_digest
from backend.portfolio.ledger import create_portfolio
from backend.strategies.clock import decision_cutoff
from backend.strategies.registry import DEFAULT_VERSION_ID, version_view
from backend.tests.integration.test_bootstrap import database as database
from backend.tests.integration.test_bootstrap import isolated_url
from backend.tests.integration.test_evaluations import prepare as prepare_snapshot

pytestmark = pytest.mark.integration


def prepare(database: Engine, root: Path) -> ForecastInputs:
    request = prepare_snapshot(database, root)
    with Session(database) as session:
        snapshot = session.get(DatasetSnapshot, request.snapshot_id)
        version = session.get(StrategyVersion, DEFAULT_VERSION_ID)
        assert snapshot is not None and version is not None
        pinned = verified_snapshot(snapshot, root)
        config_hash = version_view(version).config_sha256
    calendar = Calendar.model_validate_json(
        pinned.artifacts[pinned.manifest.calendar.artifact_path]
    )
    cutoff = decision_cutoff(calendar, request.as_of_session)
    owner = uuid4()
    create_portfolio(
        database,
        portfolio_id=owner,
        workspace_id=read_workspace(database).id,
        strategy_version_id=DEFAULT_VERSION_ID,
        name="SYNTHETIC_DATA_ONLY forecast probe",
        created_at=cutoff,
    )
    return ForecastInputs(
        portfolio_id=owner,
        portfolio_revision=1,
        strategy_version_id=DEFAULT_VERSION_ID,
        config_sha256=config_hash,
        snapshot_id=request.snapshot_id,
        snapshot_sha256=pinned.manifest.manifest_hash(),
        calendar_sha256=calendar_digest(calendar),
        source_mode="synthetic_fixture",
        as_of_session=request.as_of_session,
        decision_cutoff_utc=cutoff,
        valuation_as_of_session=request.as_of_session,
        initial_value_usd="1000.00",
        current_allocation=ForecastAllocation(weights=(), cash_weight="1", upfront_cost_usd="0.00"),
        # Authored cost/target probe, not a recommendation or a claim of investment performance.
        proposed_allocation=ForecastAllocation(
            weights=(
                ForecastWeight(asset_id="SYN:AAA", weight="0.2"),
                ForecastWeight(asset_id="SYN:BBB", weight="0.2"),
            ),
            cash_weight="0.6",
            upfront_cost_usd="1.00",
        ),
    )


def test_actual_supervised_forecasts_are_immutable_reproducible_and_do_not_post_cash(
    database: Engine,
    tmp_path: Path,
) -> None:
    inputs = prepare(database, tmp_path)
    queue, fingerprints = Queue(database), []
    for _ in range(2):
        accepted = admit_forecast(database, tmp_path, inputs)
        queued = read_forecast(database, tmp_path, accepted.forecast_id)
        assert queued is not None and queued.job.status == "queued" and queued.result is None
        assert Worker(queue, artifact_root=tmp_path).run_once()
        actual = read_forecast(database, tmp_path, accepted.forecast_id)
        assert actual is not None and actual.result is not None and actual.job.status == "completed"
        assert actual.result.status == "available" and actual.job.result is not None
        assert actual.job.result.resource_id == accepted.forecast_id
        assert actual.result.hold_unchanged is not None
        assert actual.result.hold_unchanged.median_ending_value_usd == "1000.00"
        assert actual.result.sampled_indices is not None and actual.manifest_sha256 is not None
        fingerprints.append(actual.result.fingerprint)
    assert fingerprints[0] == fingerprints[1]
    with database.connect() as connection:
        assert connection.execute(
            text("SELECT cash_usd,revision,last_sequence FROM paper_portfolio WHERE id=:id"),
            {"id": inputs.portfolio_id},
        ).one() == (1000, 1, 1)
        assert connection.execute(text("SELECT count(*) FROM ledger_event")).scalar_one() == 1
        assert connection.execute(text("SELECT count(*) FROM paper_fill")).scalar_one() == 0
    for table, column in [
        ("forecast", "created_at=created_at"),
        ("forecast_artifact", "manifest_sha256=manifest_sha256"),
    ]:
        for sql in [f"UPDATE {table} SET {column}", f"DELETE FROM {table}"]:
            with pytest.raises(DBAPIError), database.begin() as connection:
                connection.execute(text(sql))


@pytest.mark.parametrize("fence", ["cancel", "expiry"])
def test_cancelled_or_expired_preparation_cannot_register_a_forecast(
    database: Engine,
    tmp_path: Path,
    fence: str,
) -> None:
    inputs = prepare(database, tmp_path)
    accepted = admit_forecast(database, tmp_path, inputs)
    queue = Queue(database)
    lease = queue.claim("forecast-fence")
    assert lease is not None
    stage = tmp_path / "forecast-stage"
    digest = forecast(lease.payload, mp.get_context("spawn").Event(), root=tmp_path, stage=stage)
    if fence == "cancel":
        queue.cancel(accepted.job_id)
        fenced = queue
    else:
        now = queue.clock
        fenced = Queue(database, clock=lambda session: now(session) + timedelta(minutes=10))
    with pytest.raises(PublicationFenceError):
        seal_forecast(fenced, lease, tmp_path, stage, digest)
    actual = read_forecast(database, tmp_path, accepted.forecast_id)
    assert actual is not None and actual.result is None and actual.manifest_sha256 is None
    assert not (tmp_path / "forecasts" / digest).exists()
    with database.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM forecast_artifact")).scalar_one() == 0


def test_unavailable_forecast_is_completed_with_null_outcomes_not_a_failed_or_zero_prediction(
    database: Engine,
    tmp_path: Path,
) -> None:
    inputs = prepare(database, tmp_path).model_copy(update={"initial_value_usd": None})
    accepted = admit_forecast(database, tmp_path, inputs)
    assert Worker(Queue(database), artifact_root=tmp_path).run_once()
    actual = read_forecast(database, tmp_path, accepted.forecast_id)
    assert actual is not None and actual.result is not None and actual.job.status == "completed"
    assert actual.result.status == "unavailable"
    assert actual.result.unavailable_reason == "VALUATION_UNAVAILABLE"
    assert actual.result.proposed is None and actual.result.hold_unchanged is None


def test_old_build_fails_closed_with_safe_reason_without_reinterpreting_inputs(
    database: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = prepare(database, tmp_path)
    with monkeypatch.context() as old:
        old.setattr(service, "engine_fingerprint", lambda: "a" * 64)
        accepted = admit_forecast(database, tmp_path, inputs)
    assert Worker(Queue(database), artifact_root=tmp_path).run_once()
    actual = read_forecast(database, tmp_path, accepted.forecast_id)
    assert actual is not None and actual.result is None and actual.job.status == "failed"
    assert actual.job.error is not None and actual.job.error.details == {
        "reason": "INPUT_FINGERPRINT_MISMATCH"
    }


def test_completion_failure_rolls_back_registration_and_retries_verified_orphan(
    database: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = prepare(database, tmp_path)
    accepted = admit_forecast(database, tmp_path, inputs)
    queue = Queue(database)
    lease = queue.claim("forecast-atomic")
    assert lease is not None
    stage = tmp_path / "first"
    digest = forecast(lease.payload, mp.get_context("spawn").Event(), root=tmp_path, stage=stage)

    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("SYNTHETIC_DATA_ONLY completion-write fault")

    with monkeypatch.context() as fault:
        fault.setattr(queue, "finish_attempt", fail)
        with pytest.raises(RuntimeError, match="completion-write"):
            seal_forecast(queue, lease, tmp_path, stage, digest)
    pending = read_forecast(database, tmp_path, accepted.forecast_id)
    assert pending is not None and pending.job.status == "running" and pending.result is None
    with database.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM forecast_artifact")).scalar_one() == 0
    retry = tmp_path / "retry"
    assert (
        forecast(lease.payload, mp.get_context("spawn").Event(), root=tmp_path, stage=retry)
        == digest
    )
    seal_forecast(queue, lease, tmp_path, retry, digest)
    actual = read_forecast(database, tmp_path, accepted.forecast_id)
    assert actual is not None and actual.result is not None and actual.job.status == "completed"


def test_stale_revision_or_source_context_is_rejected_before_enqueue(
    database: Engine,
    tmp_path: Path,
) -> None:
    inputs = prepare(database, tmp_path)
    mutations: list[dict[str, Any]] = [
        {"portfolio_revision": 2},
        {"source_mode": "research_market_data"},
    ]
    for mutation in mutations:
        with pytest.raises(ValueError, match="CONFLICT|FINGERPRINT"):
            admit_forecast(database, tmp_path, inputs.model_copy(update=mutation))
    with database.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM forecast")).scalar_one() == 0


def test_populated_004_upgrade_retains_accounts_events_and_existing_jobs(
    database: Engine,
    tmp_path: Path,
) -> None:
    prior = tmp_path / "prior"
    shutil.copytree(MIGRATIONS, prior)
    (prior / "versions/0008_recommendations.py").unlink()
    (prior / "versions/0007_forecasts.py").unlink()
    workspace = bootstrap(database, prior)
    owner = uuid4()
    create_portfolio(
        database,
        portfolio_id=owner,
        workspace_id=workspace,
        strategy_version_id=DEFAULT_VERSION_ID,
        name="SYNTHETIC_DATA_ONLY retained account",
        created_at=datetime(2028, 7, 18, 12, 30, tzinfo=UTC),
    )
    job = Queue(database).enqueue("diagnostic", {"schema_version": 1, "work_units": 0}, uuid4())
    assert "forecast" not in inspect(database).get_table_names()
    assert bootstrap(database) == workspace
    with database.connect() as connection:
        assert connection.execute(
            text("SELECT cash_usd,revision,last_sequence FROM paper_portfolio WHERE id=:id"),
            {"id": owner},
        ).one() == (1000, 1, 1)
        assert connection.execute(text("SELECT count(*) FROM ledger_event")).scalar_one() == 1
        assert connection.execute(text("SELECT count(*) FROM forecast")).scalar_one() == 0
    saved = Queue(database).get(job)
    assert saved is not None and saved.status == "queued"


def test_prepare_forecast_restart() -> None:
    base = database_engine(isolated_url())
    name = "test_forecast_restart_" + uuid4().hex[:12]
    with base.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    base.dispose()
    engine = database_engine(
        make_url(isolated_url()).set(database=name).render_as_string(hide_password=False)
    )
    try:
        root = Path("/evidence/forecast-artifacts")
        inputs = prepare(engine, root)
        completed = admit_forecast(engine, root, inputs)
        assert Worker(Queue(engine), artifact_root=root).run_once()
        actual = read_forecast(engine, root, completed.forecast_id)
        assert actual is not None and actual.result is not None
        queued = admit_forecast(engine, root, inputs)
        Path("/evidence/forecasts.json").write_text(
            json.dumps(
                {
                    "database": name,
                    "completed": str(completed.forecast_id),
                    "queued": str(queued.forecast_id),
                    "result": actual.result.model_dump(mode="json"),
                    "manifest_sha256": actual.manifest_sha256,
                    "payload": actual.payload.model_dump(mode="json"),
                }
            )
        )
    finally:
        engine.dispose()


@pytest.mark.restart_verify
def test_forecast_and_queued_inputs_survive_actual_postgres_restart() -> None:
    saved = json.loads(Path("/evidence/forecasts.json").read_text())
    assert saved["database"].startswith("test_forecast_restart_")
    engine = database_engine(
        make_url(isolated_url())
        .set(database=saved["database"])
        .render_as_string(hide_password=False)
    )
    try:
        root = Path("/evidence/forecast-artifacts")
        actual = read_forecast(engine, root, UUID(saved["completed"]))
        assert actual is not None and actual.result is not None and actual.job.status == "completed"
        assert actual.result.model_dump(mode="json") == saved["result"]
        assert actual.payload.model_dump(mode="json") == saved["payload"]
        assert actual.manifest_sha256 == saved["manifest_sha256"]
        pending = read_forecast(engine, root, UUID(saved["queued"]))
        assert pending is not None and pending.job.status == "queued" and pending.result is None
        assert Worker(Queue(engine), artifact_root=root).run_once()
        complete = read_forecast(engine, root, UUID(saved["queued"]))
        assert (
            complete is not None
            and complete.result is not None
            and complete.job.status == "completed"
        )
        assert complete.result.fingerprint == actual.result.fingerprint
    finally:
        engine.dispose()
