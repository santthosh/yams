"""Job linkage extends the existing recommendation identity/content aggregate."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.persistence.models.workspace import Base


class RecommendationRun(Base):
    __tablename__ = "recommendation_run"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("job.id", ondelete="RESTRICT"), unique=True)
    portfolio_id: Mapped[UUID] = mapped_column(
        ForeignKey("paper_portfolio.id", ondelete="RESTRICT")
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RecommendationPublication(Base):
    __tablename__ = "recommendation_publication"

    recommendation_id: Mapped[UUID] = mapped_column(
        ForeignKey("recommendation_run.id", ondelete="RESTRICT"),
        ForeignKey("recommendation.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    forecast_id: Mapped[UUID] = mapped_column(
        ForeignKey("forecast.id", ondelete="RESTRICT"), unique=True
    )
    attempt_token: Mapped[UUID] = mapped_column(nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
