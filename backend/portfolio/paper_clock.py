"""Server-owned replay clock derived from durable evidence, with actual UTC audit."""

from datetime import datetime
from uuid import UUID

from pydantic import TypeAdapter
from sqlalchemy import DateTime, cast, func, select
from sqlalchemy.orm import Session

from backend.domain.types import SourceMode, UTCTimestamp
from backend.persistence.models.job import Job
from backend.persistence.models.ledger import LedgerEvent
from backend.persistence.models.review import PortfolioReviewTarget


def replay_floor(session: Session, owner: UUID, floor: datetime) -> datetime:
    """Caller holds the portfolio lock for operations; reads are observational.

    Explicit manual review cutoffs and accepted failed/cancelled fill steps
    retain the operator's clock observation. Scheduled reviews never update it.
    PostgreSQL compares timestamps, not lexicographically sorted JSON strings.
    """
    floor = TypeAdapter(UTCTimestamp).validate_python(floor)
    posted = session.scalar(
        select(func.max(LedgerEvent.recorded_at)).where(LedgerEvent.portfolio_id == owner)
    )
    observed = session.scalar(
        select(
            func.max(cast(Job.payload["fixture_observed_at"].as_string(), DateTime(timezone=True)))
        ).where(
            Job.kind == "apply_scheduled_fills",
            Job.source_mode == "synthetic_fixture",
            Job.payload["portfolio_id"].as_string() == str(owner),
        )
    )
    explicit_review = None
    if session.scalar(select(func.to_regclass("portfolio_review_target"))) is not None:
        explicit_review = session.scalar(
            select(PortfolioReviewTarget.last_explicit_review_cutoff).where(
                PortfolioReviewTarget.portfolio_id == owner,
            )
        )
    values = [floor]
    for value in (posted, observed, explicit_review):
        if value is not None:
            values.append(TypeAdapter(UTCTimestamp).validate_python(value))
    return max(values)


def operator_clock(
    session: Session, owner: UUID, mode: SourceMode, floor: datetime
) -> tuple[datetime, datetime]:
    actual = TypeAdapter(UTCTimestamp).validate_python(
        session.execute(select(func.clock_timestamp())).scalar_one()
    )
    return (replay_floor(session, owner, floor) if mode == "synthetic_fixture" else actual), actual


def operator_audit(actual: datetime | None) -> dict[str, str]:
    return (
        {"operator_recorded_at": actual.isoformat().replace("+00:00", "Z")}
        if actual is not None
        else {}
    )
