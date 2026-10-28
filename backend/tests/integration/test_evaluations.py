"""Real diagnostic transaction proofs with an EXPLICIT synthetic test cutoff.

These tests do not ratify a staggered-arrival policy or claim supervised handler
coverage before that policy/handler is implemented.
"""

import json
import shutil
from datetime import date, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import DBAPIError

from backend.api.main import create_app
from backend.domain.evaluation import StrategyEvaluationRequest
from backend.jobs.queue import Queue
from backend.market_data.snapshots import PublicationFenceError, publish_snapshot
from backend.persistence.bootstrap import bootstrap
from backend.persistence.database import Settings, database_engine
from backend.strategies.evaluations import admit_evaluation, read_evaluation, seal_evaluation
from backend.strategies.registry import DEFAULT_VERSION_ID
from backend.tests.integration.test_bootstrap import database as database
from backend.tests.integration.test_bootstrap import isolated_url
from backend.tests.market_data.test_files import FIXTURES, IDENTITY
from backend.tests.strategies.test_evaluation_contracts import explicit_fixture_result

pytestmark = pytest.mark.integration


def prepare(database: Engine, root: Path) -> StrategyEvaluationRequest:
    bootstrap(database)
    stage = root / "stage"
    shutil.copytree(FIXTURES / "snapshot", stage)
    store = root / "snapshots"
    store.mkdir(parents=True, exist_ok=True)
    queue = Queue(database)
    queue.enqueue(
        "refresh_market_data",
        dict(schema_version=1, source_mode="synthetic_fixture", expected_manifest_hash=IDENTITY),
        uuid4(),
    )
    lease = queue.claim("snapshot-test")
    assert lease is not None
    identity = publish_snapshot(queue, lease, stage, store, IDENTITY)
    return StrategyEvaluationRequest(
        strategy_version_id=DEFAULT_VERSION_ID,
        snapshot_id=identity,
        as_of_session=date(2028, 7, 17),
    )


def test_admission_completion_replay_and_immutable_evidence(
    database: Engine, tmp_path: Path
) -> None:
    request = prepare(database, tmp_path)
    settings = Settings(database.url.render_as_string(hide_password=False), artifact_root=tmp_path)
    _, expected = explicit_fixture_result(tmp_path / "explicit")
    hashes = []
    with TestClient(create_app(settings)) as client:
        for _ in range(2):
            response = client.post(
                "/api/v1/strategy-evaluations", json=request.model_dump(mode="json")
            )
            assert response.status_code == 202
            identity = UUID(response.json()["evaluation_id"])
            queued = client.get(f"/api/v1/strategy-evaluations/{identity}")
            assert queued.status_code == 200 and queued.json()["status"] == "queued"
            assert queued.json()["result"] is None and queued.json()["result_sha256"] is None
            queue = Queue(database)
            lease = queue.claim("explicit-cutoff-test")
            assert lease is not None and str(lease.job_id) == response.json()["job_id"]
            seal_evaluation(queue, lease, expected.model_dump_json())
            completed = client.get(f"/api/v1/strategy-evaluations/{identity}")
            assert completed.status_code == 200 and completed.json()["status"] == "completed"
            assert completed.json()["result"] == expected.model_dump(mode="json")
            assert completed.json()["strategy_config"]["portfolio"]["max_position_weight"] == "0.2"
            hashes.append(completed.json()["result_sha256"])
        assert hashes == [expected.result_hash(), expected.result_hash()]
        assert client.get(f"/api/v1/strategy-evaluations/{uuid4()}").status_code == 404
        unknown = request.model_dump(mode="json") | {"strategy_version_id": str(uuid4())}
        assert client.post("/api/v1/strategy-evaluations", json=unknown).status_code == 404
        weekend = request.model_dump(mode="json") | {"as_of_session": "2028-07-16"}
        assert client.post("/api/v1/strategy-evaluations", json=weekend).status_code == 422
    for table in ("strategy_evaluation", "strategy_evaluation_result"):
        for verb in (
            f"UPDATE {table} SET "
            + ("engine_version='0'" if table.endswith("evaluation") else "sha256='0'"),
            f"DELETE FROM {table}",
        ):
            with pytest.raises(DBAPIError), database.begin() as connection:
                connection.execute(text(verb))
    assert not {
        "portfolio",
        "paper_portfolio",
        "paper_order",
        "cash_entry",
        "recommendation",
        "forecast",
    } & set(inspect(database).get_table_names())
    with database.connect() as connection:
        assert (
            connection.execute(text("SELECT count(*) FROM job_diagnostic_effect")).scalar_one() == 0
        )


@pytest.mark.parametrize("condition", ["cancel", "expired"])
def test_cancelled_or_expired_attempt_cannot_publish(
    database: Engine, tmp_path: Path, condition: str
) -> None:
    request = prepare(database, tmp_path)
    accepted = admit_evaluation(database, tmp_path, request)
    queue = Queue(database)
    lease = queue.claim("fenced-test")
    assert lease is not None
    _, expected = explicit_fixture_result(tmp_path / "explicit")
    if condition == "cancel":
        queue.cancel(lease.job_id)
        fenced = queue
    else:
        fenced = Queue(database, clock=lambda session: queue.clock(session) + timedelta(seconds=31))
    with pytest.raises(PublicationFenceError):
        seal_evaluation(fenced, lease, expected.model_dump_json())
    current = read_evaluation(database, accepted.evaluation_id)
    assert current is not None and current.result is None and current.status != "completed"


def test_publication_fault_rolls_back_and_bad_lineage_cannot_seal(
    database: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = prepare(database, tmp_path)
    accepted = admit_evaluation(database, tmp_path, request)
    queue = Queue(database)
    lease = queue.claim("atomic-test")
    assert lease is not None
    _, expected = explicit_fixture_result(tmp_path / "explicit")
    wrong = expected.model_copy(
        update={
            "reproducibility": expected.reproducibility.model_copy(update={"snapshot_id": uuid4()})
        }
    )
    with pytest.raises(ValueError, match="lineage"):
        seal_evaluation(queue, lease, wrong.model_dump_json())

    def crash(*args: object, **kwargs: object) -> None:
        raise RuntimeError("injected diagnostic completion fault")

    monkeypatch.setattr(queue, "finish_attempt", crash)
    with pytest.raises(RuntimeError, match="injected"):
        seal_evaluation(queue, lease, expected.model_dump_json())
    current = read_evaluation(database, accepted.evaluation_id)
    assert current is not None and current.status == "running" and current.result is None
    with database.connect() as connection:
        assert (
            connection.execute(text("SELECT count(*) FROM strategy_evaluation_result")).scalar_one()
            == 0
        )


def test_prepare_evaluation_restart() -> None:
    engine = database_engine(isolated_url())
    try:
        root = Path("/evidence/evaluation-artifacts")
        request = prepare(engine, root)
        accepted = admit_evaluation(engine, root, request)
        queue = Queue(engine)
        lease = queue.claim("evaluation-restart")
        assert lease is not None
        _, expected = explicit_fixture_result(root / "explicit")
        seal_evaluation(queue, lease, expected.model_dump_json())
        saved = read_evaluation(engine, accepted.evaluation_id)
        assert saved is not None
        Path("/evidence/evaluation.json").write_text(saved.model_dump_json())
    finally:
        engine.dispose()


@pytest.mark.restart_verify
def test_completed_evaluation_survives_postgres_restart() -> None:
    saved = json.loads(Path("/evidence/evaluation.json").read_text())
    engine = database_engine(isolated_url())
    try:
        actual = read_evaluation(engine, UUID(saved["id"]))
        assert actual is not None and actual.status == "completed"
        assert actual.model_dump(mode="json") == saved
    finally:
        engine.dispose()
