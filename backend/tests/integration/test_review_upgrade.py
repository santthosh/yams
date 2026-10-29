"""Populated0008->0009 upgrade and immutable original review/key bindings."""

import json
import shutil
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from backend.jobs.queue import Queue
from backend.jobs.review_queries import schedule_status
from backend.jobs.worker import Worker
from backend.persistence.bootstrap import MIGRATIONS, bootstrap
from backend.portfolio.recommendation_queries import detail
from backend.portfolio.recommendations import admit_recommendation
from backend.tests.integration import test_evaluations
from backend.tests.integration.test_bootstrap import database as database
from backend.tests.integration.test_recommendations import request_for
from backend.tests.integration.test_review_admission import waiting_review

pytestmark = pytest.mark.integration


def test_populated_0008_upgrade_retains_original_analysis_forecast_and_legacy_request_key(
    database: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prior = tmp_path / "prior-migrations"
    shutil.copytree(MIGRATIONS, prior)
    (prior / "versions/0009_portfolio_reviews.py").unlink()
    root = tmp_path / "artifacts"
    with monkeypatch.context() as scoped:
        scoped.setattr(test_evaluations, "bootstrap", lambda engine: bootstrap(engine, prior))
        owner, request = request_for(database, root)
    key = uuid4()
    accepted = admit_recommendation(database, root, owner, request, idempotency_key=key)
    queue = Queue(database)
    assert Worker(queue, artifact_root=root).run_once()
    assert Worker(queue, artifact_root=root).run_once()
    original = detail(database, root, accepted.recommendation_id)
    assert original is not None and original.forecast is not None
    with database.connect() as connection:
        assert (
            connection.execute(text("SELECT to_regclass('portfolio_review_target')")).scalar_one()
            is None
        )
        before = connection.execute(
            text("SELECT payload FROM recommendation_run WHERE id=:id"),
            {"id": accepted.recommendation_id},
        ).scalar_one()
    bootstrap(database)
    retained = detail(database, root, accepted.recommendation_id)
    assert retained == original
    assert schedule_status(database, owner).last_observed_state == "unobserved"
    shutil.rmtree(root / "snapshots")
    assert admit_recommendation(database, root, owner, request, idempotency_key=key) == accepted
    with database.connect() as connection:
        after = connection.execute(
            text("SELECT payload FROM recommendation_run WHERE id=:id"),
            {"id": accepted.recommendation_id},
        ).scalar_one()
        assert json.dumps(after, sort_keys=True) == json.dumps(before, sort_keys=True)
        assert connection.execute(
            text("SELECT cash_usd,revision FROM paper_portfolio WHERE id=:id"), {"id": owner}
        ).one() == (1000, 1)
        assert (
            connection.execute(
                text("SELECT count(*) FROM recommendation_request_alias")
            ).scalar_one()
            == 0
        )


def test_original_occurrence_and_completed_binding_are_immutable(
    database: Engine, tmp_path: Path
) -> None:
    owner, occurrence, request = waiting_review(database, tmp_path)
    with pytest.raises(DBAPIError), database.begin() as connection:
        connection.execute(
            text(
                "UPDATE portfolio_review_occurrence SET due_at=due_at+interval '1 second' "
                "WHERE id=:id"
            ),
            {"id": occurrence},
        )
    accepted = admit_recommendation(
        database, tmp_path, owner, request, schedule_occurrence_id=occurrence
    )
    key = uuid4()
    assert admit_recommendation(database, tmp_path, owner, request, idempotency_key=key) == accepted
    for sql in [
        "UPDATE portfolio_review_occurrence SET reason='CHANGED' WHERE id=:id",
        "DELETE FROM portfolio_review_occurrence WHERE id=:id",
    ]:
        with pytest.raises(DBAPIError), database.begin() as connection:
            connection.execute(text(sql), {"id": occurrence})
    for sql in [
        "UPDATE recommendation_request_alias SET inputs_canonical_json='{}' "
        "WHERE idempotency_key=:key",
        "DELETE FROM recommendation_request_alias WHERE idempotency_key=:key",
    ]:
        with pytest.raises(DBAPIError), database.begin() as connection:
            connection.execute(text(sql), {"key": key})


def test_explicit_review_clock_and_handled_checkpoint_cannot_rewind(
    database: Engine, tmp_path: Path
) -> None:
    owner, occurrence, request = waiting_review(database, tmp_path)
    admit_recommendation(database, tmp_path, owner, request)
    admit_recommendation(database, tmp_path, owner, request, schedule_occurrence_id=occurrence)
    for sql in [
        "UPDATE portfolio_review_target SET last_explicit_review_cutoff=NULL "
        "WHERE portfolio_id=:id",
        "UPDATE portfolio_review_target SET last_handled_session=NULL WHERE portfolio_id=:id",
        "DELETE FROM portfolio_review_target WHERE portfolio_id=:id",
    ]:
        with pytest.raises(DBAPIError), database.begin() as connection:
            connection.execute(text(sql), {"id": owner})
