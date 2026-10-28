"""Immutable experiment admission and independently sealed core artifact identity."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.persistence.models.workspace import Base


class Experiment(Base):
    __tablename__ = "experiment"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("job.id", ondelete="RESTRICT"), unique=True)
    strategy_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("strategy_version.id", ondelete="RESTRICT")
    )
    snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("dataset_snapshot.id", ondelete="RESTRICT")
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ExperimentCore(Base):
    __tablename__ = "experiment_core"

    experiment_id: Mapped[UUID] = mapped_column(
        ForeignKey("experiment.id", ondelete="RESTRICT"), primary_key=True
    )
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt_token: Mapped[UUID] = mapped_column(nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ExperimentReport(Base):
    __tablename__ = "experiment_report"

    experiment_id: Mapped[UUID] = mapped_column(
        ForeignKey("experiment.id", ondelete="RESTRICT"), primary_key=True
    )
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt_token: Mapped[UUID] = mapped_column(nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
