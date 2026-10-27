"""One supervised handler process; database fencing owns every publication."""

import ctypes
import logging
import multiprocessing as mp
import os
import resource
import signal
import sys
import time
from collections.abc import Callable
from multiprocessing.connection import Connection as PipeConnection
from multiprocessing.process import BaseProcess
from multiprocessing.synchronize import Event
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from backend.domain.common import ErrorCode
from backend.jobs.queue import Lease, Queue
from backend.jobs.registry import JobLimits, validate_payload
from backend.persistence.database import Settings, database_engine

logger = logging.getLogger(__name__)
Handler = Callable[[dict[str, Any], Event], int]


class Cancelled(Exception):
    pass


def diagnostic(payload: dict[str, Any], cancelled: Event) -> int:
    config = validate_payload("diagnostic", payload)
    result = 0
    for number in range(config.work_units):
        if number % 1024 == 0 and cancelled.is_set():
            raise Cancelled
        result += number
    return result


def verify_container_budget(root: Path = Path("/sys/fs/cgroup")) -> None:
    """Fail startup instead of claiming enforcement outside a bounded Linux cgroup."""
    limits = JobLimits()
    quota, period = (root / "cpu.max").read_text().split()
    memory = (root / "memory.max").read_text().strip()
    swap = (root / "memory.swap.max").read_text().strip()
    pids = (root / "pids.max").read_text().strip()
    if (
        quota == "max"
        or int(quota) / int(period) > limits.cpu_count
        or memory == "max"
        or int(memory) > limits.memory_mib * 1024 * 1024
        or swap != "0"
        or pids == "max"
        or int(pids) > limits.pids
    ):
        raise ValueError("Worker requires <=2 CPU, <=2 GiB, zero swap and <=64 PIDs")


def child_entry(
    handler: Handler, lease: Lease, cancelled: Event, pipe: PipeConnection, parent: int
) -> None:
    # This is server-owned code, never an import path supplied in a payload.
    try:
        os.setsid()
        if ctypes.CDLL(None).prctl(1, signal.SIGKILL, 0, 0, 0) != 0:
            raise RuntimeError("Parent-death protection unavailable")
        if os.getppid() != parent:
            os._exit(1)
        cap = lease.limits.memory_mib * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
        resource.setrlimit(
            resource.RLIMIT_CPU, (lease.limits.wall_seconds, lease.limits.wall_seconds)
        )
        resource.setrlimit(resource.RLIMIT_NPROC, (lease.limits.pids, lease.limits.pids))
        if sys.platform == "linux":
            cpus = sorted(os.sched_getaffinity(0))[: lease.limits.cpu_count]
            os.sched_setaffinity(0, cpus)
        else:
            raise RuntimeError("Worker requires Linux resource enforcement")
        for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
            os.environ[name] = "1"
        value = handler(lease.payload, cancelled)
        usage = resource.getrusage(resource.RUSAGE_SELF)
        pipe.send(("ok", value, usage.ru_maxrss, usage.ru_utime + usage.ru_stime))
    except Cancelled:
        pipe.send(("cancelled",))
    except MemoryError:
        pipe.send(("error", "RESOURCE_EXHAUSTED"))
    except Exception:
        # Never serialize exception messages, credentials or arbitrary handler objects.
        pipe.send(("error", "JOB_FAILED"))
    finally:
        pipe.close()


def stop_child(process: BaseProcess, grace: float) -> None:
    if process.is_alive():
        assert process.pid is not None
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            process.terminate()
        process.join(timeout=grace)
    if process.is_alive():
        assert process.pid is not None
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            process.kill()
        process.join(timeout=1)


class Worker:
    def __init__(self, queue: Queue, handler: Handler = diagnostic):
        self.queue = queue
        self.handler = handler
        self.owner = "worker-" + uuid4().hex
        self.next_schedule_tick = 0.0

    def run_once(self) -> bool:
        verify_container_budget()
        # Session lock enforces one supervisor/handler even if accidentally started twice.
        with self.queue.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as guard:
            locked = guard.execute(text("SELECT pg_try_advisory_lock(1497451860)")).scalar_one()
            if not locked:
                return False
            try:
                if time.monotonic() >= self.next_schedule_tick:
                    self.queue.catch_up()
                    self.next_schedule_tick = time.monotonic() + JobLimits().scheduler_tick_seconds
                self.queue.recover()
                lease = self.queue.claim(self.owner)
                if lease is None:
                    return False
                self.execute(lease)
                return True
            finally:
                guard.execute(text("SELECT pg_advisory_unlock(1497451860)"))

    def execute(self, lease: Lease) -> None:
        context = mp.get_context("spawn")
        cancelled = context.Event()
        reader, writer = context.Pipe(duplex=False)
        process = context.Process(
            target=child_entry, args=(self.handler, lease, cancelled, writer, os.getpid())
        )
        started = time.monotonic()
        last_heartbeat = started
        max_gap = 0.0
        cancellation_seen: float | None = None
        message: tuple[Any, ...] | None = None
        failure: ErrorCode | None = None
        process.start()
        writer.close()
        try:
            while process.is_alive():
                now = time.monotonic()
                # Poll status separately from the 5s heartbeat so cancellation remains responsive.
                status = self.queue.get(lease.job_id)
                if status is None or status.status not in {"running", "cancel_requested"}:
                    cancelled.set()
                    stop_child(process, lease.limits.cancel_grace_seconds)
                    return
                if status.status == "cancel_requested":
                    cancelled.set()
                    cancellation_seen = cancellation_seen if cancellation_seen is not None else now
                    if now - cancellation_seen >= lease.limits.cancel_grace_seconds:
                        stop_child(process, 0)
                        break
                if now - started >= lease.limits.wall_seconds:
                    failure = "TIME_LIMIT"
                    cancelled.set()
                    stop_child(process, 0)
                    break
                if now - last_heartbeat >= lease.limits.heartbeat_seconds:
                    authority = self.queue.heartbeat(lease)
                    if authority is None:
                        cancelled.set()
                        stop_child(process, 0)
                        return
                    max_gap = max(max_gap, now - last_heartbeat)
                    last_heartbeat = now
                if reader.poll():
                    try:
                        message = reader.recv()
                    except EOFError:
                        pass
                process.join(timeout=lease.limits.poll_milliseconds / 1000)
            process.join(timeout=1)
            if message is None and reader.poll():
                try:
                    message = reader.recv()
                except EOFError:
                    pass
            if cancellation_seen is not None:
                self.queue.acknowledge_cancel(lease)
            elif failure is not None:
                self.queue.fail(lease, failure)
            elif process.exitcode == 0 and message and message[0] == "ok":
                if not self.queue.complete_diagnostic(lease, message[1]):
                    self.queue.acknowledge_cancel(lease)
            else:
                code: ErrorCode = "JOB_FAILED"
                if message and message[:2] == ("error", "RESOURCE_EXHAUSTED"):
                    code = "RESOURCE_EXHAUSTED"
                self.queue.fail(lease, code)
            logger.info(
                "job_attempt job_id=%s attempt=%s elapsed_seconds=%.6f max_heartbeat_gap=%.6f",
                lease.job_id,
                lease.attempt,
                time.monotonic() - started,
                max_gap,
            )
        except SQLAlchemyError:
            # An outage removes proof of ownership. Stop; recovery uses the persisted deadline.
            cancelled.set()
            stop_child(process, 0)
            logger.warning("Worker stopped handler after database connectivity failure")
        finally:
            stop_child(process, 0)
            reader.close()
            process.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = Settings.from_environment()
    if not settings.database_url:
        raise SystemExit("Worker requires DATABASE_URL")
    verify_container_budget()
    engine = database_engine(settings.database_url)
    worker = Worker(Queue(engine))
    try:
        while True:
            try:
                worked = worker.run_once()
            except SQLAlchemyError:
                logger.warning("Worker database unavailable; no handler publication permitted")
                worked = False
            if not worked:
                time.sleep(0.1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
