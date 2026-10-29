"""Readonly composition over actual PostgreSQL, pinned fixtures and genuine worker output."""

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from backend.api.main import create_app
from backend.persistence.database import Settings
from backend.portfolio.decision_context import approval_preview, decision_inputs
from backend.portfolio.paper_controls import apply_recommendation
from backend.tests.integration.test_bootstrap import database as database
from backend.tests.integration.test_paper_controls import computed
from backend.tests.integration.test_recommendations import request_for

pytestmark = pytest.mark.integration


def counts(database: Engine) -> tuple[object, ...]:
    with database.connect() as connection:
        return (
            connection.execute(
                text("""
            SELECT (SELECT count(*) FROM job), (SELECT count(*) FROM ledger_event),
                   (SELECT count(*) FROM recommendation_run),
                   (SELECT count(*) FROM portfolio_review_target),
                   (SELECT cash_usd FROM paper_portfolio LIMIT 1),
                   (SELECT revision FROM paper_portfolio LIMIT 1)
        """)
            )
            .one()
            ._tuple()
        )


def test_suggestion_uses_pinned_calendar_without_advancing_clock_or_admitting_work(
    database: Engine, tmp_path: Path
) -> None:
    owner, request = request_for(database, tmp_path)
    before = counts(database)
    first = decision_inputs(database, tmp_path, owner)
    assert first.suggested_session == request.as_of_session
    assert first.suggested_cutoff_utc == first.clock_at
    assert first.unavailable_reason is None
    assert first.limitation == "CALENDAR_SUPPORT_NOT_PRICE_COMPLETENESS"
    assert decision_inputs(database, tmp_path, owner) == first
    assert counts(database) == before
    settings = Settings(database.url.render_as_string(hide_password=False), artifact_root=tmp_path)
    with TestClient(create_app(settings)) as client:
        result = client.get(f"/api/v1/portfolios/{owner}/decision-inputs")
        assert result.status_code == 200 and result.json() == first.model_dump(mode="json")
        assert (
            client.post(f"/api/v1/portfolios/{owner}/decision-inputs", json={}).status_code == 405
        )
    assert counts(database) == before


def test_indicative_open_is_readonly_and_matches_actual_unchanged_clock_approval(
    database: Engine, tmp_path: Path
) -> None:
    owner, identity = computed(database, tmp_path)
    before = counts(database)
    preview = approval_preview(database, tmp_path, identity)
    assert preview.unavailable_reason is None
    assert preview.expected_revision == 1
    assert counts(database) == before
    actual = apply_recommendation(database, tmp_path, identity, 1, uuid4())
    assert actual.eligible_open_at == preview.indicative_eligible_open_at
    after = counts(database)
    obsolete = approval_preview(database, tmp_path, identity)
    assert obsolete.unavailable_reason == "PORTFOLIO_REVISION_CHANGED"
    assert obsolete.expected_revision == 1
    assert counts(database) == after
    assert after[-2:] == (1000, 2)
    assert obsolete.portfolio_id == owner


def test_missing_registered_snapshot_is_explicit_and_readonly(
    database: Engine, tmp_path: Path
) -> None:
    from datetime import UTC, datetime

    from backend.persistence.bootstrap import bootstrap
    from backend.persistence.readiness import read_workspace
    from backend.portfolio.ledger import create_portfolio
    from backend.strategies.registry import DEFAULT_VERSION_ID

    bootstrap(database)
    owner = uuid4()
    create_portfolio(
        database,
        portfolio_id=owner,
        workspace_id=read_workspace(database).id,
        strategy_version_id=DEFAULT_VERSION_ID,
        name="SYNTHETIC_DATA_ONLY no source",
        created_at=datetime(2028, 7, 18, 12, 30, tzinfo=UTC),
    )
    before = counts(database)
    result = decision_inputs(database, tmp_path, owner)
    assert result.snapshot_id is None
    assert result.suggested_session is None and result.suggested_cutoff_utc is None
    assert result.unavailable_reason == "SNAPSHOT_UNAVAILABLE"
    assert counts(database) == before
