"""Actual supervisor observations; an unobserved gap is not an exact shutdown time."""

from datetime import timedelta

from sqlalchemy import Engine, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.jobs.queue import database_now
from backend.jobs.review_admission import review_schema_available
from backend.persistence.models.review import SchedulerObservation


def observe_supervisor(engine: Engine, observer: str, grace_seconds: int) -> None:
    if not observer or len(observer) > 100 or type(grace_seconds) is not int or grace_seconds < 1:
        raise ValueError("Invalid supervisor observation")
    with Session(engine) as session, session.begin():
        if not review_schema_available(session):
            return  # Legacy migration probes; live startup requires the current schema.
        now = database_now(session)
        session.execute(
            insert(SchedulerObservation)
            .values(
                id=1,
                first_observed_at=now,
                last_seen_at=now,
                observer=observer,
                grace_seconds=grace_seconds,
                last_gap_start_at=None,
                last_gap_end_at=None,
            )
            .on_conflict_do_nothing(index_elements=["id"])
        )
        row = session.scalar(
            select(SchedulerObservation).where(SchedulerObservation.id == 1).with_for_update()
        )
        assert row is not None
        if now - row.last_seen_at > timedelta(seconds=grace_seconds):
            row.last_gap_start_at, row.last_gap_end_at = row.last_seen_at, now
        row.last_seen_at = max(now, row.last_seen_at)
        row.observer, row.grace_seconds = observer, grace_seconds
