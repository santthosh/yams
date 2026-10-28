import json
import logging
import multiprocessing as mp
import os
import platform
import time
from concurrent.futures import ThreadPoolExecutor
from multiprocessing.process import BaseProcess
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


def evidence(name: str, **measurements: Any) -> None:
    with Path("/evidence/worker.jsonl").open("a") as output:
        output.write(
            json.dumps(
                {
                    "case": name,
                    "architecture": platform.machine(),
                    "python": platform.python_version(),
                    "container_limits": {
                        name: Path(f"/sys/fs/cgroup/{name}").read_text().strip()
                        for name in ("cpu.max", "memory.max", "memory.swap.max", "pids.max")
                    },
                    **measurements,
                },
                sort_keys=True,
            )
            + "\n"
        )


def idle_handler(payload: dict[str, Any], cancelled: Event) -> int:
    end = time.monotonic() + 2.5
    while time.monotonic() < end:
        if cancelled.wait(0.05):
            raise Cancelled
    return 45


def busy_handler(payload: dict[str, Any], cancelled: Event) -> int:
    end = time.monotonic() + 2.5
    while time.monotonic() < end:
        if cancelled.is_set():
            raise Cancelled
    return 45


def stuck_handler(payload: dict[str, Any], cancelled: Event) -> int:
    while True:
        time.sleep(1)


def memory_handler(payload: dict[str, Any], cancelled: Event) -> int:
    data = bytearray(3 * 1024 * 1024 * 1024)
    return len(data)


def invalid_output_handler(payload: dict[str, Any], cancelled: Event) -> int:
    return 46


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


@pytest.mark.parametrize("handler", [idle_handler, busy_handler])
@pytest.mark.parametrize("iteration", range(4))
def test_supervisor_heartbeats_during_handler_work(
    database: Engine,
    caplog: pytest.LogCaptureFixture,
    handler: Any,
    iteration: int,
) -> None:
    bootstrap(database)
    queue = Queue(database)
    identity = queue.enqueue(
        "diagnostic", PAYLOAD, uuid4(), limits=JobLimits(heartbeat_seconds=1, lease_seconds=2)
    )
    caplog.set_level(logging.INFO)
    assert Worker(queue, handler).run_once()
    result = queue.get(identity)
    assert result is not None and result.status == "completed"
    assert "max_heartbeat_gap=" in caplog.text
    with Session(database) as session:
        attempt = session.get(JobAttempt, (identity, 1))
        assert attempt is not None and attempt.ended_at is not None
        assert (attempt.ended_at - attempt.started_at).total_seconds() > 2
        assert 0 < attempt.diagnostics["max_heartbeat_gap_seconds"] < 2
        assert attempt.diagnostics["peak_rss_kib"] > 0
        assert attempt.diagnostics["cpu_seconds"] > 0
        evidence(
            handler.__name__, iteration=iteration, warmup=iteration == 0, **attempt.diagnostics
        )


@pytest.mark.parametrize(
    ("handler", "expected"),
    [
        (stuck_handler, "TIME_LIMIT"),
        (memory_handler, "RESOURCE_EXHAUSTED"),
        (crashed_handler, "JOB_FAILED"),
        (invalid_output_handler, "VALIDATION_ERROR"),
    ],
)
def test_resource_failure_never_seals_partial_output(
    database: Engine, handler: Any, expected: str
) -> None:
    bootstrap(database)
    queue = Queue(database)
    # Spawn/import time counts toward the wall budget. Only the timeout case tests
    # a one-second deadline; other failures must reach their handlers on hosted CI.
    wall_seconds = 1 if expected == "TIME_LIMIT" else 10
    identity = queue.enqueue(
        "diagnostic", PAYLOAD, uuid4(), limits=JobLimits(wall_seconds=wall_seconds)
    )
    started = time.monotonic()
    assert Worker(queue, handler).run_once()
    queue.recover()
    result = queue.get(identity)
    assert result is not None and result.status == "failed" and result.error is not None
    assert result.error.code == expected
    assert result.result is None and result.attempts == 1
    assert time.monotonic() - started < wall_seconds + 3
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(DiagnosticEffect)) == 0
        attempt = session.get(JobAttempt, (identity, 1))
        assert attempt is not None
        evidence(expected, **attempt.diagnostics)


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
    elapsed = time.monotonic() - started
    assert elapsed < 3
    evidence("unresponsive_cancel", cancellation_seconds=elapsed)


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
            killed_at = time.monotonic()
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
        evidence(
            "crash_after_commit" if after_commit else "crash_before_publication",
            attempts=result.attempts,
            recovery_seconds=None if after_commit else time.monotonic() - killed_at,
        )
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


def test_process_start_failure_is_terminal_and_safe(
    database: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bootstrap(database)
    queue = Queue(database)
    identity = queue.enqueue("diagnostic", PAYLOAD, uuid4())

    def unavailable(self: BaseProcess) -> None:
        raise OSError("synthetic process allocation failure")

    monkeypatch.setattr(BaseProcess, "start", unavailable)
    assert Worker(queue).run_once()
    result = queue.get(identity)
    assert result is not None and result.status == "failed" and result.error is not None
    assert result.error.code == "RESOURCE_EXHAUSTED"
    assert result.attempts == 1 and result.result is None


def test_child_wall_deadline_survives_slow_supervisor_status_read(
    database: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bootstrap(database)
    queue = Queue(database)
    identity = queue.enqueue("diagnostic", PAYLOAD, uuid4(), limits=JobLimits(wall_seconds=2))
    original_get = queue.get
    CRASH_CHILD_PID.unlink(missing_ok=True)

    def slow_get(job_id: Any) -> Any:
        time.sleep(3)
        assert CRASH_CHILD_PID.exists(), "Handler did not start before its deadline"
        child_state = Path(f"/proc/{int(CRASH_CHILD_PID.read_text())}/stat")
        assert not child_state.exists() or child_state.read_text().split()[2] == "Z"
        return original_get(job_id)

    monkeypatch.setattr(queue, "get", slow_get)
    try:
        assert Worker(queue, observed_stuck_handler).run_once()
        result = original_get(identity)
        assert result is not None and result.status == "failed" and result.error is not None
        assert result.error.code == "TIME_LIMIT" and result.result is None
    finally:
        CRASH_CHILD_PID.unlink(missing_ok=True)


def provider_timeout_handler(payload: dict[str, Any], cancelled: Event) -> int:
    from backend.market_data.providers.yahoo import ProviderFailure

    raise ProviderFailure("PROVIDER_TIMEOUT")


def test_provider_retry_exhaustion_has_safe_actionable_reason(database: Engine) -> None:
    from datetime import timedelta

    from backend.persistence.models.job import Job

    bootstrap(database)
    queue = Queue(database, limits=JobLimits(max_attempts=2))
    identity = queue.enqueue("diagnostic", PAYLOAD, uuid4())
    assert Worker(queue, provider_timeout_handler).run_once()
    result = queue.get(identity)
    assert result is not None and result.status == "queued" and result.attempts == 1
    with Session(database) as session, session.begin():
        row = session.get(Job, identity)
        assert row is not None
        row.available_at = queue.clock(session) - timedelta(seconds=1)
    assert Worker(queue, provider_timeout_handler).run_once()
    result = queue.get(identity)
    assert result is not None and result.status == "failed" and result.attempts == 2
    assert result.error is not None and result.error.details == {"reason": "PROVIDER_TIMEOUT"}
