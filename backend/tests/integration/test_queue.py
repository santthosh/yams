from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, insert, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from backend.api.main import create_app
from backend.jobs.queue import IdempotencyConflict, Queue
from backend.jobs.registry import JobLimits
from backend.persistence.bootstrap import bootstrap, migration_config
from backend.persistence.database import Settings
from backend.persistence.models.job import DiagnosticEffect, Job, JobAttempt, Schedule
from backend.persistence.models.workspace import LocalWorkspace
from backend.tests.integration.test_bootstrap import database as database

pytestmark = pytest.mark.integration
PAYLOAD = {"schema_version": 1, "work_units": 10}


def queue(database: Engine) -> Queue:
    bootstrap(database)
    return Queue(database)


def test_upgrade_preserves_existing_workspace(database: Engine) -> None:
    identity = uuid4()
    with database.begin() as connection:
        config = migration_config()
        config.attributes["connection"] = connection
        command.upgrade(config, "0001_workspace")
        connection.execute(
            insert(LocalWorkspace).values(
                id=identity,
                singleton=1,
                locale="en-US",
                default_benchmark="SPY",
                preferences={"keep": True},
            )
        )
    assert bootstrap(database) == identity
    with Session(database) as session:
        assert session.get(LocalWorkspace, identity).preferences == {"keep": True}  # type: ignore[union-attr]


def test_enqueue_idempotency_and_database_input_immutability(database: Engine) -> None:
    service = queue(database)
    key = uuid4()
    with ThreadPoolExecutor(max_workers=2) as executor:
        jobs = list(executor.map(lambda _: service.enqueue("diagnostic", PAYLOAD, key), range(2)))
    assert jobs[0] == jobs[1]
    with pytest.raises(IdempotencyConflict):
        service.enqueue("diagnostic", {**PAYLOAD, "work_units": 11}, key)
    with pytest.raises(DBAPIError), database.begin() as connection:
        connection.execute(text("UPDATE job SET payload = '{}' WHERE id = :id"), {"id": jobs[0]})


def test_concurrent_claims_and_skip_locked(database: Engine) -> None:
    service = queue(database)
    first = service.enqueue("diagnostic", PAYLOAD, uuid4())
    with ThreadPoolExecutor(max_workers=2) as executor:
        leases = list(executor.map(service.claim, ["one", "two"]))
    assert len([lease for lease in leases if lease]) == 1
    assert next(lease for lease in leases if lease).job_id == first
    second = service.enqueue("diagnostic", PAYLOAD, uuid4())
    third = service.enqueue("diagnostic", PAYLOAD, uuid4())
    with Session(database) as locker, locker.begin():
        locker.execute(select(Job).where(Job.id == second).with_for_update()).scalar_one()
        claimed = service.claim("other")
        assert claimed is not None and claimed.job_id == third


def test_fenced_recovery_and_bounded_attempts(database: Engine) -> None:
    bootstrap(database)
    now = datetime(2030, 1, 1, tzinfo=UTC)
    service = Queue(database, clock=lambda _: now)
    identity = service.enqueue("diagnostic", PAYLOAD, uuid4())
    first = service.claim("crashed")
    assert first is not None
    now += timedelta(seconds=29)
    assert service.recover() == 0
    now += timedelta(seconds=1)
    assert service.recover() == 1
    assert service.heartbeat(first) is None
    assert service.complete_diagnostic(first, 45) is False
    assert service.claim("too-early") is None
    now += timedelta(seconds=1)
    second = service.claim("replacement")
    assert second is not None and second.attempt == 2 and second.token != first.token
    now += timedelta(seconds=30)
    assert service.recover() == 1
    now += timedelta(seconds=2)
    third = service.claim("last")
    assert third is not None and third.attempt == 3
    now += timedelta(seconds=30)
    assert service.recover() == 1
    result = service.get(identity)
    assert result is not None and result.status == "failed" and result.error is not None
    assert result.error.code == "JOB_FAILED"
    assert service.claim("never-fourth") is None
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(JobAttempt)) == 3


def test_completion_is_atomic_idempotent_and_cancel_serialized(database: Engine) -> None:
    service = queue(database)
    identity = service.enqueue("diagnostic", PAYLOAD, uuid4())
    lease = service.claim("worker")
    assert lease is not None
    with pytest.raises(ValueError, match="output"):
        service.complete_diagnostic(lease, 46)
    assert service.complete_diagnostic(lease, 45)
    assert not service.complete_diagnostic(lease, 45)
    assert service.cancel(identity).status == "completed"  # type: ignore[union-attr]
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(DiagnosticEffect)) == 1
        assert session.get(DiagnosticEffect, identity).value == 45  # type: ignore[union-attr]
    cancelled = service.enqueue("diagnostic", PAYLOAD, uuid4())
    lease = service.claim("worker")
    assert lease is not None
    assert service.cancel(cancelled).status == "cancel_requested"  # type: ignore[union-attr]
    assert not service.complete_diagnostic(lease, 45)
    assert service.acknowledge_cancel(lease)
    assert service.get(cancelled).status == "cancelled"  # type: ignore[union-attr]
    pending = service.enqueue("diagnostic", PAYLOAD, uuid4())
    assert service.cancel(pending).status == "cancelled"  # type: ignore[union-attr]
    assert service.claim("no-cancelled-claim") is None


def test_retry_classification_and_deadline_exhaustion(database: Engine) -> None:
    bootstrap(database)
    now = datetime(2030, 1, 1, tzinfo=UTC)
    service = Queue(database, clock=lambda _: now)
    identity = service.enqueue("diagnostic", PAYLOAD, uuid4())
    lease = service.claim("worker")
    assert lease is not None
    assert service.fail(lease, "PROVIDER_UNAVAILABLE", retryable=True, retry_after=1000)
    now += timedelta(seconds=29)
    assert service.claim("backoff") is None
    now += timedelta(seconds=1)
    lease = service.claim("retry")
    assert lease is not None
    assert service.fail(lease, "RESOURCE_EXHAUSTED", retryable=True)
    assert service.get(identity).status == "failed"  # type: ignore[union-attr]
    timeout = service.enqueue("diagnostic", PAYLOAD, uuid4(), limits=JobLimits(wall_seconds=1))
    lease = service.claim("timed-out")
    assert lease is not None
    now += timedelta(seconds=1)
    assert not service.complete_diagnostic(lease, 45)
    assert service.recover() == 1
    assert service.get(timeout).error.code == "TIME_LIMIT"  # type: ignore[union-attr]


def test_job_get_is_read_only_and_public_cancel_remains_staged(database: Engine) -> None:
    service = queue(database)
    identity = service.enqueue("diagnostic", PAYLOAD, uuid4())
    before = service.get(identity)
    settings = Settings(database.url.render_as_string(hide_password=False))
    with TestClient(create_app(settings)) as client:
        response = client.get(f"/api/v1/jobs/{identity}")
        assert response.status_code == 200
        assert response.json()["status"] == "queued"
        assert response.json()["result"] is None
        assert client.get(f"/api/v1/jobs/{uuid4()}").status_code == 404
        assert client.post(f"/api/v1/jobs/{identity}/cancel").status_code == 404
    assert service.get(identity) == before


def test_scheduler_catchup_is_bounded_deduplicated_and_ordered(database: Engine) -> None:
    bootstrap(database)
    now = datetime(2030, 1, 1, tzinfo=UTC)
    service = Queue(database, clock=lambda _: now)
    first_due = now - timedelta(seconds=20)
    schedule_id = service.create_schedule(
        "diagnostic",
        PAYLOAD,
        target="synthetic-counter",
        first_due_at=first_due,
        interval_seconds=5,
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        counts = list(executor.map(lambda _: service.catch_up(2), range(2)))
    assert 2 <= sum(counts) <= 4
    # A new Queue represents restart; the durable cursor retains all remaining work.
    restarted = Queue(database, clock=lambda _: now)
    assert restarted.catch_up() == 5 - sum(counts)
    assert restarted.catch_up() == 0
    with Session(database) as session:
        rows = session.execute(select(Job).order_by(Job.scheduled_at)).scalars().all()
        assert len(rows) == 5
        assert [row.scheduled_at for row in rows] == [
            first_due + timedelta(seconds=5 * index) for index in range(5)
        ]
        assert len({row.idempotency_key for row in rows}) == 5
        assert all(row.schedule_id == schedule_id and row.schedule_version == 1 for row in rows)
        schedule = session.get(Schedule, schedule_id)
        assert schedule is not None and schedule.next_due_at == now + timedelta(seconds=5)
    first = restarted.claim("first")
    assert first is not None
    assert restarted.claim("cannot-overtake") is None
    assert restarted.complete_diagnostic(first, 45)
    assert restarted.claim("next") is not None
    with pytest.raises(DBAPIError), database.begin() as connection:
        connection.execute(
            text("UPDATE schedule SET payload = '{}' WHERE id = :id"), {"id": schedule_id}
        )


def test_unmaterialized_earlier_occurrence_blocks_later_target_job(database: Engine) -> None:
    bootstrap(database)
    now = datetime(2030, 1, 1, tzinfo=UTC)
    service = Queue(database, clock=lambda _: now)
    service.create_schedule(
        "diagnostic", PAYLOAD, target="same", first_due_at=now, interval_seconds=5
    )
    assert service.catch_up(1) == 1
    # Another schedule introduced with an older cutoff must be materialized first.
    service.create_schedule(
        "diagnostic",
        PAYLOAD,
        target="same",
        first_due_at=now - timedelta(seconds=10),
        interval_seconds=5,
    )
    assert service.claim("later") is None
    assert service.catch_up(1) == 1
    lease = service.claim("earlier")
    assert lease is not None
    with Session(database) as session:
        row = session.get(Job, lease.job_id)
        assert row is not None and row.scheduled_at == now - timedelta(seconds=10)


def test_poisoned_persisted_payload_fails_without_starving_next_job(database: Engine) -> None:
    service = queue(database)
    poison = service.enqueue("diagnostic", PAYLOAD, uuid4())
    healthy = service.enqueue("diagnostic", PAYLOAD, uuid4())
    # Simulate storage corruption in this disposable database, not a public write path.
    with database.begin() as connection:
        connection.execute(text("ALTER TABLE job DISABLE TRIGGER immutable_job_inputs"))
        connection.execute(text("UPDATE job SET payload = '{}' WHERE id = :id"), {"id": poison})
        connection.execute(text("ALTER TABLE job ENABLE TRIGGER immutable_job_inputs"))
    assert service.claim("poison") is None
    failed = service.get(poison)
    assert failed is not None and failed.status == "failed" and failed.attempts == 0
    assert failed.error is not None and failed.error.code == "VALIDATION_ERROR"
    lease = service.claim("healthy")
    assert lease is not None and lease.job_id == healthy


def test_default_limit_change_does_not_mutate_accepted_job(
    database: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bootstrap(database)
    monkeypatch.setenv("YAMS_JOB_LIMITS", '{"wall_seconds":30}')
    service = Queue(database)
    first = service.enqueue("diagnostic", PAYLOAD, uuid4())
    monkeypatch.setenv("YAMS_JOB_LIMITS", '{"wall_seconds":10}')
    restarted = Queue(database)
    second = restarted.enqueue("diagnostic", PAYLOAD, uuid4())
    with Session(database) as session:
        first_row, second_row = session.get(Job, first), session.get(Job, second)
        assert first_row is not None and second_row is not None
        assert first_row.limits["wall_seconds"] == 30
        assert second_row.limits["wall_seconds"] == 10


def test_cancel_complete_race_has_one_legal_winner(database: Engine) -> None:
    service = queue(database)
    identity = service.enqueue("diagnostic", PAYLOAD, uuid4())
    lease = service.claim("racing")
    assert lease is not None
    with ThreadPoolExecutor(max_workers=2) as executor:
        completion = executor.submit(service.complete_diagnostic, lease, 45)
        cancellation = executor.submit(service.cancel, identity)
        completed = completion.result(timeout=5)
        assert cancellation.result(timeout=5) is not None
    result = service.get(identity)
    assert result is not None
    if completed:
        assert result.status == "completed" and result.result is not None
    else:
        assert result.status == "cancel_requested" and result.result is None
        assert service.acknowledge_cancel(lease)
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(DiagnosticEffect)) == int(completed)


def test_concurrent_recoverers_abandon_one_attempt(database: Engine) -> None:
    bootstrap(database)
    now = datetime(2030, 1, 1, tzinfo=UTC)
    service = Queue(database, clock=lambda _: now)
    identity = service.enqueue("diagnostic", PAYLOAD, uuid4())
    assert service.claim("old") is not None
    now += timedelta(seconds=30)
    with ThreadPoolExecutor(max_workers=2) as executor:
        recovered = list(executor.map(lambda _: service.recover(), range(2)))
    assert sum(recovered) == 1
    now += timedelta(seconds=1)
    replacement = service.claim("replacement")
    assert replacement is not None and replacement.attempt == 2
    with Session(database) as session:
        attempt = session.get(JobAttempt, (identity, 1))
        assert attempt is not None and attempt.outcome == "abandoned"
        assert attempt.diagnostics["backoff_seconds"] == 1


def test_transient_retry_exhaustion_retains_correlation(database: Engine) -> None:
    bootstrap(database)
    now = datetime(2030, 1, 1, tzinfo=UTC)
    service = Queue(database, clock=lambda _: now)
    correlation = uuid4()
    identity = service.enqueue("diagnostic", PAYLOAD, uuid4(), correlation_id=correlation)
    for attempt in range(1, 4):
        lease = service.claim("transient")
        assert lease is not None and lease.attempt == attempt
        assert service.fail(lease, "PROVIDER_UNAVAILABLE", retryable=True)
        if attempt < 3:
            assert service.claim("too-early") is None
            now += timedelta(seconds=2 ** (attempt - 1))
    result = service.get(identity)
    assert result is not None and result.status == "failed" and result.error is not None
    assert result.error.correlation_id == correlation
    assert result.error.code == "PROVIDER_UNAVAILABLE" and result.attempts == 3
    assert service.claim("no-fourth") is None
