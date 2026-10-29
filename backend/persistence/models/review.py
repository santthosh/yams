"""Monthly review observations/checkpoints; original financial aggregates remain separate."""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.persistence.models.workspace import Base


class PortfolioReviewTarget(Base):
    __tablename__ = "portfolio_review_target"

    portfolio_id: Mapped[UUID] = mapped_column(
        ForeignKey("paper_portfolio.id", ondelete="RESTRICT"), primary_key=True
    )
    last_explicit_review_cutoff: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_handled_session: Mapped[date | None] = mapped_column(Date)
    next_session: Mapped[date | None] = mapped_column(Date)
    next_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_window_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_calendar_rows: Mapped[list[str] | None] = mapped_column(JSONB)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_clock_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(100))


class PortfolioReviewOccurrence(Base):
    __tablename__ = "portfolio_review_occurrence"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    portfolio_id: Mapped[UUID] = mapped_column(
        ForeignKey("portfolio_review_target.portfolio_id", ondelete="RESTRICT")
    )
    decision_session: Mapped[date] = mapped_column(Date, nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    calendar_rows: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    observed_snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("dataset_snapshot.id", ondelete="RESTRICT")
    )
    observed_snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_clock_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    outcome: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(100))
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    handled_clock_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recommendation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("recommendation_run.id", ondelete="RESTRICT")
    )
    job_id: Mapped[UUID | None] = mapped_column(ForeignKey("job.id", ondelete="RESTRICT"))


class RecommendationRequestAlias(Base):
    __tablename__ = "recommendation_request_alias"

    portfolio_id: Mapped[UUID] = mapped_column(
        ForeignKey("paper_portfolio.id", ondelete="RESTRICT"), primary_key=True
    )
    idempotency_key: Mapped[UUID] = mapped_column(primary_key=True)
    recommendation_id: Mapped[UUID] = mapped_column(
        ForeignKey("recommendation_run.id", ondelete="RESTRICT")
    )
    inputs_canonical_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SchedulerObservation(Base):
    __tablename__ = "scheduler_observation"

    id: Mapped[int] = mapped_column(primary_key=True)
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observer: Mapped[str] = mapped_column(String(100), nullable=False)
    grace_seconds: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_gap_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_gap_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
