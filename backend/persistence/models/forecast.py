"""Immutable forecast admission and independently sealed evidence identity."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.persistence.models.workspace import Base


class Forecast(Base):
    __tablename__ = "forecast"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("job.id", ondelete="RESTRICT"), unique=True)
    portfolio_id: Mapped[UUID] = mapped_column(
        ForeignKey("paper_portfolio.id", ondelete="RESTRICT")
    )
    portfolio_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    strategy_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("strategy_version.id", ondelete="RESTRICT")
    )
    snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("dataset_snapshot.id", ondelete="RESTRICT")
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ForecastArtifact(Base):
    __tablename__ = "forecast_artifact"

    forecast_id: Mapped[UUID] = mapped_column(
        ForeignKey("forecast.id", ondelete="RESTRICT"), primary_key=True
    )
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt_token: Mapped[UUID] = mapped_column(nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
