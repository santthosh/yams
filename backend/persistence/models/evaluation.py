"""Immutable diagnostic inputs and separately sealed completion evidence."""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.persistence.models.workspace import Base


class StrategyEvaluation(Base):
    __tablename__ = "strategy_evaluation"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("job.id", ondelete="RESTRICT"), unique=True)
    strategy_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("strategy_version.id", ondelete="RESTRICT")
    )
    snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("dataset_snapshot.id", ondelete="RESTRICT")
    )
    as_of_session: Mapped[date] = mapped_column(Date, nullable=False)
    source_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    config_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    calendar_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StrategyEvaluationResult(Base):
    __tablename__ = "strategy_evaluation_result"

    evaluation_id: Mapped[UUID] = mapped_column(
        ForeignKey("strategy_evaluation.id", ondelete="RESTRICT"), primary_key=True
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempt_token: Mapped[UUID] = mapped_column(nullable=False)
