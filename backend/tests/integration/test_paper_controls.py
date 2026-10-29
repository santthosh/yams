"""Public controls over genuine computed synthetic decisions and the actual worker."""

import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from backend.api.main import create_app
from backend.jobs.queue import Queue
from backend.jobs.worker import Worker
from backend.persistence.database import Settings
from backend.persistence.models.ledger import RecommendationReference
from backend.portfolio.ledger import digest
from backend.portfolio.paper_controls import apply_recommendation
from backend.portfolio.recommendations import admit_recommendation
from backend.tests.integration.test_bootstrap import database as database
from backend.tests.integration.test_recommendations import request_for

pytestmark = pytest.mark.integration


def computed(database: Engine, root: Path) -> tuple[UUID, UUID]:
    owner, request = request_for(database, root)
    accepted = admit_recommendation(database, root, owner, request)
    worker = Worker(Queue(database), artifact_root=root)
    assert worker.run_once()  # Actual recommendation preparation/publication.
    assert worker.run_once()  # Drain its forecast before testing fill admission.
    return owner, accepted.recommendation_id


def test_public_approval_retry_recovery_and_cancel_without_source_files(
    database: Engine, tmp_path: Path
) -> None:
    owner, identity = computed(database, tmp_path)
    settings = Settings(database.url.render_as_string(hide_password=False), artifact_root=tmp_path)
    headers = {"Idempotency-Key": str(uuid4())}
    path = f"/api/v1/recommendations/{identity}"
    with TestClient(create_app(settings)) as client:
        first = client.post(path + "/apply", json={"expected_revision": 1}, headers=headers)
        assert first.status_code == 202, first.text
        accepted = first.json()
        assert accepted["operator_recorded_at"].endswith("Z")
        assert accepted["clock_mode"] == "synthetic_replay"
        batch_path = f"/api/v1/order-batches/{accepted['batch_id']}"
        pending = client.get(batch_path)
        assert pending.status_code == 200, pending.text
        assert (
            pending.json()["status"] == "pending"
            and pending.json()["current_portfolio_revision"] == 2
        )
        shutil.rmtree(tmp_path / "snapshots")
        assert (
            client.post(path + "/apply", json={"expected_revision": 1}, headers=headers).json()
            == accepted
        )
        assert client.get(path + "/apply-result", headers=headers).json() == accepted
        changed = client.post(path + "/apply", json={"expected_revision": 2}, headers=headers)
        assert (
            changed.status_code == 409 and changed.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
        )
        assert client.post(path + "/dismiss", json={}).status_code == 409
        cancelled = client.post(batch_path + "/cancel", json={})
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["status"] == "cancelled"
        assert all(row["filled_quantity"] == "0.000000" for row in cancelled.json()["orders"])
        assert client.post(batch_path + "/cancel", json={}).json() == cancelled.json()
        assert client.get(path + "/apply-result", headers=headers).json() == accepted
    with database.connect() as connection:
        assert connection.execute(
            text("SELECT cash_usd,revision,last_sequence FROM paper_portfolio WHERE id=:id"),
            {"id": owner},
        ).one() == (1000, 3, 3)
        assert connection.execute(text("SELECT count(*) FROM paper_fill")).scalar_one() == 0


def test_concurrent_exact_approval_one_batch_one_event(database: Engine, tmp_path: Path) -> None:
    owner, identity = computed(database, tmp_path)
    key = uuid4()
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(
            workers.map(
                lambda _: apply_recommendation(database, tmp_path, identity, 1, key), range(2)
            )
        )
    assert results[0] == results[1]
    with database.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM paper_order_batch")).scalar_one() == 1
        assert (
            connection.execute(
                text("SELECT count(*) FROM ledger_event WHERE kind='batch_approval'")
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                text("SELECT cash_usd FROM paper_portfolio WHERE id=:id"), {"id": owner}
            ).scalar_one()
            == 1000
        )


def test_public_fixture_step_actual_fill_and_original_key_after_cancel(
    database: Engine, tmp_path: Path
) -> None:
    owner, identity = computed(database, tmp_path)
    settings = Settings(database.url.render_as_string(hide_password=False), artifact_root=tmp_path)
    with TestClient(create_app(settings)) as client:
        approved = client.post(
            f"/api/v1/recommendations/{identity}/apply",
            json={"expected_revision": 1},
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert approved.status_code == 202, approved.text
        path = f"/api/v1/order-batches/{approved.json()['batch_id']}"
        headers = {"Idempotency-Key": str(uuid4())}
        step = client.post(path + "/advance-fixture", json={}, headers=headers)
        assert step.status_code == 202, step.text
        original = step.json()
        assert original["fixture_observed_at"] > approved.json()["approved_at"]
        overlap = client.post(
            path + "/advance-fixture", json={}, headers={"Idempotency-Key": str(uuid4())}
        )
        assert overlap.status_code == 409
        assert client.post(path + "/advance-fixture", json={}, headers=headers).json() == original
        assert Worker(Queue(database), artifact_root=tmp_path).run_once()
        waiting = client.get(path).json()
        # Authored fixture bars arrive one second after close. The first explicit
        # close therefore remains pending; no caller or route may invent a quote.
        assert waiting["latest_fill_job"]["status"] == "completed"
        assert all(row["filled_quantity"] == "0.000000" for row in waiting["orders"])
        later = client.post(
            path + "/advance-fixture", json={}, headers={"Idempotency-Key": str(uuid4())}
        )
        assert later.status_code == 202, later.text
        assert later.json()["fixture_observed_at"] > original["fixture_observed_at"]
        assert Worker(Queue(database), artifact_root=tmp_path).run_once()
        filled = client.get(path)
        assert filled.status_code == 200, filled.text
        assert any(row["filled_quantity"] != "0.000000" for row in filled.json()["orders"]), (
            filled.json()
        )
        cancelled = client.post(path + "/cancel", json={})
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["status"] == "partially_filled"
        assert cancelled.json()["orders"] == client.get(path).json()["orders"]
        shutil.rmtree(tmp_path / "snapshots")
        assert client.post(path + "/advance-fixture", json={}, headers=headers).json() == original
    with database.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM paper_fill")).scalar_one() == 1
        assert (
            connection.execute(
                text("SELECT cash_usd FROM paper_portfolio WHERE id=:id"), {"id": owner}
            ).scalar_one()
            < 1000
        )


def test_dismiss_preserves_immutable_evidence_and_finances(
    database: Engine, tmp_path: Path
) -> None:
    owner, identity = computed(database, tmp_path)
    with Session(database) as session:
        row = session.get(RecommendationReference, identity)
        assert row is not None
        original, fingerprint = row.content, row.content_sha256
    settings = Settings(database.url.render_as_string(hide_password=False), artifact_root=tmp_path)
    with TestClient(create_app(settings)) as client:
        path = f"/api/v1/recommendations/{identity}"
        assert client.post(path + "/dismiss", json={}).json()["status"] == "dismissed"
        assert client.post(path + "/dismiss", json={}).status_code == 200
        assert (
            client.post(
                path + "/apply",
                json={"expected_revision": 1},
                headers={"Idempotency-Key": str(uuid4())},
            ).status_code
            == 409
        )
    with Session(database) as session:
        row = session.get(RecommendationReference, identity)
        assert (
            row is not None
            and row.content == original
            and row.content_sha256 == fingerprint == digest(original)
        )
    with database.connect() as connection:
        assert connection.execute(
            text("SELECT cash_usd,revision,last_sequence FROM paper_portfolio WHERE id=:id"),
            {"id": owner},
        ).one() == (1000, 1, 1)


@pytest.mark.parametrize("condition", ["pending", "dismissed", "stale_revision", "stale_source"])
def test_public_apply_rejects_unavailable_or_changed_original_state(
    database: Engine, tmp_path: Path, condition: str
) -> None:
    owner, request = request_for(database, tmp_path)
    accepted = admit_recommendation(database, tmp_path, owner, request)
    if condition != "pending":
        assert Worker(Queue(database), artifact_root=tmp_path).run_once()
    if condition == "stale_revision":
        # Reconciliation does not invent cash; a separate computed decision can
        # become stale only through a legitimate posted revision transition.
        from backend.market_data.catalog import verified_snapshot
        from backend.persistence.models.snapshot import DatasetSnapshot
        from backend.portfolio.batches import approve_batch, cancel_batch

        with Session(database) as session:
            row = session.get(DatasetSnapshot, request.snapshot_id)
            assert row is not None
            pinned = verified_snapshot(row, tmp_path)
        batch = approve_batch(
            database,
            owner,
            accepted.recommendation_id,
            expected_revision=1,
            idempotency_key=uuid4(),
            pinned=pinned,
            server_clock=True,
        )
        cancel_batch(database, batch, server_clock=True)
    if condition == "stale_source":
        assert Worker(Queue(database), artifact_root=tmp_path).run_once()  # Drain forecast.
        from backend.tests.integration.test_paper_batches import publish_decision_only

        publish_decision_only(database, tmp_path, request.as_of_session)
    settings = Settings(database.url.render_as_string(hide_password=False), artifact_root=tmp_path)
    with TestClient(create_app(settings)) as client:
        path = f"/api/v1/recommendations/{accepted.recommendation_id}"
        if condition == "dismissed":
            assert client.post(path + "/dismiss", json={}).status_code == 200
        response = client.post(
            path + "/apply",
            json={"expected_revision": 1},
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == (
            "STALE_DATA" if condition == "stale_source" else "STATE_CONFLICT"
        )
    with database.connect() as connection:
        assert (
            connection.execute(
                text("SELECT cash_usd FROM paper_portfolio WHERE id=:id"), {"id": owner}
            ).scalar_one()
            == 1000
        )
        assert connection.execute(text("SELECT count(*) FROM paper_fill")).scalar_one() == 0


def test_cancel_after_readonly_fill_preparation_fences_posting(
    database: Engine, tmp_path: Path
) -> None:
    from datetime import timedelta
    from multiprocessing import get_context

    from backend.jobs.handlers.apply_scheduled_fills import apply_scheduled_fills
    from backend.market_data.catalog import verified_snapshot
    from backend.market_data.models import Calendar
    from backend.persistence.models.snapshot import DatasetSnapshot
    from backend.portfolio.batches import cancel_batch
    from backend.portfolio.fills import enqueue_batch_attempt, seal_fill

    owner, identity = computed(database, tmp_path)
    approved = apply_recommendation(database, tmp_path, identity, 1, uuid4())
    with Session(database) as session:
        rec = session.get(RecommendationReference, identity)
        assert rec is not None
        source = session.get(DatasetSnapshot, rec.snapshot_id)
        assert source is not None
        pinned = verified_snapshot(source, tmp_path)
    calendar = Calendar.model_validate_json(
        pinned.artifacts[pinned.manifest.calendar.artifact_path]
    )
    eligible = next(row for row in calendar.sessions if row.open_at == approved.eligible_open_at)
    queue = Queue(database)
    assert (
        enqueue_batch_attempt(
            queue, approved.batch_id, fixture_observed_at=eligible.close_at + timedelta(seconds=1)
        )
        is not None
    )
    lease = queue.claim("public-cancel-race")
    assert lease is not None
    prepared = apply_scheduled_fills(lease.payload, get_context("spawn").Event(), root=tmp_path)
    cancel_batch(database, approved.batch_id, server_clock=True)
    seal_fill(queue, lease, prepared)
    with database.connect() as connection:
        assert (
            connection.execute(
                text("SELECT cash_usd FROM paper_portfolio WHERE id=:id"), {"id": owner}
            ).scalar_one()
            == 1000
        )
        assert connection.execute(text("SELECT count(*) FROM paper_fill")).scalar_one() == 0
        assert (
            connection.execute(
                text("SELECT status FROM paper_order_batch WHERE id=:id"), {"id": approved.batch_id}
            ).scalar_one()
            == "cancelled"
        )


def test_cash_only_computed_decision_cannot_manufacture_an_approval_batch(
    database: Engine, tmp_path: Path
) -> None:
    from backend.domain.registry import StrategyCreateRequest
    from backend.domain.strategy import StrategyConfigV1
    from backend.market_data.catalog import verified_snapshot
    from backend.market_data.models import Calendar
    from backend.persistence.models.snapshot import DatasetSnapshot
    from backend.persistence.readiness import read_workspace
    from backend.portfolio.ledger import create_portfolio
    from backend.strategies.clock import decision_cutoff
    from backend.strategies.registry import create_strategy, default_config

    _, request = request_for(database, tmp_path)
    rules = default_config().model_dump(mode="json")
    rules["universe"]["min_price_usd"] = "1000000"
    strategy = create_strategy(
        database,
        StrategyCreateRequest(
            name="SYNTHETIC_DATA_ONLY empty", config=StrategyConfigV1.model_validate(rules)
        ),
    )
    with Session(database) as session:
        source = session.get(DatasetSnapshot, request.snapshot_id)
        assert source is not None
        pinned = verified_snapshot(source, tmp_path)
    calendar = Calendar.model_validate_json(
        pinned.artifacts[pinned.manifest.calendar.artifact_path]
    )
    owner = uuid4()
    create_portfolio(
        database,
        portfolio_id=owner,
        workspace_id=read_workspace(database).id,
        strategy_version_id=strategy.published_version.id,
        name="SYNTHETIC_DATA_ONLY empty",
        created_at=decision_cutoff(calendar, request.as_of_session),
    )
    accepted = admit_recommendation(database, tmp_path, owner, request)
    assert Worker(Queue(database), artifact_root=tmp_path).run_once()
    settings = Settings(database.url.render_as_string(hide_password=False), artifact_root=tmp_path)
    with TestClient(create_app(settings)) as client:
        response = client.post(
            f"/api/v1/recommendations/{accepted.recommendation_id}/apply",
            json={"expected_revision": 1},
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert response.status_code == 422, response.text
    with database.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM paper_order_batch")).scalar_one() == 0
        assert connection.execute(
            text("SELECT cash_usd,revision FROM paper_portfolio WHERE id=:id"), {"id": owner}
        ).one() == (1000, 1)
