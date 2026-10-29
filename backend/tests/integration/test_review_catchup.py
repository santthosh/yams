"""Chronological monthly catch-up and actual worker/status proofs; synthetic data only."""

import shutil
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from backend.api.main import create_app
from backend.jobs.catchup import catch_up_reviews
from backend.jobs.queue import Queue
from backend.jobs.registry import JobLimits
from backend.jobs.review_observation import observe_supervisor
from backend.jobs.review_queries import schedule_status
from backend.jobs.worker import Worker
from backend.persistence.database import Settings
from backend.persistence.models.review import PortfolioReviewOccurrence
from backend.portfolio.recommendations import admit_recommendation
from backend.tests.integration.test_bootstrap import database as database
from backend.tests.integration.test_review_admission import waiting_review

pytestmark = pytest.mark.integration
MISSED_MONTHS = [
    "2027-01",
    "2027-02",
    "2027-03",
    "2027-04",
    "2027-05",
    "2027-06",
    "2027-07",
    "2027-08",
    "2027-09",
    "2027-10",
    "2027-11",
    "2027-12",
    "2028-01",
    "2028-02",
    "2028-03",
    "2028-04",
    "2028-05",
    "2028-06",
]


def test_multiple_missed_months_are_recorded_not_backdated_then_current_review_runs(
    database: Engine, tmp_path: Path
) -> None:
    owner, _, request = waiting_review(
        database, tmp_path, initialize=False, opened_at=datetime(2027, 1, 4, 20, tzinfo=UTC)
    )
    queue = Queue(database)
    assert catch_up_reviews(queue, tmp_path) == {"handled": 18, "admitted": 1, "deferred": 0}
    with Session(database) as session:
        rows = list(
            session.scalars(
                select(PortfolioReviewOccurrence)
                .where(PortfolioReviewOccurrence.portfolio_id == owner)
                .order_by(PortfolioReviewOccurrence.decision_session)
            )
        )
        assert [row.decision_session.strftime("%Y-%m") for row in rows[:-1]] == MISSED_MONTHS
        assert all(
            row.outcome == "missed"
            and row.reason == "REVIEW_WINDOW_PASSED"
            and row.recommendation_id is None
            for row in rows[:-1]
        )
        assert rows[-1].decision_session == date(2028, 7, 31) and rows[-1].outcome == "admitted"
        original_id = rows[-1].recommendation_id
    assert catch_up_reviews(queue, tmp_path) == {"handled": 0, "admitted": 0, "deferred": 0}
    manual = admit_recommendation(database, tmp_path, owner, request, idempotency_key=uuid4())
    assert manual.recommendation_id == original_id
    assert Worker(queue, artifact_root=tmp_path).run_once()
    assert Worker(queue, artifact_root=tmp_path).run_once()
    status = schedule_status(database, owner)
    assert status.next_review_session == date(2028, 8, 31) and status.due_backlog is False
    assert status.supervisor.status == "fresh" and status.active_order_batch_id is None
    assert len(status.recent_occurrences) == 19
    assert (
        status.recent_occurrences[0].job is not None
        and status.recent_occurrences[0].job.status == "completed"
    )
    assert status.recent_occurrences[0].handled_clock_at == datetime(2028, 8, 1, 12, 30, tzinfo=UTC)
    with database.connect() as connection:
        assert connection.execute(
            text("SELECT cash_usd,revision FROM paper_portfolio WHERE id=:id"), {"id": owner}
        ).one() == (1000, 3)
        assert connection.execute(text("SELECT count(*) FROM paper_fill")).scalar_one() == 0
        assert (
            connection.execute(
                text("SELECT count(*) FROM job WHERE kind='evaluate_portfolio'")
            ).scalar_one()
            == 1
        )
    settings = Settings(database.url.render_as_string(hide_password=False), artifact_root=tmp_path)
    with TestClient(create_app(settings)) as client:
        path = f"/api/v1/portfolios/{owner}/schedule"
        before = client.get(path)
        assert before.status_code == 200, before.text
        assert before.json()["clock_mode"] == "synthetic_replay"
        assert client.post(path, json={"observed_at": "2030-01-01T00:00:00Z"}).status_code == 405
        assert client.get(f"/api/v1/portfolios/{uuid4()}/schedule").status_code == 404
    with database.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM portfolio_review_occurrence")
            ).scalar_one()
            == 19
        )


def test_small_catchup_budget_defers_remaining_months_without_duplicate_occurrences(
    database: Engine, tmp_path: Path
) -> None:
    owner, _, _ = waiting_review(
        database, tmp_path, initialize=False, opened_at=datetime(2027, 1, 4, 20, tzinfo=UTC)
    )
    queue = Queue(database, limits=JobLimits(catchup_batch=2))
    assert catch_up_reviews(queue, tmp_path) == {"handled": 2, "admitted": 0, "deferred": 0}
    first = schedule_status(database, owner)
    assert first.due_backlog is True and first.next_review_session == date(2027, 3, 31)
    assert len(first.recent_occurrences) == 3 and first.recent_occurrences[0].outcome == "waiting"
    totals = {"handled": 2, "admitted": 0, "deferred": 0}
    for _ in range(9):
        result = catch_up_reviews(queue, tmp_path)
        assert sum(result.values()) <= 2
        totals = {key: totals[key] + result[key] for key in totals}
    assert totals["handled"] == 18 and totals["admitted"] == 1
    with database.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM portfolio_review_occurrence")
            ).scalar_one()
            == 19
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM job WHERE kind='evaluate_portfolio'")
            ).scalar_one()
            == 1
        )


def test_missing_source_waits_without_a_review_job_then_recovers_and_read_is_pure(
    database: Engine, tmp_path: Path
) -> None:
    owner, _, _ = waiting_review(database, tmp_path, initialize=False)
    moved = tmp_path / "unavailable-snapshots"
    shutil.move(tmp_path / "snapshots", moved)
    queue = Queue(database)
    assert catch_up_reviews(queue, tmp_path)["admitted"] == 0
    status = schedule_status(database, owner)
    assert (
        status.last_observed_state == "unavailable"
        and status.reason == "SOURCE_INTEGRITY_UNAVAILABLE"
    )
    assert status.due_backlog is None and status.recent_occurrences == ()
    shutil.move(moved, tmp_path / "snapshots")
    assert catch_up_reviews(queue, tmp_path)["admitted"] == 1
    first = schedule_status(database, owner)
    again = schedule_status(database, owner)
    assert first.recent_occurrences == again.recent_occurrences
    assert first.observed_clock_at == again.observed_clock_at
    with database.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM job WHERE kind='evaluate_portfolio'")
            ).scalar_one()
            == 1
        )


def test_observed_gap_is_durable_not_an_invented_exact_shutdown(
    database: Engine, tmp_path: Path
) -> None:
    owner, _, _ = waiting_review(database, tmp_path, initialize=False)
    observe_supervisor(database, "controlled-observation", 10)
    with database.begin() as connection:
        connection.execute(
            text(
                "UPDATE scheduler_observation SET "
                "first_observed_at=clock_timestamp()-interval '120 seconds', "
                "last_seen_at=clock_timestamp()-interval '60 seconds'"
            )
        )
    observe_supervisor(database, "resumed-observation", 10)
    status = schedule_status(database, owner)
    assert status.last_observed_state == "unobserved" and status.supervisor.status == "fresh"
    assert status.supervisor.last_unobserved_start_at is not None
    assert status.supervisor.last_unobserved_end_at is not None
    assert status.supervisor.last_unobserved_end_at > status.supervisor.last_unobserved_start_at
    assert status.supervisor.limitation == "OBSERVATION_NOT_EXACT_SHUTDOWN"


def test_explicit_manual_cash_review_advances_only_observation_and_reuses_scheduled_work(
    database: Engine, tmp_path: Path
) -> None:
    from backend.tests.integration.test_recommendations import request_for

    owner, original_request = request_for(database, tmp_path)
    request = original_request.model_copy(update={"as_of_session": date(2028, 7, 31), "seed": 42})
    accepted = admit_recommendation(database, tmp_path, owner, request, idempotency_key=uuid4())
    initial = schedule_status(database, owner)
    assert initial.last_explicit_review_cutoff == datetime(2028, 8, 1, 12, 30, tzinfo=UTC)
    assert initial.supervisor.status == "unobserved" and initial.active_order_batch_id is None
    assert catch_up_reviews(Queue(database), tmp_path) == {
        "handled": 0,
        "admitted": 1,
        "deferred": 0,
    }
    current = schedule_status(database, owner)
    assert current.observed_clock_at == initial.last_explicit_review_cutoff
    assert current.recent_occurrences[0].recommendation_id == accepted.recommendation_id
    # An explicit older historical inspection cannot rewind time or pretend its
    # new computation was created at the old logical cutoff.
    older = original_request.model_copy(update={"seed": 42})
    historical = admit_recommendation(database, tmp_path, owner, older, idempotency_key=uuid4())
    assert (
        schedule_status(database, owner).last_explicit_review_cutoff
        == initial.last_explicit_review_cutoff
    )
    with database.connect() as connection:
        requested = connection.execute(
            text("SELECT payload->>'requested_at' FROM recommendation_run WHERE id=:id"),
            {"id": historical.recommendation_id},
        ).scalar_one()
        assert requested == "2028-08-01T12:30:00Z"
        assert (
            connection.execute(
                text("SELECT count(*) FROM job WHERE kind='evaluate_portfolio'")
            ).scalar_one()
            == 2
        )
        assert connection.execute(text("SELECT count(*) FROM paper_order_batch")).scalar_one() == 0
        assert connection.execute(
            text("SELECT cash_usd,revision,last_sequence FROM paper_portfolio WHERE id=:id"),
            {"id": owner},
        ).one() == (1000, 1, 1)


def test_failed_admission_cannot_advance_explicit_clock_but_accepted_cancel_retains_it(
    database: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.portfolio import recommendations as service
    from backend.tests.integration.test_recommendations import request_for

    owner, original_request = request_for(database, tmp_path)
    request = original_request.model_copy(update={"as_of_session": date(2028, 7, 31), "seed": 42})
    original = service._remember_explicit_clock

    def fail_after_flush(
        session: Session, identity: UUID, cutoff: datetime, actual_at: datetime
    ) -> None:
        original(session, identity, cutoff, actual_at)
        raise RuntimeError("controlled explicit observation rollback")

    with monkeypatch.context() as scoped:
        scoped.setattr(service, "_remember_explicit_clock", fail_after_flush)
        with pytest.raises(RuntimeError, match="controlled explicit observation rollback"):
            admit_recommendation(database, tmp_path, owner, request)
    with database.connect() as connection:
        assert (
            connection.execute(text("SELECT count(*) FROM portfolio_review_target")).scalar_one()
            == 0
        )
        assert connection.execute(text("SELECT count(*) FROM recommendation_run")).scalar_one() == 0
        assert (
            connection.execute(
                text("SELECT count(*) FROM job WHERE kind='evaluate_portfolio'")
            ).scalar_one()
            == 0
        )
    accepted = admit_recommendation(database, tmp_path, owner, request)
    assert Queue(database).cancel(accepted.job_id) is not None
    assert schedule_status(database, owner).last_explicit_review_cutoff == datetime(
        2028, 8, 1, 12, 30, tzinfo=UTC
    )


def test_backlog_uses_current_explicit_clock_before_the_next_supervisor_scan(
    database: Engine, tmp_path: Path
) -> None:
    owner, _, request = waiting_review(database, tmp_path, initialize=False)
    queue = Queue(database)
    assert catch_up_reviews(queue, tmp_path)["admitted"] == 1
    assert Worker(queue, artifact_root=tmp_path).run_once()
    assert Worker(queue, artifact_root=tmp_path).run_once()
    before = schedule_status(database, owner)
    assert before.next_review_session == date(2028, 8, 31) and before.due_backlog is False
    later = request.model_copy(update={"as_of_session": date(2028, 8, 31)})
    admit_recommendation(database, tmp_path, owner, later)
    observed = schedule_status(database, owner)
    assert observed.observed_clock_at == before.observed_clock_at
    assert observed.clock_at == datetime(2028, 9, 1, 12, 30, tzinfo=UTC)
    assert observed.due_backlog is True
