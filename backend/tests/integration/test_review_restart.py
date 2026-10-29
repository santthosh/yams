"""Actual PostgreSQL restart retains monthly checkpoints, original jobs/keys and replay time."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

from backend.domain.recommendation_api import RecommendationRequest
from backend.jobs.catchup import catch_up_reviews
from backend.jobs.queue import Queue
from backend.jobs.review_observation import observe_supervisor
from backend.jobs.review_queries import schedule_status
from backend.jobs.worker import Worker
from backend.persistence.database import database_engine
from backend.portfolio.recommendations import admit_recommendation
from backend.tests.integration.test_bootstrap import isolated_url
from backend.tests.integration.test_review_admission import waiting_review

pytestmark = pytest.mark.integration
ROOT = Path("/evidence/monthly-review-artifacts")
RECEIPT = Path("/evidence/monthly-review-restart.json")


def test_prepare_monthly_review_actual_restart() -> None:
    base = database_engine(isolated_url())
    name = "test_monthly_review_" + uuid4().hex[:12]
    with base.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    base.dispose()
    engine = database_engine(
        make_url(isolated_url()).set(database=name).render_as_string(hide_password=False)
    )
    try:
        owner, _, request = waiting_review(
            engine, ROOT, initialize=False, opened_at=datetime(2027, 1, 4, 20, tzinfo=UTC)
        )
        queue = Queue(engine)
        observe_supervisor(engine, "before-actual-restart", 10)
        assert catch_up_reviews(queue, ROOT) == {"handled": 18, "admitted": 1, "deferred": 0}
        key = uuid4()
        accepted = admit_recommendation(engine, ROOT, owner, request, idempotency_key=key)
        status = schedule_status(engine, owner)
        assert status.observed_clock_at is not None and status.supervisor.last_seen_at is not None
        RECEIPT.write_text(
            json.dumps(
                dict(
                    database=name,
                    portfolio=str(owner),
                    key=str(key),
                    request=request.model_dump(mode="json"),
                    accepted=accepted.model_dump(mode="json"),
                    occurrences=[row.model_dump(mode="json") for row in status.recent_occurrences],
                    clock=status.observed_clock_at.isoformat(),
                    last_seen=status.supervisor.last_seen_at.isoformat(),
                )
            )
        )
    finally:
        engine.dispose()


@pytest.mark.restart_verify
def test_monthly_review_checkpoint_original_keys_and_jobs_survive_actual_restart() -> None:
    saved = json.loads(RECEIPT.read_text())
    assert saved["database"].startswith("test_monthly_review_")
    engine = database_engine(
        make_url(isolated_url())
        .set(database=saved["database"])
        .render_as_string(hide_password=False)
    )
    try:
        owner = UUID(saved["portfolio"])
        with ThreadPoolExecutor(max_workers=2) as workers:
            states = list(workers.map(lambda _: schedule_status(engine, owner), range(2)))
        for status in states:
            assert (
                status.observed_clock_at is not None and status.supervisor.last_seen_at is not None
            )
            assert [row.model_dump(mode="json") for row in status.recent_occurrences] == saved[
                "occurrences"
            ]
            assert status.observed_clock_at.isoformat() == saved["clock"]
            assert status.supervisor.last_seen_at.isoformat() == saved["last_seen"]
        accepted = admit_recommendation(
            engine,
            ROOT,
            owner,
            RecommendationRequest.model_validate(saved["request"]),
            idempotency_key=UUID(saved["key"]),
        )
        assert accepted.model_dump(mode="json") == saved["accepted"]
        queue = Queue(engine)
        assert Worker(queue, artifact_root=ROOT).run_once()
        assert Worker(queue, artifact_root=ROOT).run_once()
        assert catch_up_reviews(queue, ROOT) == {"handled": 0, "admitted": 0, "deferred": 0}
        final = schedule_status(engine, owner)
        assert len(final.recent_occurrences) == 19 and final.due_backlog is False
        assert final.observed_clock_at is not None
        assert final.observed_clock_at.isoformat() == saved["clock"]
        assert final.recent_occurrences[0].job is not None
        assert final.recent_occurrences[0].job.id == UUID(saved["accepted"]["job_id"])
        assert final.recent_occurrences[0].job.status == "completed"
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT count(*) FROM job WHERE kind='evaluate_portfolio'")
                ).scalar_one()
                == 1
            )
            assert connection.execute(
                text("SELECT cash_usd,revision FROM paper_portfolio WHERE id=:id"), {"id": owner}
            ).one() == (1000, 3)
            assert connection.execute(text("SELECT count(*) FROM paper_fill")).scalar_one() == 0
    finally:
        engine.dispose()
