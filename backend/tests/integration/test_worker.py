import logging
import multiprocessing as mp
import os
import time
from concurrent.futures import ThreadPoolExecutor
from multiprocessing.synchronize import Event
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from backend.jobs.queue import Lease, Queue
from backend.jobs.registry import JobLimits
from backend.jobs.worker import Cancelled, Worker, verify_container_budget
from backend.persistence.bootstrap import bootstrap
from backend.persistence.database import database_engine
from backend.persistence.models.job import DiagnosticEffect, JobAttempt
from backend.tests.integration.test_bootstrap import database as database

pytestmark = pytest.mark.integration
PAYLOAD = {"schema_version": 1, "work_units": 10}


def idle_handler(payload: dict[str, Any], cancelled: Event) -> int:
    end = time.monotonic() + 2.5
    while time.monotonic() < end:
        if cancelled.wait(0.05):
            raise Cancelled
    return 45


def stuck_handler(payload: dict[str, Any], cancelled: Event) -> int:
    while True:
        time.sleep(1)


def memory_handler(payload: dict[str, Any], cancelled: Event) -> int:
    data = bytearray(3 * 1024 * 1024 * 1024)
    return len(data)


def crashed_handler(payload: dict[str, Any], cancelled: Event) -> int:
    os._exit(7)


def test_supervised_diagnostic_publishes_one_effect(database: Engine) -> None:
    bootstrap(database)
    verify_container_budget()
    queue = Queue(database)
    identity = queue.enqueue("diagnostic", PAYLOAD, uuid4())
    assert Worker(queue).run_once()
    result = queue.get(identity)
    assert result is not None and result.status == "completed" and result.result is not None
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(DiagnosticEffect)) == 1
    assert not Worker(queue).run_once()


def test_supervisor_heartbeats_while_handler_is_idle(
    database: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    bootstrap(database)
    queue = Queue(database)
    identity = queue.enqueue(
        "diagnostic", PAYLOAD, uuid4(), limits=JobLimits(heartbeat_seconds=1, lease_seconds=2)
    )
    caplog.set_level(logging.INFO)
    assert Worker(queue, idle_handler).run_once()
    result = queue.get(identity)
    assert result is not None and result.status == "completed"
    assert "max_heartbeat_gap=" in caplog.text
    with Session(database) as session:
        attempt = session.get(JobAttempt, (identity, 1))
        assert attempt is not None and attempt.ended_at is not None
        assert (attempt.ended_at - attempt.started_at).total_seconds() > 2


@pytest.mark.parametrize(
    ("handler", "expected"),
    [
        (stuck_handler, "TIME_LIMIT"),
        (memory_handler, "RESOURCE_EXHAUSTED"),
        (crashed_handler, "JOB_FAILED"),
    ],
)
def test_resource_failure_never_seals_partial_output(
    database: Engine, handler: Any, expected: str
) -> None:
    bootstrap(database)
    queue = Queue(database)
    identity = queue.enqueue("diagnostic", PAYLOAD, uuid4(), limits=JobLimits(wall_seconds=1))
    started = time.monotonic()
    assert Worker(queue, handler).run_once()
    queue.recover()
    result = queue.get(identity)
    assert result is not None and result.status == "failed" and result.error is not None
    assert result.error.code == expected
    assert result.result is None and result.attempts == 1
    assert time.monotonic() - started < 4
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(DiagnosticEffect)) == 0


def test_running_cancel_terminates_unresponsive_handler(database: Engine) -> None:
    bootstrap(database)
    queue = Queue(database)
    identity = queue.enqueue(
        "diagnostic", PAYLOAD, uuid4(), limits=JobLimits(cancel_grace_seconds=1)
    )
    with ThreadPoolExecutor(max_workers=1) as executor:
        task = executor.submit(Worker(queue, stuck_handler).run_once)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            current = queue.get(identity)
            if current is not None and current.status == "running":
                break
            time.sleep(0.05)
        else:
            pytest.fail("Worker never claimed the diagnostic")
        started = time.monotonic()
        queue.cancel(identity)
        assert task.result(timeout=4)
    result = queue.get(identity)
    assert result is not None and result.status == "cancelled" and result.result is None
    assert time.monotonic() - started < 3


CRASH_CHILD_PID = Path("/evidence/supervisor-crash-child.pid")


def observed_stuck_handler(payload: dict[str, Any], cancelled: Event) -> int:
    CRASH_CHILD_PID.write_text(str(os.getpid()))
    return stuck_handler(payload, cancelled)


class CrashAfterCommitQueue(Queue):
    def complete_diagnostic(self, lease: Lease, value: int) -> bool:
        assert super().complete_diagnostic(lease, value)
        os._exit(17)


def crash_supervisor(database_url: str, after_commit: bool) -> None:
    engine = database_engine(database_url)
    try:
        if after_commit:
            Worker(CrashAfterCommitQueue(engine)).run_once()
        else:
            Worker(Queue(engine), observed_stuck_handler).run_once()
    finally:
        engine.dispose()


@pytest.mark.parametrize("after_commit", [False, True])
def test_supervisor_process_crash_preserves_exactly_one_effect(
    database: Engine, after_commit: bool
) -> None:
    bootstrap(database)
    queue = Queue(database)
    identity = queue.enqueue(
        "diagnostic",
        PAYLOAD,
        uuid4(),
        limits=JobLimits(heartbeat_seconds=1, lease_seconds=2, wall_seconds=30),
    )
    CRASH_CHILD_PID.unlink(missing_ok=True)
    process = mp.get_context("spawn").Process(
        target=crash_supervisor,
        args=(database.url.render_as_string(hide_password=False), after_commit),
    )
    process.start()
    try:
        deadline = time.monotonic() + 8
        if after_commit:
            process.join(timeout=8)
            assert process.exitcode == 17
        else:
            while not CRASH_CHILD_PID.exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            assert CRASH_CHILD_PID.exists(), "Handler never started"
            child_pid = int(CRASH_CHILD_PID.read_text())
            process.kill()
            process.join(timeout=2)
            assert process.exitcode == -9
            # A zombie has ceased execution; container init owns adopted-process reaping.
            child_state = Path(f"/proc/{child_pid}/stat")
            while child_state.exists() and time.monotonic() < deadline:
                if child_state.read_text().split()[2] == "Z":
                    break
                time.sleep(0.05)
            assert not child_state.exists() or child_state.read_text().split()[2] == "Z"
            assert queue.recover() == 0, "Live lease must not be reclaimed early"
            with Session(database) as session:
                assert session.scalar(select(func.count()).select_from(DiagnosticEffect)) == 0
            while time.monotonic() < deadline:
                Worker(queue).run_once()
                current = queue.get(identity)
                if current is not None and current.status == "completed":
                    break
                time.sleep(0.05)
        result = queue.get(identity)
        assert result is not None and result.status == "completed"
        assert result.attempts == (1 if after_commit else 2)
        assert not Worker(queue).run_once()
        with Session(database) as session:
            assert session.scalar(select(func.count()).select_from(DiagnosticEffect)) == 1
            assert session.scalar(select(DiagnosticEffect.value)) == 45
    finally:
        if process.is_alive():
            process.kill()
            process.join(timeout=2)
        process.close()
        CRASH_CHILD_PID.unlink(missing_ok=True)
