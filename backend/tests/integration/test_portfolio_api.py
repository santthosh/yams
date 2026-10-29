"""Actual paper account HTTP/SQL boundaries; SYNTHETIC_DATA_ONLY evidence."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from backend.api.main import create_app
from backend.domain.portfolio import PortfolioCreateRequest
from backend.persistence.bootstrap import bootstrap
from backend.persistence.database import Settings
from backend.portfolio.accounts import create_account
from backend.strategies.registry import DEFAULT_VERSION_ID
from backend.tests.integration.test_bootstrap import database as database
from backend.tests.integration.test_evaluations import prepare as prepare_snapshot

pytestmark = pytest.mark.integration


def settings(database: Engine, root: Path) -> Settings:
    return Settings(database.url.render_as_string(hide_password=False), artifact_root=root)


def counts(database: Engine) -> dict[str, int]:
    with database.connect() as connection:
        return {
            table: connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
            for table in (
                "paper_portfolio",
                "ledger_event",
                "cash_ledger_entry",
                "position_event",
                "paper_position",
                "paper_fill",
                "paper_order",
                "recommendation",
                "job",
            )
        }


def test_account_creation_exact_retry_and_read_only_pages(database: Engine, tmp_path: Path) -> None:
    source = prepare_snapshot(database, tmp_path)
    key = str(uuid4())
    body = dict(
        name="Independent paper",
        strategy_version_id=str(DEFAULT_VERSION_ID),
        snapshot_id=str(source.snapshot_id),
    )
    with TestClient(create_app(settings(database, tmp_path))) as client:
        assert client.get("/api/v1/portfolios").json()["items"] == []
        created = client.post("/api/v1/portfolios", json=body, headers={"Idempotency-Key": key})
        assert created.status_code == 201, created.text
        account = created.json()
        assert account["cash_usd"] == account["opening_cash_usd"] == "1000.00"
        assert account["holdings"] == [] and account["valuation_mode"] == "synthetic_fixture"
        assert account["valuation"]["total_value_usd"] == "1000.00"
        assert account["valuation"]["cash_weight"] == "1"
        assert account["opening_snapshot_id"] == str(source.snapshot_id)
        again = client.post("/api/v1/portfolios", json=body, headers={"Idempotency-Key": key})
        assert again.status_code == 201 and again.json()["id"] == account["id"]
        assert again.json()["created_at"] == account["created_at"]
        for change in (
            {"opening_cash_usd": "1001.00"},
            {"strategy_version_id": str(uuid4())},
            {"snapshot_id": str(uuid4())},
        ):
            conflict = client.post(
                "/api/v1/portfolios", json=body | change, headers={"Idempotency-Key": key}
            )
            assert (
                conflict.status_code == 409
                and conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
            )
        before = counts(database)
        for _ in range(2):
            assert client.get(f"/api/v1/portfolios/{account['id']}").status_code == 200
            listed = client.get("/api/v1/portfolios?limit=1").json()
            assert listed["items"][0]["id"] == account["id"] and listed["next_cursor"] is None
            history = client.get(f"/api/v1/portfolios/{account['id']}/transactions").json()
            assert history["items"][0]["kind"] == "opening_funding"
            assert history["items"][0]["cash_delta_usd"] == "1000.00"
            assert history["items"][0]["fill"] is None
        assert counts(database) == before
        assert (
            before["paper_portfolio"] == before["ledger_event"] == before["cash_ledger_entry"] == 1
        )
        assert before["paper_fill"] == before["paper_order"] == before["recommendation"] == 0
        for capital in (0, "0.00", "1.001", "NaN", "-1.00"):
            response = client.post(
                "/api/v1/portfolios",
                json=body | {"opening_cash_usd": capital},
                headers={"Idempotency-Key": str(uuid4())},
            )
            assert response.status_code == 422
        for change in ({"strategy_version_id": str(uuid4())}, {"snapshot_id": str(uuid4())}):
            unknown = client.post(
                "/api/v1/portfolios", json=body | change, headers={"Idempotency-Key": str(uuid4())}
            )
            assert unknown.status_code == 404 and unknown.json()["error"]["code"] == "NOT_FOUND"
        wrong_mode = client.post(
            "/api/v1/portfolios",
            json=body | {"mode": "research_market_data"},
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert (
            wrong_mode.status_code == 409 and wrong_mode.json()["error"]["code"] == "STATE_CONFLICT"
        )
        invalid_asset = client.post(
            "/api/v1/portfolios",
            json=body | {"asset_id": "invented"},
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert invalid_asset.status_code == 422
        assert client.post("/api/v1/portfolios", json=body).status_code == 422
        assert client.get(f"/api/v1/portfolios/{uuid4()}").status_code == 404
        assert client.get("/api/v1/portfolios?limit=101").status_code == 422
        assert client.get(f"/api/v1/portfolios?cursor={uuid4()}").status_code == 422
        assert counts(database) == before


def test_concurrent_creation_and_exact_retry_do_not_exhaust_pool(
    database: Engine, tmp_path: Path
) -> None:
    bootstrap(database)
    request = PortfolioCreateRequest(
        name="Concurrent paper", strategy_version_id=DEFAULT_VERSION_ID
    )
    key = uuid4()

    def submit() -> object:
        return create_account(database, tmp_path, request, key)

    with ThreadPoolExecutor(max_workers=2) as workers:
        records = list(workers.map(lambda _: submit(), range(2)))
    assert records[0] == records[1]
    with ThreadPoolExecutor(max_workers=2) as workers:
        retried = list(workers.map(lambda _: submit(), range(2)))
    assert retried == records
    actual = counts(database)
    assert actual["paper_portfolio"] == actual["ledger_event"] == actual["cash_ledger_entry"] == 1
    other = create_account(database, tmp_path, request, uuid4())
    assert other.state.cash_usd == "1000.00"
    assert counts(database)["paper_portfolio"] == 2


def post_authored_fixture_buy(
    database: Engine, root: Path, identity: str, snapshot_id: object
) -> None:
    """Fully linked test-only approval; never creates a production recommendation."""
    from datetime import date
    from uuid import UUID

    from sqlalchemy.orm import Session

    from backend.market_data.catalog import verified_snapshot
    from backend.market_data.repository import MarketRepository
    from backend.persistence.models.ledger import (
        PaperOrder,
        PaperOrderBatch,
        RecommendationReference,
    )
    from backend.persistence.models.snapshot import DatasetSnapshot
    from backend.portfolio.execution import (
        DEFAULT_EXECUTION_POLICY,
        ExecutionContext,
        MarketEvidence,
        OrderIntent,
        calendar_digest,
        next_eligible_session,
    )
    from backend.portfolio.ledger import digest, post_order
    from backend.strategies.clock import decision_cutoff

    account = UUID(identity)
    with Session(database) as session:
        row = session.get(DatasetSnapshot, UUID(str(snapshot_id)))
        assert row is not None
        pinned = verified_snapshot(row, root)
    with MarketRepository(pinned) as repo:
        cutoff = decision_cutoff(repo.calendar, date(2030, 1, 3))
        context = ExecutionContext(
            snapshot_id=pinned.manifest.snapshot_id(),
            snapshot_sha256=pinned.manifest.manifest_hash(),
            calendar_sha256=calendar_digest(repo.calendar),
            mode="synthetic_fixture",
            engine_version="SYNTHETIC_DATA_ONLY",
            execution_mode="historical_replay",
            decision_session=date(2030, 1, 3),
            decision_cutoff=cutoff,
            approved_at=cutoff,
        )
        order = OrderIntent(
            key="SYNTHETIC_DATA_ONLY",
            asset_id="SYN:AAA",
            sector="Technology",
            side="BUY",
            requested_quantity="2.000000",
        )
        intent = {"orders": [order.model_dump(mode="json")]}
        content = {
            "label": "SYNTHETIC_DATA_ONLY",
            "purpose": "explicit #45 valuation test, no production generator",
        }
        rec_id, batch_id, order_id = uuid4(), uuid4(), uuid4()
        with Session(database) as session, session.begin():
            session.add(
                RecommendationReference(
                    id=rec_id,
                    portfolio_id=account,
                    strategy_version_id=DEFAULT_VERSION_ID,
                    snapshot_id=context.snapshot_id,
                    as_of_session=context.decision_session,
                    decision_cutoff=cutoff,
                    portfolio_revision=1,
                    source_mode="synthetic_fixture",
                    content=content,
                    content_sha256=digest(content),
                    disposition="applied",
                    created_at=cutoff,
                )
            )
            session.flush()
            session.add(
                PaperOrderBatch(
                    id=batch_id,
                    portfolio_id=account,
                    recommendation_id=rec_id,
                    strategy_version_id=DEFAULT_VERSION_ID,
                    snapshot_id=context.snapshot_id,
                    snapshot_sha256=context.snapshot_sha256,
                    calendar_sha256=context.calendar_sha256,
                    approved_revision=1,
                    approved_at=cutoff,
                    decision_cutoff=cutoff,
                    eligible_open_at=next_eligible_session(repo.calendar, cutoff, cutoff).open_at,
                    idempotency_key=uuid4(),
                    request_sha256=digest(intent),
                    intent=intent,
                    intent_sha256=digest(intent),
                    context=context.model_dump(mode="json"),
                    policy=DEFAULT_EXECUTION_POLICY.model_dump(mode="json"),
                    status="pending",
                    terminal=False,
                    reason=None,
                    created_at=cutoff,
                )
            )
            session.flush()
            session.add(
                PaperOrder(
                    id=order_id,
                    batch_id=batch_id,
                    ordinal=0,
                    asset_id=order.asset_id,
                    sector=order.sector,
                    side="BUY",
                    intent_key=order.key,
                    requested_quantity=Decimal("2.000000"),
                    filled_quantity=Decimal(0),
                    pending_quantity=Decimal("2.000000"),
                    closed_quantity=Decimal(0),
                    status="pending",
                    terminal=False,
                    reason="WAITING_FOR_ELIGIBLE_OPEN",
                )
            )
        observed = repo.fixture_observation_at(date(2030, 1, 4))
        view = repo.accounting_as_of(observed, date(2030, 1, 4))
        evidence = MarketEvidence(
            snapshot_id=context.snapshot_id,
            snapshot_sha256=context.snapshot_sha256,
            mode="synthetic_fixture",
            freshness="fixture",
            bars=view.bars,
        )
        assert (
            post_order(
                database, order_id, calendar=repo.calendar, market=evidence, observed_at=observed
            )
            is not None
        )


def test_posted_holdings_use_actual_coherent_marks_and_missing_files_are_unavailable(
    database: Engine, tmp_path: Path
) -> None:
    source = prepare_snapshot(database, tmp_path)
    with TestClient(create_app(settings(database, tmp_path))) as client:
        made = client.post(
            "/api/v1/portfolios",
            json={
                "name": "Valued paper",
                "strategy_version_id": str(DEFAULT_VERSION_ID),
                "snapshot_id": str(source.snapshot_id),
            },
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert made.status_code == 201, made.text
        identity = made.json()["id"]
        post_authored_fixture_buy(database, tmp_path, identity, source.snapshot_id)
        before = counts(database)
        response = client.get(f"/api/v1/portfolios/{identity}")
        assert response.status_code == 200, response.text
        actual = response.json()
        # Independently derived from committed inputs: Jan4 raw89 *1.001 *2
        # gives178.18 cents-rounded debit. Latest Dec31 raw101.800 *2=203.60.
        assert actual["cash_usd"] == "821.82"
        assert actual["holdings"][0]["quantity"] == "2.000000"
        assert actual["holdings"][0]["total_basis_usd"] == "178.18"
        assert Decimal(actual["holdings"][0]["mark_price_usd"]) == Decimal("101.800")
        assert actual["holdings"][0]["market_value_usd"] == "203.60"
        assert actual["valuation"]["total_value_usd"] == "1025.42"
        assert actual["valuation"]["as_of_session"] == "2030-12-31"
        assert actual["valuation"]["status"] == "available"
        assert actual["valuation"]["warnings"] == ["SYNTHETIC_DATA_ONLY"]
        history = client.get(f"/api/v1/portfolios/{identity}/transactions?limit=1").json()
        assert history["items"][0]["cash_delta_usd"] == "-178.18"
        assert history["items"][0]["fill"]["quantity"] == "2.000000"
        assert history["next_cursor"] is not None
        older = client.get(
            f"/api/v1/portfolios/{identity}/transactions?limit=1&cursor={history['next_cursor']}"
        ).json()
        assert older["items"][0]["kind"] == "opening_funding" and older["next_cursor"] is None
        assert counts(database) == before
        from sqlalchemy.orm import Session

        from backend.persistence.models.snapshot import DatasetSnapshot

        with Session(database) as session:
            row = session.get(DatasetSnapshot, source.snapshot_id)
            assert row is not None
            manifest = tmp_path / "snapshots" / row.manifest_hash / "manifest.json"
        moved = manifest.with_suffix(".held")
        manifest.rename(moved)
        try:
            missing = client.get(f"/api/v1/portfolios/{identity}").json()
            assert missing["cash_usd"] == "821.82"
            assert missing["valuation"]["status"] == "unavailable"
            assert missing["valuation"]["total_value_usd"] is None
            assert missing["holdings"][0]["market_value_usd"] is None
            assert missing["holdings"][0]["mark_price_usd"] is None
            assert missing["holdings"][0]["reason"] == "SNAPSHOT_UNAVAILABLE"
            assert counts(database) == before
        finally:
            moved.rename(manifest)


def test_pagination_and_source_scoped_cursors_preserve_independent_accounts(
    database: Engine, tmp_path: Path
) -> None:
    bootstrap(database)
    with TestClient(create_app(settings(database, tmp_path))) as client:
        first = client.post(
            "/api/v1/portfolios",
            json={"name": "Fixture capital", "strategy_version_id": str(DEFAULT_VERSION_ID)},
            headers={"Idempotency-Key": str(uuid4())},
        ).json()
        second = client.post(
            "/api/v1/portfolios",
            json={
                "name": "Research capital",
                "strategy_version_id": str(DEFAULT_VERSION_ID),
                "mode": "research_market_data",
                "opening_cash_usd": "2000.00",
            },
            headers={"Idempotency-Key": str(uuid4())},
        ).json()
        before = counts(database)
        page = client.get("/api/v1/portfolios?limit=1").json()
        assert page["items"][0]["id"] == second["id"] and page["next_cursor"] == second["id"]
        old = client.get(f"/api/v1/portfolios?limit=1&cursor={page['next_cursor']}").json()
        assert old["items"][0]["id"] == first["id"] and old["next_cursor"] is None
        fixtures = client.get("/api/v1/portfolios?mode=synthetic_fixture").json()
        assert [item["id"] for item in fixtures["items"]] == [first["id"]]
        assert (
            client.get(
                f"/api/v1/portfolios?mode=synthetic_fixture&cursor={second['id']}"
            ).status_code
            == 422
        )
        history = client.get(f"/api/v1/portfolios/{second['id']}/transactions").json()
        assert (
            client.get(
                f"/api/v1/portfolios/{first['id']}/transactions?cursor={history['items'][0]['id']}"
            ).status_code
            == 422
        )
        assert first["valuation"]["total_value_usd"] == "1000.00"
        assert second["valuation"]["total_value_usd"] == "2000.00"
        assert (
            first["valuation_mode"] == "synthetic_fixture"
            and second["valuation_mode"] == "research_market_data"
        )
        assert counts(database) == before


def test_prepare_account_api_database_restart() -> None:
    import json

    from backend.persistence.database import database_engine
    from backend.tests.integration.test_bootstrap import isolated_url

    engine = database_engine(isolated_url())
    try:
        bootstrap(engine)
        key = str(uuid4())
        body = {
            "name": "SYNTHETIC_DATA_ONLY API restart",
            "strategy_version_id": str(DEFAULT_VERSION_ID),
        }
        with TestClient(create_app(settings(engine, Path("/evidence/portfolio-api")))) as client:
            made = client.post("/api/v1/portfolios", json=body, headers={"Idempotency-Key": key})
            assert made.status_code == 201, made.text
            account = made.json()
            Path("/evidence/portfolio-api.json").write_text(
                json.dumps(
                    {
                        "key": key,
                        "request": body,
                        "id": account["id"],
                        "created_at": account["created_at"],
                    }
                )
            )
    finally:
        engine.dispose()


@pytest.mark.restart_verify
def test_account_api_identity_funding_and_retry_after_actual_database_restart() -> None:
    import json

    from backend.persistence.database import database_engine
    from backend.tests.integration.test_bootstrap import isolated_url

    engine = database_engine(isolated_url())
    try:
        proof = json.loads(Path("/evidence/portfolio-api.json").read_text())
        with TestClient(create_app(settings(engine, Path("/evidence/portfolio-api")))) as client:
            response = client.get(f"/api/v1/portfolios/{proof['id']}")
            assert response.status_code == 200, response.text
            actual = response.json()
            assert actual["cash_usd"] == "1000.00" and actual["holdings"] == []
            assert actual["revision"] == actual["last_sequence"] == 1
            retried = client.post(
                "/api/v1/portfolios",
                json=proof["request"],
                headers={"Idempotency-Key": proof["key"]},
            )
            assert retried.status_code == 201 and retried.json()["id"] == proof["id"]
            assert retried.json()["created_at"] == proof["created_at"]
            history = client.get(f"/api/v1/portfolios/{proof['id']}/transactions").json()
            assert len(history["items"]) == 1 and history["items"][0]["cash_delta_usd"] == "1000.00"
            assert history["next_cursor"] is None
    finally:
        engine.dispose()
