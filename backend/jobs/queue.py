"""Short PostgreSQL transactions for durable, fenced job state transitions."""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4, uuid5

from sqlalchemy import Engine, exists, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, aliased

from backend.backtesting.errors import SAFE_BACKTEST_REASONS
from backend.domain.common import ErrorCode, ErrorDetail, JobResult, JobV1
from backend.domain.types import canonical_json
from backend.forecasting.errors import SAFE_FORECAST_REASONS
from backend.jobs.registry import AttemptMetrics, JobLimits, validate_payload
from backend.market_data.providers.yahoo import SAFE_PROVIDER_REASONS
from backend.persistence.models.job import DiagnosticEffect, Job, JobAttempt, Schedule
from backend.portfolio.recommendation_errors import SAFE_RECOMMENDATION_REASONS

TERMINAL = {"completed", "failed", "cancelled"}
TRANSIENT_CODES = {"PROVIDER_UNAVAILABLE"}


class TerminalJobConflict(ValueError):
    pass


class IdempotencyConflict(ValueError):
    pass


@dataclass(frozen=True)
class Lease:
    job_id: UUID
    token: UUID
    attempt: int
    kind: str
    payload: dict[str, Any]
    limits: JobLimits
    deadline: datetime


def database_now(session: Session) -> datetime:
    value = session.execute(select(func.clock_timestamp())).scalar_one()
    assert isinstance(value, datetime)
    return value


class Queue:
    def __init__(
        self,
        engine: Engine,
        clock: Callable[[Session], datetime] = database_now,
        *,
        limits: JobLimits | None = None,
    ):
        self.engine = engine
        self.clock = clock
        self.limits = limits if limits is not None else JobLimits.from_environment()

    def enqueue(
        self,
        kind: str,
        payload: object,
        idempotency_key: UUID,
        *,
        correlation_id: UUID | None = None,
        limits: JobLimits | None = None,
        scheduled_at: datetime | None = None,
    ) -> UUID:
        with Session(self.engine) as session, session.begin():
            return self._enqueue(
                session,
                kind,
                payload,
                idempotency_key,
                correlation_id=correlation_id,
                limits=limits,
                scheduled_at=scheduled_at,
            )

    def _enqueue(
        self,
        session: Session,
        kind: str,
        payload: object,
        idempotency_key: UUID,
        *,
        correlation_id: UUID | None = None,
        limits: JobLimits | None = None,
        scheduled_at: datetime | None = None,
        schedule: Schedule | None = None,
    ) -> UUID:
        validated = validate_payload(kind, payload).model_dump(mode="json")
        source_mode = validated.get("source_mode", "synthetic_fixture")
        effective = limits or self.limits
        if scheduled_at is not None and (
            scheduled_at.tzinfo is None or scheduled_at.utcoffset() != timedelta(0)
        ):
            raise ValueError("Scheduled time must be UTC")
        payload_hash = hashlib.sha256(canonical_json(validated)).hexdigest()
        request_hash = hashlib.sha256(
            canonical_json(
                {
                    "kind": kind,
                    "payload": validated,
                    "limits": effective.model_dump(mode="json"),
                    "scheduled_at": scheduled_at.isoformat() if scheduled_at else None,
                    "source_mode": source_mode,
                    "schedule_id": str(schedule.id) if schedule else None,
                    "schedule_version": schedule.version if schedule else None,
                    "target": schedule.target if schedule else None,
                }
            )
        ).hexdigest()
        now = self.clock(session)
        identity = uuid4()
        inserted = session.execute(
            insert(Job)
            .values(
                id=identity,
                schema_version=1,
                kind=kind,
                payload=validated,
                payload_hash=payload_hash,
                request_hash=request_hash,
                idempotency_key=idempotency_key,
                source_mode=source_mode,
                correlation_id=correlation_id or uuid4(),
                status="queued",
                created_at=now,
                updated_at=now,
                scheduled_at=scheduled_at,
                available_at=max(now, scheduled_at) if scheduled_at else now,
                attempts=0,
                max_attempts=effective.max_attempts,
                progress=0,
                limits=effective.model_dump(mode="json"),
                result=None,
                error=None,
                schedule_id=schedule.id if schedule else None,
                schedule_version=schedule.version if schedule else None,
                occurrence_at=scheduled_at if schedule else None,
                target=schedule.target if schedule else None,
            )
            .on_conflict_do_nothing(index_elements=["idempotency_key"])
            .returning(Job.id)
        ).scalar_one_or_none()
        if inserted is not None:
            return inserted
        original = session.execute(
            select(Job).where(Job.idempotency_key == idempotency_key)
        ).scalar_one()
        if original.request_hash != request_hash:
            raise IdempotencyConflict("Idempotency key refers to different job inputs")
        return original.id

    def create_schedule(
        self,
        kind: str,
        payload: object,
        *,
        target: str,
        first_due_at: datetime,
        interval_seconds: int,
        limits: JobLimits | None = None,
    ) -> UUID:
        validated = validate_payload(kind, payload).model_dump(mode="json")
        if not target or len(target) > 160:
            raise ValueError("Invalid schedule target")
        if type(interval_seconds) is not int or not 5 <= interval_seconds <= 31536000:
            raise ValueError("Invalid schedule interval")
        if first_due_at.tzinfo is None or first_due_at.utcoffset() != timedelta(0):
            raise ValueError("Schedule time must be UTC")
        identity = uuid4()
        with Session(self.engine) as session, session.begin():
            session.add(
                Schedule(
                    id=identity,
                    version=1,
                    target=target,
                    kind=kind,
                    payload=validated,
                    limits=(limits or self.limits).model_dump(mode="json"),
                    interval_seconds=interval_seconds,
                    next_due_at=first_due_at,
                    enabled=True,
                )
            )
        return identity

    def catch_up(self, limit: int = 100) -> int:
        """Atomically enqueue original occurrences and advance their durable cursors."""
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Catch-up batch exceeds bound")
        with Session(self.engine) as session, session.begin():
            # Serialize short scheduler batches to preserve global oldest-first generation.
            if not session.execute(
                text("SELECT pg_try_advisory_xact_lock(1497451861)")
            ).scalar_one():
                return 0
            now = self.clock(session)
            count = 0
            for _ in range(limit):
                schedule = session.execute(
                    select(Schedule)
                    .where(
                        Schedule.enabled.is_(True),
                        Schedule.next_due_at <= now,
                    )
                    .order_by(Schedule.next_due_at, Schedule.id)
                    .with_for_update()
                    .limit(1)
                ).scalar_one_or_none()
                if schedule is None:
                    break
                due = schedule.next_due_at
                self._enqueue(
                    session,
                    schedule.kind,
                    schedule.payload,
                    uuid5(schedule.id, f"{schedule.version}:{due.isoformat()}"),
                    limits=JobLimits.model_validate(schedule.limits),
                    scheduled_at=due,
                    schedule=schedule,
                )
                schedule.next_due_at = due + timedelta(seconds=schedule.interval_seconds)
                session.flush()
                count += 1
            return count

    @staticmethod
    def view(row: Job) -> JobV1:
        return JobV1.model_validate(
            {
                "id": row.id,
                "kind": row.kind,
                "status": row.status,
                "attempts": row.attempts,
                "max_attempts": row.max_attempts,
                "progress": row.progress,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
                "result": row.result,
                "error": row.error,
            }
        )

    def get(self, identity: UUID) -> JobV1 | None:
        with Session(self.engine) as session:
            row = session.get(Job, identity)
            return self.view(row) if row else None

    @staticmethod
    def error(row: Job, code: ErrorCode, retryable: bool = False) -> dict[str, Any]:
        return ErrorDetail(
            code=code,
            message="Job could not complete.",
            details={},
            retryable=retryable,
            correlation_id=row.correlation_id,
        ).model_dump(mode="json")

    @staticmethod
    def finish_attempt(
        session: Session, row: Job, now: datetime, outcome: str, **details: Any
    ) -> None:
        attempt = session.get(JobAttempt, (row.id, row.attempts))
        if attempt is not None:
            attempt.ended_at = now
            attempt.outcome = outcome
            attempt.diagnostics = {**attempt.diagnostics, **details}
        row.lease_token = None
        row.lease_owner = None
        row.lease_expires_at = None
        row.attempt_deadline = None
        row.updated_at = now

    def claim(self, owner: str) -> Lease | None:
        if not owner or len(owner) > 128:
            raise ValueError("Invalid lease owner")
        with Session(self.engine) as session, session.begin():
            now = self.clock(session)
            earlier = aliased(Job)
            unresolved_earlier = exists(
                select(earlier.id).where(
                    earlier.target == Job.target,
                    earlier.scheduled_at < Job.scheduled_at,
                    earlier.status.not_in(TERMINAL),
                )
            )
            row = session.execute(
                select(Job)
                .where(
                    Job.status == "queued",
                    Job.available_at <= now,
                    or_(Job.target.is_(None), ~unresolved_earlier),
                    ~exists(
                        select(Schedule.id).where(
                            Schedule.enabled.is_(True),
                            Schedule.target == Job.target,
                            Schedule.next_due_at < Job.scheduled_at,
                        )
                    ),
                )
                .order_by(Job.available_at, Job.created_at, Job.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            ).scalar_one_or_none()
            if row is None:
                return None
            now = self.clock(session)
            try:
                limits = JobLimits.model_validate(row.limits)
                validate_payload(row.kind, row.payload)
                if hashlib.sha256(canonical_json(row.payload)).hexdigest() != row.payload_hash:
                    raise ValueError("Payload integrity failure")
                if row.attempts >= row.max_attempts:
                    raise ValueError("Attempt budget exhausted")
            except ValueError:
                row.status = "failed"
                row.error = self.error(row, "VALIDATION_ERROR")
                row.updated_at = now
                return None
            row.attempts += 1
            row.status = "running"
            row.progress = 0
            row.updated_at = now
            row.lease_owner = owner
            row.lease_token = uuid4()
            row.heartbeat_at = now
            row.lease_expires_at = now + timedelta(seconds=limits.lease_seconds)
            row.attempt_deadline = now + timedelta(seconds=limits.wall_seconds)
            session.add(
                JobAttempt(
                    job_id=row.id,
                    number=row.attempts,
                    token=row.lease_token,
                    started_at=now,
                    diagnostics={},
                )
            )
            return Lease(
                row.id,
                row.lease_token,
                row.attempts,
                row.kind,
                dict(row.payload),
                limits,
                row.attempt_deadline,
            )

    def owned(self, session: Session, lease: Lease) -> tuple[Job | None, datetime]:
        row = session.execute(
            select(Job).where(Job.id == lease.job_id).with_for_update()
        ).scalar_one_or_none()
        now = self.clock(session)
        if (
            row is None
            or row.status not in {"running", "cancel_requested"}
            or row.lease_token != lease.token
            or row.attempts != lease.attempt
            or row.lease_expires_at is None
            or row.lease_expires_at <= now
        ):
            return None, now
        return row, now

    def heartbeat(self, lease: Lease, progress: float = 0) -> str | None:
        if not 0 <= progress <= 100:
            raise ValueError("Invalid progress")
        with Session(self.engine) as session, session.begin():
            row, now = self.owned(session, lease)
            if row is None or row.attempt_deadline is None or row.attempt_deadline <= now:
                return None
            row.heartbeat_at = now
            limits = JobLimits.model_validate(row.limits)
            row.lease_expires_at = now + timedelta(seconds=limits.lease_seconds)
            row.updated_at = now
            row.progress = progress
            return row.status

    def record_metrics(self, lease: Lease, metrics: AttemptMetrics) -> bool:
        with Session(self.engine) as session, session.begin():
            row, _ = self.owned(session, lease)
            if row is None:
                return False
            attempt = session.get(JobAttempt, (row.id, row.attempts))
            assert attempt is not None
            attempt.diagnostics = {**attempt.diagnostics, **metrics.model_dump(mode="json")}
            return True

    def complete_diagnostic(self, lease: Lease, value: int) -> bool:
        """Seal effect and result atomically; no handler can publish directly."""
        with Session(self.engine) as session, session.begin():
            row, now = self.owned(session, lease)
            if (
                row is None
                or row.status != "running"
                or row.attempt_deadline is None
                or row.attempt_deadline <= now
            ):
                return False
            expected = row.payload["work_units"] * (row.payload["work_units"] - 1) // 2
            if type(value) is not int or value != expected:
                raise ValueError("Invalid diagnostic output")
            session.execute(
                insert(DiagnosticEffect)
                .values(
                    job_id=row.id,
                    value=value,
                    created_at=now,
                )
                .on_conflict_do_nothing(index_elements=["job_id"])
            )
            row.result = JobResult(
                kind="diagnostic", resource_id=None, message="Synthetic diagnostic completed."
            ).model_dump(mode="json")
            row.status = "completed"
            row.progress = 100
            self.finish_attempt(session, row, now, "completed")
            return True

    def fail(
        self,
        lease: Lease,
        code: ErrorCode,
        *,
        retryable: bool = False,
        retry_after: int = 0,
        reason: str | None = None,
    ) -> bool:
        allowed_reasons = (
            SAFE_RECOMMENDATION_REASONS
            if lease.kind == "evaluate_portfolio"
            else SAFE_FORECAST_REASONS
            if lease.kind == "forecast"
            else SAFE_BACKTEST_REASONS
            if lease.kind in {"backtest_core", "backtest"}
            else SAFE_PROVIDER_REASONS
        )
        if reason is not None and reason not in allowed_reasons:
            raise ValueError("Unsupported job failure reason")
        if retry_after < 0:
            raise ValueError("Negative retry-after")
        with Session(self.engine) as session, session.begin():
            row, now = self.owned(session, lease)
            if row is None:
                return False
            if row.status == "cancel_requested":
                row.status = "cancelled"
                self.finish_attempt(session, row, now, "cancelled")
                return True
            retry = retryable and code in TRANSIENT_CODES and row.attempts < row.max_attempts
            delay = min(30, max(2 ** (row.attempts - 1), retry_after))
            row.status = "queued" if retry else "failed"
            row.error = None if retry else self.error(row, code)
            if row.error is not None and reason is not None:
                row.error = {**row.error, "details": {"reason": reason}}
            if retry:
                row.available_at = now + timedelta(seconds=delay)
            self.finish_attempt(
                session,
                row,
                now,
                "retry" if retry else "failed",
                code=code,
                backoff_seconds=delay if retry else 0,
                **({"reason": reason} if reason is not None else {}),
            )
            return True

    def cancel(self, identity: UUID, *, reject_terminal: bool = False) -> JobV1 | None:
        with Session(self.engine) as session, session.begin():
            row = session.execute(
                select(Job).where(Job.id == identity).with_for_update()
            ).scalar_one_or_none()
            if row is None:
                return None
            if reject_terminal and row.status in TERMINAL:
                raise TerminalJobConflict("Job is already terminal")
            now = self.clock(session)
            if row.status not in TERMINAL and row.status != "cancel_requested":
                row.cancel_requested_at = now
                row.updated_at = now
                row.status = "cancelled" if row.status == "queued" else "cancel_requested"
            return self.view(row)

    def acknowledge_cancel(self, lease: Lease) -> bool:
        with Session(self.engine) as session, session.begin():
            row, now = self.owned(session, lease)
            if row is None or row.status != "cancel_requested":
                return False
            row.status = "cancelled"
            self.finish_attempt(session, row, now, "cancelled")
            return True

    def recover(self, limit: int = 100) -> int:
        if not 1 <= limit <= 100:
            raise ValueError("Recovery batch exceeds bound")
        with Session(self.engine) as session, session.begin():
            now = self.clock(session)
            rows = (
                session.execute(
                    select(Job)
                    .where(
                        Job.status.in_(["running", "cancel_requested"]),
                        or_(Job.lease_expires_at <= now, Job.attempt_deadline <= now),
                    )
                    .order_by(Job.created_at, Job.id)
                    .with_for_update(skip_locked=True)
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            for row in rows:
                now = self.clock(session)
                deadline = row.attempt_deadline is not None and row.attempt_deadline <= now
                if row.status == "cancel_requested":
                    row.status = "cancelled"
                    outcome = "cancelled"
                elif deadline or row.attempts >= row.max_attempts:
                    row.status = "failed"
                    row.error = self.error(row, "TIME_LIMIT" if deadline else "JOB_FAILED")
                    outcome = "failed"
                else:
                    row.status = "queued"
                    row.available_at = now + timedelta(seconds=2 ** (row.attempts - 1))
                    outcome = "abandoned"
                self.finish_attempt(
                    session,
                    row,
                    now,
                    outcome,
                    backoff_seconds=2 ** (row.attempts - 1) if outcome == "abandoned" else 0,
                )
            return len(rows)
