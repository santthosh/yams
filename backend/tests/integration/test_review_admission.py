"""Actual PostgreSQL manual/scheduled admission races and rollback (SYNTHETIC_DATA_ONLY)."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
from uuid import UUID, uuid4, uuid5

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from backend.domain.recommendation_api import RecommendationAccepted, RecommendationRequest
from backend.jobs.queue import IdempotencyConflict, Queue, database_now
from backend.jobs.review_admission import ScheduledAdmission, link_scheduled_admission
from backend.jobs.review_clock import monthly_anchors
from backend.market_data.models import Calendar
from backend.persistence.models.review import PortfolioReviewOccurrence, PortfolioReviewTarget
from backend.portfolio import recommendations as service
from backend.portfolio.batches import approve_batch, cancel_batch
from backend.portfolio.fills import enqueue_batch_attempt
from backend.portfolio.recommendations import admit_recommendation
from backend.tests.integration.test_bootstrap import database as database
from backend.tests.integration.test_paper_batches import pending_recommendation

pytestmark = pytest.mark.integration


def waiting_review(
    database: Engine, root: Path, *, initialize: bool = True, opened_at: datetime | None = None
) -> tuple[UUID, UUID, RecommendationRequest]:
    owner, private_rec, pinned, cutoff = pending_recommendation(database, root, opened_at=opened_at)
    calendar = Calendar.model_validate_json(
        pinned.artifacts[pinned.manifest.calendar.artifact_path]
    )
    anchor = next(row for row in monthly_anchors(calendar) if row.session == date(2028, 7, 31))
    batch = approve_batch(
        database,
        owner,
        private_rec,
        expected_revision=1,
        idempotency_key=uuid4(),
        pinned=pinned,
        approved_at=cutoff,
    )
    queue = Queue(database)
    clock_job = enqueue_batch_attempt(queue, batch, fixture_observed_at=anchor.due_at)
    assert clock_job is not None
    # Trusted private fixture seam explicitly advances time; cancellation posts no
    # fill and is known exactly at the due cutoff. No HTTP caller clock is added.
    cancel_batch(database, batch, server_clock=True)
    queue.cancel(clock_job)
    identity = uuid5(owner, "monthly-review:" + anchor.session.isoformat())
    if initialize:
        with Session(database) as session, session.begin():
            now = database_now(session)
            session.add(
                PortfolioReviewTarget(
                    portfolio_id=owner,
                    last_handled_session=None,
                    next_session=anchor.session,
                    next_due_at=anchor.due_at,
                    next_window_end_at=anchor.window_end_at,
                    next_calendar_rows=list(anchor.calendar_rows),
                    last_observed_at=now,
                    last_clock_at=anchor.due_at,
                    status="waiting",
                    reason="REVIEW_DUE",
                )
            )
            session.flush()
            session.add(
                PortfolioReviewOccurrence(
                    id=identity,
                    portfolio_id=owner,
                    decision_session=anchor.session,
                    due_at=anchor.due_at,
                    window_end_at=anchor.window_end_at,
                    calendar_rows=list(anchor.calendar_rows),
                    observed_snapshot_id=pinned.manifest.snapshot_id(),
                    observed_snapshot_sha256=pinned.manifest.manifest_hash(),
                    observed_clock_at=anchor.due_at,
                    created_at=now,
                    outcome="waiting",
                    reason="REVIEW_DUE",
                    handled_at=None,
                    handled_clock_at=None,
                    recommendation_id=None,
                    job_id=None,
                )
            )
    return (
        owner,
        identity,
        RecommendationRequest(
            as_of_session=anchor.session,
            snapshot_id=pinned.manifest.snapshot_id(),
            clock_mode="synthetic_replay",
        ),
    )


@pytest.mark.parametrize("first", ["manual", "scheduled", "concurrent"])
def test_equivalent_manual_and_scheduled_review_share_one_original_job(
    database: Engine, tmp_path: Path, first: str
) -> None:
    owner, occurrence, request = waiting_review(database, tmp_path)

    def manual() -> RecommendationAccepted:
        return admit_recommendation(database, tmp_path, owner, request)

    def scheduled() -> RecommendationAccepted:
        return admit_recommendation(
            database, tmp_path, owner, request, schedule_occurrence_id=occurrence
        )

    if first == "concurrent":
        with ThreadPoolExecutor(max_workers=2) as workers:
            futures = [workers.submit(manual), workers.submit(scheduled)]
            results = [future.result() for future in futures]
    else:
        results = [manual(), scheduled()] if first == "manual" else [scheduled(), manual()]
    assert results[0] == results[1]
    original = results[0]
    with Session(database) as session:
        row = session.get(PortfolioReviewOccurrence, occurrence)
        assert row is not None and row.outcome == "admitted"
        assert row.recommendation_id == original.recommendation_id and row.job_id == original.job_id
        target = session.get(PortfolioReviewTarget, owner)
        assert target is not None and target.last_handled_session == request.as_of_session
    with database.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM recommendation_run")).scalar_one() == 1
        assert (
            connection.execute(
                text("SELECT count(*) FROM job WHERE kind='evaluate_portfolio'")
            ).scalar_one()
            == 1
        )
        assert connection.execute(
            text("SELECT cash_usd,revision FROM paper_portfolio WHERE id=:id"), {"id": owner}
        ).one() == (1000, 3)


def test_reused_manual_key_retains_its_own_input_and_recovers_before_files(
    database: Engine, tmp_path: Path
) -> None:
    import shutil

    owner, occurrence, request = waiting_review(database, tmp_path)
    scheduled = admit_recommendation(
        database, tmp_path, owner, request, schedule_occurrence_id=occurrence
    )
    implicit = request.model_copy(update={"snapshot_id": None})
    key = uuid4()
    assert (
        admit_recommendation(database, tmp_path, owner, implicit, idempotency_key=key) == scheduled
    )
    shutil.rmtree(tmp_path / "snapshots")
    assert (
        admit_recommendation(database, tmp_path, owner, implicit, idempotency_key=key) == scheduled
    )
    with pytest.raises(IdempotencyConflict):
        admit_recommendation(database, tmp_path, owner, request, idempotency_key=key)


def test_occurrence_link_failure_rolls_back_job_run_and_checkpoint(
    database: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, occurrence, request = waiting_review(database, tmp_path)
    original = link_scheduled_admission

    def fail_after_flush(
        session: Session, context: ScheduledAdmission, accepted: RecommendationAccepted
    ) -> None:
        original(session, context, accepted)
        raise RuntimeError("controlled after-link failure")

    with monkeypatch.context() as scoped:
        scoped.setattr(service, "link_scheduled_admission", fail_after_flush)
        with pytest.raises(RuntimeError, match="controlled after-link failure"):
            admit_recommendation(
                database, tmp_path, owner, request, schedule_occurrence_id=occurrence
            )
    with database.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM recommendation_run")).scalar_one() == 0
        assert (
            connection.execute(
                text("SELECT count(*) FROM job WHERE kind='evaluate_portfolio'")
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                text("SELECT outcome FROM portfolio_review_occurrence WHERE id=:id"),
                {"id": occurrence},
            ).scalar_one()
            == "waiting"
        )
        assert (
            connection.execute(
                text(
                    "SELECT last_handled_session FROM portfolio_review_target "
                    "WHERE portfolio_id=:id"
                ),
                {"id": owner},
            ).scalar_one()
            is None
        )
    assert admit_recommendation(
        database, tmp_path, owner, request, schedule_occurrence_id=occurrence
    ).job_id
