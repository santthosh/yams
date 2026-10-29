"""Public approval and accepted fixture work survive an actual PostgreSQL restart."""

import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

from backend.jobs.queue import Queue
from backend.jobs.worker import Worker
from backend.persistence.database import database_engine
from backend.portfolio.paper_controls import (
    advance_fixture,
    apply_recommendation,
    approval_result,
    batch_detail,
)
from backend.tests.integration.test_bootstrap import isolated_url
from backend.tests.integration.test_paper_controls import computed

pytestmark = pytest.mark.integration
RECEIPT = Path("/evidence/public-paper-controls.json")
ROOT = Path("/evidence/public-paper-controls-artifacts")


def test_prepare_public_paper_controls_restart() -> None:
    base = database_engine(isolated_url())
    name = "test_public_controls_" + uuid4().hex[:12]
    with base.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    base.dispose()
    engine = database_engine(
        make_url(isolated_url()).set(database=name).render_as_string(hide_password=False)
    )
    try:
        _, identity = computed(engine, ROOT)
        key, step_key = uuid4(), uuid4()
        approved = apply_recommendation(engine, ROOT, identity, 1, key)
        step = advance_fixture(Queue(engine), ROOT, approved.batch_id, step_key)
        pending = batch_detail(engine, approved.batch_id).latest_fill_job
        assert pending is not None and pending.status == "queued"
        RECEIPT.write_text(
            json.dumps(
                dict(
                    database=name,
                    recommendation=str(identity),
                    key=str(key),
                    step_key=str(step_key),
                    approval=approved.model_dump(mode="json"),
                    step=step.model_dump(mode="json"),
                )
            )
        )
    finally:
        engine.dispose()


@pytest.mark.restart_verify
def test_public_controls_recover_original_key_and_clock_after_actual_restart() -> None:
    saved = json.loads(RECEIPT.read_text())
    assert saved["database"].startswith("test_public_controls_")
    engine = database_engine(
        make_url(isolated_url())
        .set(database=saved["database"])
        .render_as_string(hide_password=False)
    )
    try:
        identity, key = UUID(saved["recommendation"]), UUID(saved["key"])
        approved = approval_result(engine, identity, key)
        assert approved.model_dump(mode="json") == saved["approval"]
        assert apply_recommendation(engine, ROOT, identity, 1, key) == approved
        queue = Queue(engine)
        step = advance_fixture(queue, ROOT, approved.batch_id, UUID(saved["step_key"]))
        assert step.model_dump(mode="json") == saved["step"]
        state = batch_detail(engine, approved.batch_id)
        assert state.latest_fill_job is not None and state.latest_fill_job.status == "queued"
        assert state.fixture_clock_at == step.fixture_observed_at
        assert Worker(queue, artifact_root=ROOT).run_once()
        after = batch_detail(engine, approved.batch_id)
        assert after.fixture_clock_at == step.fixture_observed_at
        assert after.approved_at == approved.approved_at and after.current_portfolio_revision == 2
        assert approval_result(engine, identity, key) == approved
        assert advance_fixture(queue, ROOT, approved.batch_id, UUID(saved["step_key"])) == step
    finally:
        engine.dispose()
