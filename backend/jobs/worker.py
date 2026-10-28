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
from functools import partial
from multiprocessing.connection import Connection as PipeConnection
from multiprocessing.process import BaseProcess
from multiprocessing.synchronize import Event
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from backend.domain.common import ErrorCode
from backend.jobs.handlers.refresh_market_data import refresh_market_data
from backend.jobs.queue import Lease, Queue
from backend.jobs.registry import AttemptMetrics, DiagnosticPayload, JobLimits
from backend.market_data.providers.yahoo import ProviderFailure
from backend.market_data.snapshots import PublicationFenceError, publish_snapshot
from backend.persistence.database import Settings, database_engine

logger = logging.getLogger(__name__)
Handler = Callable[[dict[str, Any], Event], int | str]


class Cancelled(Exception):
    pass


def diagnostic(payload: dict[str, Any], cancelled: Event) -> int:
    config = DiagnosticPayload.model_validate(payload)
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
    handler: Handler,
    lease: Lease,
    cancelled: Event,
    pipe: PipeConnection,
    parent: int,
    deadline: float,
) -> None:
    # This is server-owned code, never an import path supplied in a payload.
    try:
        os.setsid()
        if ctypes.CDLL(None).prctl(1, signal.SIGKILL, 0, 0, 0) != 0:
            raise RuntimeError("Parent-death protection unavailable")
        if os.getppid() != parent:
            os._exit(1)
        # Kernel wall-clock termination remains active even if the supervisor is waiting on DB I/O.
        signal.signal(signal.SIGALRM, signal.SIG_DFL)
        signal.setitimer(signal.ITIMER_REAL, max(0.001, deadline - time.monotonic()))
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
    except ProviderFailure as error:
        pipe.send(("provider_error", error.reason))
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
    def __init__(
        self,
        queue: Queue,
        handler: Handler = diagnostic,
        *,
        artifact_root: Path = Path("/artifacts"),
    ):
        self.queue = queue
        self.handler = handler
        self.artifact_root = artifact_root
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
                self.schedule_if_due()
                self.queue.recover()
                lease = self.queue.claim(self.owner)
                if lease is None:
                    return False
                self.execute(lease)
                return True
            finally:
                guard.execute(text("SELECT pg_advisory_unlock(1497451860)"))

    def schedule_if_due(self) -> None:
        if time.monotonic() >= self.next_schedule_tick:
            self.queue.catch_up(self.queue.limits.catchup_batch)
            self.next_schedule_tick = time.monotonic() + self.queue.limits.scheduler_tick_seconds

    def execute(self, lease: Lease) -> None:
        handler = self.handler
        stage: Path | None = None
        store = self.artifact_root / "snapshots"
        if lease.kind == "refresh_market_data":
            staging = self.artifact_root / "snapshot-staging"
            staging.mkdir(mode=0o700, parents=True, exist_ok=True)
            store.mkdir(mode=0o700, parents=True, exist_ok=True)
            stage = staging / f"{lease.job_id}-{lease.token}"
            handler = partial(refresh_market_data, stage=stage)
        context = mp.get_context("spawn")
        cancelled = context.Event()
        reader, writer = context.Pipe(duplex=False)
        process = context.Process(
            target=child_entry,
            args=(
                handler,
                lease,
                cancelled,
                writer,
                os.getpid(),
                time.monotonic() + lease.limits.wall_seconds,
            ),
        )
        started = time.monotonic()
        last_heartbeat = started
        max_gap = 0.0
        cancellation_seen: float | None = None
        message: tuple[Any, ...] | None = None
        failure: ErrorCode | None = None
        usage_before = resource.getrusage(resource.RUSAGE_CHILDREN)
        peak_rss: int | None = None
        try:
            try:
                process.start()
            except (OSError, RuntimeError):
                self.queue.fail(lease, "RESOURCE_EXHAUSTED")
                return
            finally:
                writer.close()
            while process.is_alive():
                now = time.monotonic()
                if process.pid is not None:
                    try:
                        for line in Path(f"/proc/{process.pid}/status").read_text().splitlines():
                            if line.startswith("VmHWM:"):
                                peak_rss = max(peak_rss or 0, int(line.split()[1]))
                    except (FileNotFoundError, ProcessLookupError):
                        pass
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
                    heartbeat_done = time.monotonic()
                    max_gap = max(max_gap, heartbeat_done - last_heartbeat)
                    last_heartbeat = heartbeat_done
                self.schedule_if_due()
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
            usage_after = resource.getrusage(resource.RUSAGE_CHILDREN)
            if message and message[0] == "ok":
                peak_rss = max(peak_rss or 0, int(message[2]))
            self.queue.record_metrics(
                lease,
                AttemptMetrics(
                    elapsed_seconds=time.monotonic() - started,
                    max_heartbeat_gap_seconds=max_gap,
                    cpu_seconds=max(
                        0,
                        usage_after.ru_utime
                        + usage_after.ru_stime
                        - usage_before.ru_utime
                        - usage_before.ru_stime,
                    ),
                    peak_rss_kib=peak_rss,
                ),
            )
            if cancellation_seen is not None:
                self.queue.acknowledge_cancel(lease)
            elif failure is not None:
                self.queue.fail(lease, failure)
            elif process.exitcode == 0 and message and message[0] == "ok":
                try:
                    if lease.kind == "refresh_market_data":
                        assert stage is not None
                        if not isinstance(message[1], str):
                            raise ValueError("Invalid refresh completion")
                        publish_snapshot(self.queue, lease, stage, store, message[1])
                    elif not self.queue.complete_diagnostic(lease, message[1]):
                        self.queue.acknowledge_cancel(lease)
                except PublicationFenceError:
                    self.queue.acknowledge_cancel(lease)
                except (ValueError, OSError):
                    self.queue.fail(lease, "VALIDATION_ERROR")
            else:
                code: ErrorCode = "JOB_FAILED"
                if process.exitcode == -signal.SIGALRM:
                    code = "TIME_LIMIT"
                if message and message[:2] == ("error", "RESOURCE_EXHAUSTED"):
                    code = "RESOURCE_EXHAUSTED"
                if message and message[0] == "provider_error":
                    provider = ProviderFailure(message[1])
                    self.queue.fail(
                        lease,
                        "PROVIDER_UNAVAILABLE",
                        retryable=provider.retryable,
                        reason=provider.reason,
                    )
                else:
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
    try:
        limits = JobLimits.from_environment()
    except ValueError:
        raise SystemExit("Invalid YAMS_JOB_LIMITS configuration") from None
    settings = Settings.from_environment()
    if not settings.database_url:
        raise SystemExit("Worker requires DATABASE_URL")
    verify_container_budget()
    engine = database_engine(settings.database_url)
    worker = Worker(Queue(engine, limits=limits), artifact_root=settings.artifact_root)
    try:
        while True:
            try:
                worked = worker.run_once()
            except SQLAlchemyError:
                logger.warning("Worker database unavailable; no handler publication permitted")
                worked = False
            if not worked:
                time.sleep(limits.poll_milliseconds / 1000)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
