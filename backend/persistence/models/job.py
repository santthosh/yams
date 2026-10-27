from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.persistence.models.workspace import Base


class Schedule(Base):
    __tablename__ = "schedule"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(nullable=False)
    target: Mapped[str] = mapped_column(String(160), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    limits: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    interval_seconds: Mapped[int] = mapped_column(nullable=False)
    next_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    enabled: Mapped[bool] = mapped_column(nullable=False)
    __table_args__ = (
        CheckConstraint("version >= 1 AND interval_seconds >= 5", name="ck_schedule_bounds"),
    )


class Job(Base):
    __tablename__ = "job"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    schema_version: Mapped[int] = mapped_column(nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[UUID] = mapped_column(unique=True, nullable=False)
    source_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    correlation_id: Mapped[UUID] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(nullable=False)
    max_attempts: Mapped[int] = mapped_column(nullable=False)
    progress: Mapped[float] = mapped_column(nullable=False)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_token: Mapped[UUID | None]
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    limits: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    schedule_id: Mapped[UUID | None] = mapped_column(ForeignKey("schedule.id", ondelete="RESTRICT"))
    schedule_version: Mapped[int | None]
    occurrence_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    target: Mapped[str | None] = mapped_column(String(160))
    __table_args__ = (
        UniqueConstraint(
            "schedule_id", "schedule_version", "occurrence_at", name="uq_job_occurrence"
        ),
        CheckConstraint(
            "attempts >= 0 AND attempts <= max_attempts AND max_attempts BETWEEN 1 AND 3",
            name="ck_job_attempts",
        ),
        CheckConstraint("progress >= 0 AND progress <= 100", name="ck_job_progress"),
        CheckConstraint(
            "status IN ('queued','running','cancel_requested','completed','failed','cancelled')",
            name="ck_job_status",
        ),
        Index("ix_job_due", "status", "available_at", "created_at", "id"),
    )


class JobAttempt(Base):
    __tablename__ = "job_attempt"
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("job.id", ondelete="RESTRICT"), primary_key=True
    )
    number: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[UUID] = mapped_column(unique=True, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str | None] = mapped_column(String(32))
    diagnostics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class DiagnosticEffect(Base):
    """One harmless sealed diagnostic effect per job, never an investment output."""

    __tablename__ = "job_diagnostic_effect"
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("job.id", ondelete="RESTRICT"), primary_key=True
    )
    value: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
