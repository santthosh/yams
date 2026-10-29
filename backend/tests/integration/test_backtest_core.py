"""Real PostgreSQL admission, immutable filesystem publication and supervised replay."""

import json
import multiprocessing as mp
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid5

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from backend.backtesting import service
from backend.backtesting.artifacts import read_core
from backend.backtesting.service import admit_core, read_core_run, seal_core
from backend.domain.experiment import ExperimentRequest
from backend.jobs.handlers.backtest import backtest_core
from backend.jobs.queue import Queue
from backend.jobs.worker import Worker
from backend.market_data.snapshots import PublicationFenceError
from backend.persistence.database import database_engine
from backend.strategies.registry import template_strategy_id
from backend.tests.integration.test_bootstrap import database as database
from backend.tests.integration.test_bootstrap import isolated_url
from backend.tests.integration.test_evaluations import prepare as prepare_snapshot

pytestmark = pytest.mark.integration
ORACLE = json.loads(
    (Path(__file__).resolve().parents[3] / "data/fixtures/backtesting/core-case.json").read_text()
)


def prepare(database: Engine, root: Path) -> ExperimentRequest:
    evaluation = prepare_snapshot(database, root)
    return ExperimentRequest.model_validate(
        dict(
            strategy_version_id=uuid5(template_strategy_id("mean_reversion"), "1"),
            snapshot_id=evaluation.snapshot_id,
            start_session="2028-07-18",
            end_session_exclusive="2028-07-24",
            initial_capital_usd="1000.00",
            benchmark_asset_id="SYN:SPY",
            execution_policy_id="us_eod_next_open_v1",
            random_seed=42,
            evaluation_split={"kind": "chronological", "holdout_fraction": 0.25},
        )
    )


def test_atomic_admission_sealing_replay_and_immutable_rows(
    database: Engine, tmp_path: Path
) -> None:
    request = prepare(database, tmp_path)
    queue = Queue(database)
    digests = []
    for index in range(2):
        accepted = admit_core(database, tmp_path, request)
        queued = read_core_run(database, tmp_path, accepted.experiment_id)
        assert queued is not None and queued.job.status == "queued" and queued.result is None
        lease = queue.claim("core-test")
        assert lease is not None and lease.job_id == accepted.job_id
        stage = tmp_path / f"core-stage-{index}"
        digest = backtest_core(
            lease.payload, mp.get_context("spawn").Event(), root=tmp_path, stage=stage
        )
        seal_core(queue, lease, tmp_path, stage, digest)
        actual = read_core_run(database, tmp_path, accepted.experiment_id)
        assert actual is not None and actual.job.status == "completed" and actual.result is not None
        assert actual.job.progress == 100 and actual.job.result is not None
        assert actual.job.result.resource_id == accepted.experiment_id
        assert [row.nav_usd for row in actual.result.points] == ORACLE["daily_nav_usd"]
        assert actual.result.points[1].state.cash_usd == "392.84"
        digests.append(actual.manifest_sha256)
    assert digests[0] == digests[1]
    for table, column in [
        ("experiment", "created_at=created_at"),
        ("experiment_core", "manifest_sha256=manifest_sha256"),
    ]:
        for statement in [f"UPDATE {table} SET {column}", f"DELETE FROM {table}"]:
            with pytest.raises(DBAPIError), database.begin() as connection:
                connection.execute(text(statement))


@pytest.mark.parametrize("fence", ["cancel", "expiry"])
def test_cancelled_or_expired_attempt_never_publishes(
    database: Engine, tmp_path: Path, fence: str
) -> None:
    request = prepare(database, tmp_path)
    accepted = admit_core(database, tmp_path, request)
    queue = Queue(database)
    lease = queue.claim("fence-test")
    assert lease is not None
    stage = tmp_path / "core-stage"
    digest = backtest_core(
        lease.payload, mp.get_context("spawn").Event(), root=tmp_path, stage=stage
    )
    if fence == "cancel":
        queue.cancel(accepted.job_id)
        fenced = queue
    else:
        fenced = Queue(database, clock=lambda session: queue.clock(session) + timedelta(seconds=31))
    with pytest.raises(PublicationFenceError):
        seal_core(fenced, lease, tmp_path, stage, digest)
    actual = read_core_run(database, tmp_path, accepted.experiment_id)
    assert actual is not None and actual.result is None and actual.job.status != "completed"
    assert not (tmp_path / "experiments" / digest).exists()
    if fence == "cancel":
        assert queue.acknowledge_cancel(lease)
        cancelled_job = queue.get(accepted.job_id)
        assert cancelled_job is not None and cancelled_job.status == "cancelled"


def test_post_rename_crash_rolls_back_and_recomputed_retry_reuses_verified_orphan(
    database: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = prepare(database, tmp_path)
    accepted = admit_core(database, tmp_path, request)
    queue = Queue(database)
    lease = queue.claim("orphan-test")
    assert lease is not None
    stage = tmp_path / "core-stage"
    digest = backtest_core(
        lease.payload, mp.get_context("spawn").Event(), root=tmp_path, stage=stage
    )

    def crash(*args: object, **kwargs: object) -> None:
        raise RuntimeError("injected completion crash")

    with monkeypatch.context() as fault:
        fault.setattr(queue, "finish_attempt", crash)
        with pytest.raises(RuntimeError, match="injected"):
            seal_core(queue, lease, tmp_path, stage, digest)
    actual = read_core_run(database, tmp_path, accepted.experiment_id)
    assert actual is not None and actual.job.status == "running" and actual.result is None
    assert not stage.exists()
    assert read_core(tmp_path / "experiments" / digest, digest).points[0].nav_usd == "1000.00"
    retry = tmp_path / "recomputed-stage"
    assert (
        backtest_core(lease.payload, mp.get_context("spawn").Event(), root=tmp_path, stage=retry)
        == digest
    )
    seal_core(queue, lease, tmp_path, retry, digest)
    actual = read_core_run(database, tmp_path, accepted.experiment_id)
    assert (
        actual is not None and actual.job.status == "completed" and actual.manifest_sha256 == digest
    )


def test_failed_or_partial_core_cannot_complete_and_failure_reason_is_safe(
    database: Engine, tmp_path: Path
) -> None:
    request = prepare(database, tmp_path)
    accepted = admit_core(database, tmp_path, request)
    queue = Queue(database)
    lease = queue.claim("partial-test")
    assert lease is not None
    stage = tmp_path / "core-stage"
    digest = backtest_core(
        lease.payload, mp.get_context("spawn").Event(), root=tmp_path, stage=stage
    )
    from backend.backtesting.artifacts import stage_core

    result = read_core(stage, digest)
    partial_stage = tmp_path / "partial-stage"
    partial_hash = stage_core(
        partial_stage, result.model_copy(update={"points": result.points[:-1]})
    )
    with pytest.raises(ValueError, match="complete input window"):
        seal_core(queue, lease, tmp_path, partial_stage, partial_hash)
    with pytest.raises(ValueError, match="failure reason"):
        queue.fail(lease, "VALIDATION_ERROR", reason="arbitrary untrusted text")
    assert queue.fail(lease, "VALIDATION_ERROR", reason="MISSING_ELIGIBLE_OPEN")
    actual = read_core_run(database, tmp_path, accepted.experiment_id)
    assert actual is not None and actual.job.status == "failed" and actual.result is None
    assert actual.job.error is not None and actual.job.error.details == {
        "reason": "MISSING_ELIGIBLE_OPEN"
    }
    assert not (tmp_path / "experiments" / partial_hash).exists()


def test_real_supervised_core_handler_and_rerun(database: Engine, tmp_path: Path) -> None:
    request = prepare(database, tmp_path)
    queue = Queue(database)
    digests = []
    for _ in range(2):
        accepted = admit_core(database, tmp_path, request)
        assert Worker(queue, artifact_root=tmp_path).run_once()
        actual = read_core_run(database, tmp_path, accepted.experiment_id)
        assert actual is not None and actual.result is not None and actual.job.status == "completed"
        assert [row.nav_usd for row in actual.result.points] == ORACLE["daily_nav_usd"]
        digests.append(actual.manifest_sha256)
    assert digests[0] == digests[1]


def test_old_queued_build_fails_without_reinterpreting_inputs(
    database: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = prepare(database, tmp_path)
    with monkeypatch.context() as old:
        old.setattr(service, "engine_fingerprint", lambda: "a" * 64)
        accepted = admit_core(database, tmp_path, request)
    assert Worker(Queue(database), artifact_root=tmp_path).run_once()
    actual = read_core_run(database, tmp_path, accepted.experiment_id)
    assert actual is not None and actual.job.status == "failed" and actual.result is None
    assert actual.job.error is not None and actual.job.error.details == {
        "reason": "INPUT_FINGERPRINT_MISMATCH"
    }


def test_prepare_core_restart() -> None:
    engine = database_engine(isolated_url())
    try:
        root = Path("/evidence/core-artifacts")
        request = prepare(engine, root)
        accepted = admit_core(engine, root, request)
        assert Worker(Queue(engine), artifact_root=root).run_once()
        actual = read_core_run(engine, root, accepted.experiment_id)
        assert actual is not None and actual.result is not None
        Path("/evidence/backtest-core.json").write_text(
            json.dumps(
                dict(
                    id=str(actual.id),
                    manifest_sha256=actual.manifest_sha256,
                    result=actual.result.model_dump(mode="json"),
                    payload=actual.payload.model_dump(mode="json"),
                )
            )
        )
    finally:
        engine.dispose()


@pytest.mark.restart_verify
def test_core_and_inputs_survive_postgres_restart() -> None:
    saved = json.loads(Path("/evidence/backtest-core.json").read_text())
    engine = database_engine(isolated_url())
    try:
        actual = read_core_run(engine, Path("/evidence/core-artifacts"), UUID(saved["id"]))
        assert actual is not None and actual.result is not None and actual.job.status == "completed"
        assert actual.manifest_sha256 == saved["manifest_sha256"]
        assert actual.result.model_dump(mode="json") == saved["result"]
        assert actual.payload.model_dump(mode="json") == saved["payload"]
    finally:
        engine.dispose()


def test_running_core_cancellation_never_registers_a_result(
    database: Engine, tmp_path: Path
) -> None:
    import time
    from concurrent.futures import ThreadPoolExecutor

    request = prepare(database, tmp_path)
    accepted = admit_core(database, tmp_path, request)
    queue = Queue(database)
    with ThreadPoolExecutor(max_workers=1) as executor:
        running = executor.submit(Worker(queue, artifact_root=tmp_path).run_once)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            current = queue.get(accepted.job_id)
            assert current is not None
            if current.status == "running":
                break
            assert current.status != "completed"
            time.sleep(0.01)
        else:
            pytest.fail("Backtest worker did not claim its job")
        cancelled = queue.cancel(accepted.job_id)
        assert cancelled is not None and cancelled.status == "cancel_requested"
        assert running.result(timeout=10)
    actual = read_core_run(database, tmp_path, accepted.experiment_id)
    assert actual is not None and actual.job.status == "cancelled" and actual.result is None
    with database.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM experiment_core")).scalar_one() == 0


def test_abandoned_attempt_recovers_and_stale_token_cannot_publish(
    database: Engine, tmp_path: Path
) -> None:
    request = prepare(database, tmp_path)
    accepted = admit_core(database, tmp_path, request)
    original = Queue(database)
    stale = original.claim("abandoned-core")
    assert stale is not None
    stage = tmp_path / "abandoned-stage"
    digest = backtest_core(
        stale.payload, mp.get_context("spawn").Event(), root=tmp_path, stage=stage
    )
    offset = timedelta(seconds=31)
    recovered = Queue(database, clock=lambda session: original.clock(session) + offset)
    assert recovered.recover() == 1
    offset = timedelta(seconds=34)
    assert Worker(recovered, artifact_root=tmp_path).run_once()
    actual = read_core_run(database, tmp_path, accepted.experiment_id)
    assert actual is not None and actual.result is not None and actual.job.attempts == 2
    assert actual.manifest_sha256 == digest
    with pytest.raises(PublicationFenceError):
        seal_core(recovered, stale, tmp_path, stage, digest)


def test_populated_prior_schema_upgrade_preserves_workspace_versions_and_jobs(
    database: Engine, tmp_path: Path
) -> None:
    import shutil

    from sqlalchemy import inspect

    from backend.persistence.bootstrap import MIGRATIONS, bootstrap
    from backend.persistence.readiness import read_workspace
    from backend.strategies.registry import DEFAULT_STRATEGY_ID, list_versions

    prior = tmp_path / "prior-migrations"
    shutil.copytree(MIGRATIONS, prior)
    (prior / "versions/0009_portfolio_reviews.py").unlink()
    (prior / "versions/0008_recommendations.py").unlink()
    (prior / "versions/0007_forecasts.py").unlink()
    (prior / "versions/0006_paper_ledger.py").unlink()
    (prior / "versions/0005a_experiment_reports.py").unlink()
    (prior / "versions/0005_experiments.py").unlink()
    identity = bootstrap(database, prior)
    assert "experiment" not in inspect(database).get_table_names()
    versions = list_versions(database, DEFAULT_STRATEGY_ID)
    queue = Queue(database)
    from uuid import uuid4

    job_id = queue.enqueue("diagnostic", {"schema_version": 1, "work_units": 10}, uuid4())
    with database.begin() as connection:
        connection.execute(
            text("UPDATE local_workspace SET preferences = CAST(:preferences AS jsonb)"),
            {"preferences": json.dumps({"retained": True})},
        )
    assert bootstrap(database) == identity
    assert {"experiment", "experiment_core"} <= set(inspect(database).get_table_names())
    assert list_versions(database, DEFAULT_STRATEGY_ID) == versions
    assert read_workspace(database).preferences == {"retained": True}
    job = queue.get(job_id)
    assert job is not None and job.status == "queued"


def test_reader_serializes_status_and_artifact_with_completion(
    database: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    request = prepare(database, tmp_path)
    accepted = admit_core(database, tmp_path, request)
    queue = Queue(database)
    lease = queue.claim("read-fence-test")
    assert lease is not None
    stage = tmp_path / "core-stage"
    digest = backtest_core(
        lease.payload, mp.get_context("spawn").Event(), root=tmp_path, stage=stage
    )
    committing, release = Event(), Event()
    finish = queue.finish_attempt

    def pause_commit(*args: object, **kwargs: object) -> None:
        committing.set()
        assert release.wait(5), "Completion transaction was not released"
        finish(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(queue, "finish_attempt", pause_commit)
    with ThreadPoolExecutor(max_workers=2) as executor:
        writer = executor.submit(seal_core, queue, lease, tmp_path, stage, digest)
        try:
            assert committing.wait(5)
            reader = executor.submit(read_core_run, database, tmp_path, accepted.experiment_id)
            with pytest.raises(TimeoutError):
                reader.result(timeout=0.2)
        finally:
            release.set()
        writer.result(timeout=10)
        actual = reader.result(timeout=10)
    assert actual is not None and actual.result is not None and actual.job.status == "completed"
    assert actual.manifest_sha256 == digest
