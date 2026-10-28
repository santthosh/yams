"""Public API through real PostgreSQL, worker, lease fencing and immutable artifacts."""

import json
import multiprocessing as mp
import shutil
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from backend.api.main import create_app
from backend.backtesting.publication import seal_report
from backend.backtesting.queries import detail
from backend.backtesting.service import admit_experiment
from backend.jobs.handlers.backtest import backtest
from backend.jobs.queue import Queue
from backend.jobs.worker import Worker
from backend.market_data.snapshots import PublicationFenceError
from backend.persistence.bootstrap import MIGRATIONS, bootstrap
from backend.persistence.database import Settings, database_engine
from backend.tests.integration.test_backtest_core import ORACLE, prepare
from backend.tests.integration.test_bootstrap import database as database
from backend.tests.integration.test_bootstrap import isolated_url

pytestmark = pytest.mark.integration


def client_for(database: Engine, root: Path) -> TestClient:
    return TestClient(
        create_app(Settings(database.url.render_as_string(hide_password=False), artifact_root=root))
    )


def test_create_run_pages_rerun_and_immutable_report(database: Engine, tmp_path: Path) -> None:
    request = prepare(database, tmp_path)
    hashes = []
    identities = []
    with client_for(database, tmp_path) as client:
        for _ in range(2):
            accepted = client.post("/api/v1/experiments", json=request.model_dump(mode="json"))
            assert accepted.status_code == 202, accepted.text
            identity = accepted.json()["experiment_id"]
            identities.append(identity)
            url = f"/api/v1/experiments/{identity}"
            queued = client.get(url).json()
            assert (
                queued["status"] == "queued"
                and queued["metrics"] is None
                and queued["report"] is None
            )
            assert client.get(url + "/series").status_code == 409
            assert Worker(Queue(database), artifact_root=tmp_path).run_once()
            response = client.get(url)
            assert response.status_code == 200, response.text
            run = response.json()
            assert run["status"] == "completed" and run["report"] is not None
            assert run["metrics"]["trade_count"] == 3
            assert (
                run["data_status"] == "synthetic_fixture"
                and "SYNTHETIC_DATA_ONLY" in run["warnings"]
            )
            assert run["reproducibility_manifest"]["schema_version"] == 1
            hashes.append(
                [
                    run[key]["sha256"]
                    for key in ("curve_artifact", "trade_artifact", "reproducibility_manifest")
                ]
            )
            points = []
            cursor = None
            while True:
                page = client.get(
                    url + "/series", params={"limit": 2, **({"cursor": cursor} if cursor else {})}
                )
                assert page.status_code == 200, page.text
                points.extend(page.json()["items"])
                cursor = page.json()["next_cursor"]
                if cursor is None:
                    break
                assert (
                    client.get(url + "/trades", params={"limit": 2, "cursor": cursor}).status_code
                    == 422
                )
                assert (
                    client.get(url + "/series", params={"limit": 3, "cursor": cursor}).status_code
                    == 422
                )
            assert [row["portfolio_nav_usd"] for row in points] == ORACLE["daily_nav_usd"]
            assert all(isinstance(row["cash_weight"]["value"], str) for row in points)
            assert len(client.get(url + "/trades").json()["items"]) == 3
            window = client.get(
                url + "/series",
                params={"start_session": "2028-07-20", "end_session_exclusive": "2028-07-21"},
            )
            assert [p["session_date"] for p in window.json()["items"]] == ["2028-07-20"]
            assert (
                client.get(url + "/series", params={"start_session": "2028-07-22"}).json()["items"]
                == []
            )
            assert (
                client.post(f"/api/v1/jobs/{accepted.json()['job_id']}/cancel", json={}).status_code
                == 409
            )
        assert identities[0] != identities[1] and hashes[0] == hashes[1]
        history = client.get("/api/v1/experiments", params={"limit": 1}).json()
        assert history["items"][0]["id"] == identities[-1]
        second = client.get(
            "/api/v1/experiments", params={"limit": 1, "cursor": history["next_cursor"]}
        ).json()
        assert second["items"][0]["id"] == identities[0] and second["next_cursor"] is None
    for statement in [
        "UPDATE experiment_report SET manifest_sha256=manifest_sha256",
        "DELETE FROM experiment_report",
    ]:
        with pytest.raises(DBAPIError), database.begin() as connection:
            connection.execute(text(statement))


def test_cancel_queued_running_and_terminal_under_public_contract(
    database: Engine, tmp_path: Path
) -> None:
    request = prepare(database, tmp_path)
    with client_for(database, tmp_path) as client:
        queued = admit_experiment(database, tmp_path, request)
        cancel = f"/api/v1/jobs/{queued.job_id}/cancel"
        assert client.post(cancel, json={"arbitrary": True}).status_code == 422
        assert client.post(cancel, json={}).status_code == 202
        assert client.post(cancel, json={}).status_code == 409
        current = detail(database, tmp_path, queued.experiment_id)
        assert current is not None and current.status == "cancelled"
        running = admit_experiment(database, tmp_path, request)
        queue = Queue(database)
        lease = queue.claim("cancel-test")
        assert lease is not None
        cancel = f"/api/v1/jobs/{running.job_id}/cancel"
        assert client.post(cancel, json={}).json()["status"] == "cancel_requested"
        assert client.post(cancel, json={}).status_code == 202
        assert queue.acknowledge_cancel(lease)
        assert client.post(cancel, json={}).status_code == 409
        assert client.post(f"/api/v1/jobs/{uuid4()}/cancel", json={}).status_code == 404


@pytest.mark.parametrize("fence", ["cancel", "expiry", "late_expiry"])
def test_full_report_cannot_publish_after_fence(
    database: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fence: str
) -> None:
    request = prepare(database, tmp_path)
    accepted = admit_experiment(database, tmp_path, request)
    queue = Queue(database)
    lease = queue.claim("report-fence")
    assert lease is not None
    stage = tmp_path / "report-stage"
    digest = backtest(lease.payload, mp.get_context("spawn").Event(), root=tmp_path, stage=stage)
    fenced = queue
    if fence == "cancel":
        queue.cancel(accepted.job_id)
    elif fence == "expiry":
        fenced = Queue(database, clock=lambda session: queue.clock(session) + timedelta(seconds=31))
    else:
        # Inject expiry at the second owned() check, after filesystem publication.
        owned = queue.owned
        calls = 0

        def late(session, active):  # type: ignore[no-untyped-def]
            nonlocal calls
            row, now = owned(session, active)
            calls += 1
            return row, now + timedelta(seconds=301) if calls > 1 else now

        monkeypatch.setattr(queue, "owned", late)
    with pytest.raises(PublicationFenceError):
        seal_report(fenced, lease, tmp_path, stage, digest)
    current = detail(database, tmp_path, accepted.experiment_id)
    assert current is not None and current.status != "completed" and current.report is None
    with database.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM experiment_report")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM experiment_core")).scalar_one() == 0


def test_post_publication_crash_recomputed_orphan_and_tamper(
    database: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = prepare(database, tmp_path)
    accepted = admit_experiment(database, tmp_path, request)
    queue = Queue(database)
    lease = queue.claim("report-crash")
    assert lease is not None
    stage = tmp_path / "stage-report"
    digest = backtest(lease.payload, mp.get_context("spawn").Event(), root=tmp_path, stage=stage)

    def crash(*args: object, **kwargs: object) -> None:
        raise RuntimeError("Injected report commit crash")

    with monkeypatch.context() as fault:
        fault.setattr(queue, "finish_attempt", crash)
        with pytest.raises(RuntimeError, match="Injected"):
            seal_report(queue, lease, tmp_path, stage, digest)
    current = detail(database, tmp_path, accepted.experiment_id)
    assert current is not None and current.report is None
    retry = tmp_path / "retry-report"
    assert (
        backtest(lease.payload, mp.get_context("spawn").Event(), root=tmp_path, stage=retry)
        == digest
    )
    seal_report(queue, lease, tmp_path, retry, digest)
    with client_for(database, tmp_path) as client:
        url = f"/api/v1/experiments/{accepted.experiment_id}"
        assert client.get(url).json()["status"] == "completed"
        target = tmp_path / "experiment-reports" / digest / "series.jsonl"
        target.write_bytes(target.read_bytes().replace(b"1000.00", b"1001.00", 1))
        response = client.get(url + "/series")
        assert response.status_code == 503 and response.json()["error"]["code"] == "NOT_READY"
        assert "series.jsonl" not in response.text


def test_public_negative_inputs_and_safe_errors(database: Engine, tmp_path: Path) -> None:
    request = prepare(database, tmp_path)
    with client_for(database, tmp_path) as client:
        unknown = client.post(
            "/api/v1/experiments",
            json=request.model_dump(mode="json") | {"snapshot_id": str(uuid4())},
        )
        assert unknown.status_code == 404
        invalid = client.post(
            "/api/v1/experiments",
            json=request.model_dump(mode="json") | {"start_session": "2028-07-25"},
        )
        assert invalid.status_code == 422
        empty_window = client.post(
            "/api/v1/experiments",
            json=request.model_dump(mode="json")
            | {
                "start_session": "2028-07-22",
                "end_session_exclusive": "2028-07-24",
            },
        )
        assert empty_window.status_code == 422
        accepted = admit_experiment(database, tmp_path, request)
        assert Worker(Queue(database), artifact_root=tmp_path).run_once()
        url = f"/api/v1/experiments/{accepted.experiment_id}/series"
        for params in (
            {"limit": 101},
            {"cursor": "../../etc/passwd"},
            {"start_session": "2028-07-17"},
            {"end_session_exclusive": "2028-07-19", "start_session": "2028-07-20"},
        ):
            assert client.get(url, params=params).status_code == 422
        assert client.get(f"/api/v1/experiments/{uuid4()}").status_code == 404
        assert client.get("/api/v1/experiments/not-a-uuid").status_code == 422


def test_populated_core_schema_upgrade_retains_admission(database: Engine, tmp_path: Path) -> None:
    prior = tmp_path / "prior-migrations"
    shutil.copytree(MIGRATIONS, prior)
    (prior / "versions/0006_paper_ledger.py").unlink()
    (prior / "versions/0005a_experiment_reports.py").unlink()
    workspace = bootstrap(database, prior)
    queue = Queue(database)
    job = queue.enqueue("diagnostic", {"schema_version": 1, "work_units": 10}, uuid4())
    assert bootstrap(database) == workspace
    current_job = queue.get(job)
    assert current_job is not None and current_job.status == "queued"


def test_prepare_public_report_restart() -> None:
    engine = database_engine(isolated_url())
    try:
        root = Path("/evidence/public-report-artifacts")
        request = prepare(engine, root)
        accepted = admit_experiment(engine, root, request)
        assert Worker(Queue(engine), artifact_root=root).run_once()
        actual = detail(engine, root, accepted.experiment_id)
        assert actual is not None and actual.status == "completed"
        Path("/evidence/public-report.json").write_text(actual.model_dump_json())
    finally:
        engine.dispose()


@pytest.mark.restart_verify
def test_public_report_survives_postgres_restart() -> None:
    saved = json.loads(Path("/evidence/public-report.json").read_text())
    engine = database_engine(isolated_url())
    try:
        actual = detail(engine, Path("/evidence/public-report-artifacts"), UUID(saved["id"]))
        assert actual is not None and actual.model_dump(mode="json") == saved
    finally:
        engine.dispose()


def test_completion_serializes_public_read_and_late_cancel(
    database: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    request = prepare(database, tmp_path)
    accepted = admit_experiment(database, tmp_path, request)
    queue = Queue(database)
    lease = queue.claim("report-row-lock")
    assert lease is not None
    stage = tmp_path / "locked-report"
    digest = backtest(lease.payload, mp.get_context("spawn").Event(), root=tmp_path, stage=stage)
    committing, release = Event(), Event()
    finish = queue.finish_attempt

    def pause(*args: object, **kwargs: object) -> None:
        committing.set()
        assert release.wait(5)
        finish(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(queue, "finish_attempt", pause)
    with client_for(database, tmp_path) as client, ThreadPoolExecutor(max_workers=3) as executor:
        writer = executor.submit(seal_report, queue, lease, tmp_path, stage, digest)
        try:
            assert committing.wait(5)
            read = executor.submit(client.get, f"/api/v1/experiments/{accepted.experiment_id}")
            cancel = executor.submit(client.post, f"/api/v1/jobs/{accepted.job_id}/cancel", json={})
            with pytest.raises(TimeoutError):
                read.result(timeout=0.1)
            with pytest.raises(TimeoutError):
                cancel.result(timeout=0.1)
        finally:
            release.set()
        writer.result(timeout=10)
        assert read.result(timeout=10).json()["status"] == "completed"
        assert cancel.result(timeout=10).status_code == 409


def test_live_full_worker_cancellation_and_failed_report_remain_unsealed(
    database: Engine,
    tmp_path: Path,
) -> None:
    import time
    from concurrent.futures import ThreadPoolExecutor

    request = prepare(database, tmp_path)
    queue = Queue(database)
    accepted = admit_experiment(database, tmp_path, request)
    with client_for(database, tmp_path) as client, ThreadPoolExecutor(max_workers=1) as executor:
        worker = executor.submit(Worker(queue, artifact_root=tmp_path).run_once)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            current = queue.get(accepted.job_id)
            assert current is not None and current.status != "completed"
            if current.status == "running":
                break
            time.sleep(0.01)
        else:
            pytest.fail("Public backtest was not claimed")
        response = client.post(f"/api/v1/jobs/{accepted.job_id}/cancel", json={})
        assert response.status_code == 202 and response.json()["status"] == "cancel_requested"
        assert worker.result(timeout=10)
        current_run = detail(database, tmp_path, accepted.experiment_id)
        assert (
            current_run is not None
            and current_run.status == "cancelled"
            and current_run.report is None
        )
        failed = admit_experiment(database, tmp_path, request)
        lease = queue.claim("failed-public-report")
        assert lease is not None
        assert queue.fail(lease, "VALIDATION_ERROR", reason="MISSING_ELIGIBLE_OPEN")
        failed_run = detail(database, tmp_path, failed.experiment_id)
        assert (
            failed_run is not None and failed_run.status == "failed" and failed_run.report is None
        )
        assert failed_run.error is not None and failed_run.error.details == {
            "reason": "MISSING_ELIGIBLE_OPEN"
        }
        assert client.get(f"/api/v1/experiments/{failed.experiment_id}/series").status_code == 409


def test_exact_uint64_canonical_rerun_and_unmodified_sealed_artifacts(
    database: Engine,
    tmp_path: Path,
) -> None:
    request = prepare(database, tmp_path).model_copy(update={"random_seed": 18446744073709551615})
    refs = []
    ids = []
    with client_for(database, tmp_path) as client:
        content = request.model_dump_json()
        for _ in range(2):
            created = client.post(
                "/api/v1/experiments", content=content, headers={"content-type": "application/json"}
            )
            assert created.status_code == 202
            identity = created.json()["experiment_id"]
            ids.append(identity)
            assert Worker(Queue(database), artifact_root=tmp_path).run_once()
            run = client.get(f"/api/v1/experiments/{identity}")
            assert run.status_code == 200
            value = run.json()
            assert value["status"] == "completed"
            assert value["inputs"]["random_seed"] == 18446744073709551615
            content = value["inputs_canonical_json"]
            assert '"random_seed":18446744073709551615' in content
            refs.append(
                [value[k] for k in ("curve_artifact", "trade_artifact", "reproducibility_manifest")]
            )
        assert ids[0] != ids[1] and refs[0] == refs[1]
        # Detail is a projection of existing immutable payload metadata; it does
        # not add fields to or rewrite already sealed report artifacts.
        before = {
            p.relative_to(tmp_path): p.read_bytes()
            for p in (tmp_path / "experiment-reports").rglob("*")
            if p.is_file()
        }
        assert (
            client.get(f"/api/v1/experiments/{ids[0]}").json()["inputs_canonical_json"] == content
        )
        assert before == {
            p.relative_to(tmp_path): p.read_bytes()
            for p in (tmp_path / "experiment-reports").rglob("*")
            if p.is_file()
        }
