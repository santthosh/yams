"""Real Postgres guarantees; all authored records are SYNTHETIC_DATA_ONLY."""

import hashlib
import json
import shutil
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4, uuid5

import pytest
from sqlalchemy import Engine, inspect, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from backend.domain.types import canonical_json
from backend.market_data.models import CorporateAction
from backend.persistence.bootstrap import MIGRATIONS, bootstrap
from backend.persistence.models.ledger import CashEntry, LedgerEvent
from backend.persistence.models.portfolio import PaperPortfolio
from backend.persistence.readiness import read_workspace
from backend.portfolio.execution import MarketEvidence, PortfolioState
from backend.strategies.registry import DEFAULT_STRATEGY_ID, DEFAULT_VERSION_ID, list_versions
from backend.tests.integration.test_bootstrap import database as database

pytestmark = pytest.mark.integration
NOW = datetime(2030, 1, 3, 21, tzinfo=UTC)


def authored_funding(engine: Engine, cash: str = "1000.00") -> tuple[UUID, UUID]:
    """Independently authored valid SQL tuple, not production posting output."""
    workspace = bootstrap(engine)
    identity = uuid4()
    event_id = uuid5(identity, "opening_funding")
    before = PortfolioState(cash_usd="0.00", positions=()).model_dump(mode="json")
    after = PortfolioState(cash_usd=cash, positions=()).model_dump(mode="json")
    payload = {"before": before, "after": after, "command_sha256": "a" * 64}
    with Session(engine) as session, session.begin():
        session.add(
            PaperPortfolio(
                id=identity,
                workspace_id=workspace,
                name="SYNTHETIC_DATA_ONLY",
                currency="USD",
                source_mode="synthetic_fixture",
                strategy_version_id=DEFAULT_VERSION_ID,
                opening_cash_usd=Decimal(cash),
                opening_event_id=event_id,
                opening_sha256="a" * 64,
                cash_usd=Decimal(cash),
                revision=1,
                last_sequence=1,
                status="active",
                reconciliation_failed=False,
                state_metadata={"applied_actions": [], "entitlements": []},
                created_at=NOW,
            )
        )
        session.flush()
        session.add(
            LedgerEvent(
                id=event_id,
                portfolio_id=identity,
                sequence=1,
                portfolio_revision=1,
                kind="opening_funding",
                event_key="opening_funding",
                payload_sha256=hashlib.sha256(canonical_json(payload)).hexdigest(),
                recorded_at=NOW,
                effective_at=NOW,
                order_id=None,
                action_evidence_id=None,
                correction_target_id=None,
                snapshot_id=None,
                strategy_version_id=DEFAULT_VERSION_ID,
                payload=payload,
            )
        )
        session.flush()
        session.add(
            CashEntry(
                id=uuid5(event_id, "cash"),
                event_id=event_id,
                purpose="opening",
                delta_usd=Decimal(cash),
            )
        )
    return identity, event_id


def test_empty_schema_valid_funding_exact_bounds_and_immutable_evidence(database: Engine) -> None:
    identity, event_id = authored_funding(database)
    with Session(database) as session:
        account = session.get(PaperPortfolio, identity)
        assert account is not None and account.cash_usd == Decimal("1000.00")
        assert session.scalar(
            select(CashEntry.delta_usd).where(CashEntry.event_id == event_id)
        ) == Decimal("1000.00")
    for table in ("ledger_event", "cash_ledger_entry"):
        for operation in (f"UPDATE {table} SET id=id", f"DELETE FROM {table}"):
            with pytest.raises(DBAPIError), database.begin() as connection:
                connection.execute(text(operation))
    for invalid in ("-0.01", "NaN", "Infinity"):
        with pytest.raises(DBAPIError), database.begin() as connection:
            connection.execute(
                text("UPDATE paper_portfolio SET cash_usd=CAST(:amount AS numeric) WHERE id=:id"),
                {"amount": invalid, "id": identity},
            )
    with pytest.raises(DBAPIError), database.begin() as connection:
        connection.execute(
            text("UPDATE paper_portfolio SET opening_cash_usd=2000 WHERE id=:id"), {"id": identity}
        )
    with database.connect() as connection:
        assert connection.execute(
            text("SELECT cash_usd FROM paper_portfolio WHERE id=:id"), {"id": identity}
        ).scalar_one() == Decimal("1000.00")
        assert connection.execute(text("SELECT count(*) FROM paper_position")).scalar_one() == 0


def test_incomplete_or_unchained_event_rolls_back_projection_and_all_rows(database: Engine) -> None:
    identity, opening = authored_funding(database)
    for sequence in (2, 3):
        with pytest.raises(DBAPIError), Session(database) as session, session.begin():
            account = session.get(PaperPortfolio, identity)
            assert account is not None
            root = session.get(LedgerEvent, opening)
            assert root is not None
            state = root.payload["after"]
            payload = {"before": state, "after": state, "command_sha256": "b" * 64}
            account.revision = 2
            account.last_sequence = sequence
            session.add(
                LedgerEvent(
                    id=uuid4(),
                    portfolio_id=identity,
                    sequence=sequence,
                    portfolio_revision=2,
                    kind="correction",
                    event_key=f"incomplete-{sequence}",
                    payload_sha256=hashlib.sha256(canonical_json(payload)).hexdigest(),
                    recorded_at=NOW,
                    effective_at=NOW,
                    order_id=None,
                    action_evidence_id=None,
                    correction_target_id=opening,
                    snapshot_id=None,
                    strategy_version_id=DEFAULT_VERSION_ID,
                    payload=payload,
                )
            )
            # No required cash entry. The deferred commit check must reject the
            # entire transition rather than leave an incomplete event/revision.
        with database.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM ledger_event")).scalar_one() == 1
            assert connection.execute(
                text("SELECT revision,last_sequence,cash_usd FROM paper_portfolio WHERE id=:id"),
                {"id": identity},
            ).one() == (1, 1, Decimal("1000.00"))


def test_populated_003_upgrade_preserves_existing_workspace_registry_and_jobs(
    database: Engine, tmp_path: Path
) -> None:
    from backend.jobs.queue import Queue

    prior = tmp_path / "prior"
    shutil.copytree(MIGRATIONS, prior)
    (prior / "versions/0009_portfolio_reviews.py").unlink()
    (prior / "versions/0008_recommendations.py").unlink()
    (prior / "versions/0007_forecasts.py").unlink()
    (prior / "versions/0006_paper_ledger.py").unlink()
    identity = bootstrap(database, prior)
    versions = list_versions(database, DEFAULT_STRATEGY_ID)
    job = Queue(database).enqueue("diagnostic", {"schema_version": 1, "work_units": 10}, uuid4())
    assert "paper_portfolio" not in inspect(database).get_table_names()
    with database.begin() as connection:
        connection.execute(
            text("UPDATE local_workspace SET preferences=CAST(:value AS jsonb)"),
            {"value": json.dumps({"retained": "SYNTHETIC_DATA_ONLY"})},
        )
    assert bootstrap(database) == identity
    assert read_workspace(database).preferences == {"retained": "SYNTHETIC_DATA_ONLY"}
    assert list_versions(database, DEFAULT_STRATEGY_ID) == versions
    assert Queue(database).get(job) is not None
    assert {"paper_portfolio", "ledger_event", "paper_fill"} <= set(
        inspect(database).get_table_names()
    )
    with database.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM recommendation")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM paper_portfolio")).scalar_one() == 0


def test_funding_retry_isolated_accounts_concurrency_and_reconciliation(database: Engine) -> None:
    from concurrent.futures import ThreadPoolExecutor

    from backend.portfolio.ledger import (
        LedgerConflict,
        LedgerView,
        ReconciliationFailure,
        create_portfolio,
        read_portfolio,
        reconcile,
    )

    workspace = bootstrap(database)
    identity = uuid4()

    def fund(account_id: UUID = identity, amount: str = "1000.00") -> LedgerView:
        return create_portfolio(
            database,
            portfolio_id=account_id,
            workspace_id=workspace,
            strategy_version_id=DEFAULT_VERSION_ID,
            name="SYNTHETIC_DATA_ONLY",
            created_at=NOW,
            opening_cash_usd=amount,
        )

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _: fund(), range(2)))
    assert results[0] == results[1]
    assert results[0].revision == results[0].last_sequence == 1
    assert results[0].state == PortfolioState(cash_usd="1000.00", positions=())
    # Decimal-equivalent funding is the same semantic request.
    assert fund(amount="1000") == results[0]
    with pytest.raises(LedgerConflict):
        fund(amount="1001.00")
    other = fund(uuid4())
    assert other.portfolio_id != identity
    for value in ("0.00", "1.001", "NaN", "-1.00", "10000000000000000000000"):
        with pytest.raises(ValueError):
            fund(uuid4(), value)
    with database.connect() as connection:
        # An independent SQL fold verifies funding once, not twice on replay.
        assert connection.execute(text("SELECT count(*) FROM ledger_event")).scalar_one() == 2
        assert connection.execute(
            text("SELECT sum(delta_usd) FROM cash_ledger_entry")
        ).scalar_one() == Decimal("2000.00")
    assert reconcile(database, identity) == results[0]
    with database.begin() as connection:
        connection.execute(
            text("UPDATE paper_portfolio SET cash_usd=999 WHERE id=:id"), {"id": identity}
        )
    with pytest.raises(ReconciliationFailure):
        reconcile(database, identity)
    assert read_portfolio(database, identity).reconciliation_failed
    assert reconcile(database, identity, rebuild=True) == results[0]
    assert read_portfolio(database, other.portfolio_id) == other


def test_funding_write_failures_roll_back_all_effects(database: Engine) -> None:
    from sqlalchemy import event

    from backend.portfolio.ledger import create_portfolio

    workspace = bootstrap(database)
    for target in (
        "INSERT INTO paper_portfolio",
        "INSERT INTO ledger_event",
        "INSERT INTO cash_ledger_entry",
        "UPDATE paper_portfolio",
    ):
        identity = uuid4()

        def fail_after_write(
            connection: object,
            cursor: object,
            statement: str,
            parameters: object,
            context: object,
            executemany: bool,
            failure_target: str = target,
        ) -> None:
            if failure_target in statement:
                raise RuntimeError("Injected failure after durable write boundary")

        event.listen(database, "after_cursor_execute", fail_after_write)
        try:
            with pytest.raises(RuntimeError, match="Injected failure"):
                create_portfolio(
                    database,
                    portfolio_id=identity,
                    workspace_id=workspace,
                    strategy_version_id=DEFAULT_VERSION_ID,
                    name="SYNTHETIC_DATA_ONLY",
                    created_at=NOW,
                )
        finally:
            event.remove(database, "after_cursor_execute", fail_after_write)
        with database.connect() as connection:
            for table in ("paper_portfolio", "ledger_event", "cash_ledger_entry", "paper_position"):
                assert connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0


def seed_batch(
    engine: Engine,
    *,
    identity: UUID | None = None,
    cash: str = "1000.00",
    side: str = "BUY",
    shares: str = "2.000000",
    decision: int = 3,
    extra_buy: bool = False,
) -> tuple[UUID, UUID]:
    """Fully linked synthetic relational fixture, never production recommendation.

    This tests the private posting boundary with authored validated evidence. It
    does not assert filesystem publication (already covered by snapshot tests).
    """
    from backend.domain.market import SnapshotManifestV1
    from backend.persistence.models.ledger import (
        PaperOrder,
        PaperOrderBatch,
        RecommendationReference,
    )
    from backend.persistence.models.snapshot import DatasetSnapshot
    from backend.portfolio.execution import (
        DEFAULT_EXECUTION_POLICY,
        OrderIntent,
        calendar_digest,
        next_eligible_session,
    )
    from backend.portfolio.ledger import create_portfolio, digest, read_portfolio
    from backend.tests.portfolio.test_execution import ROOT, calendar, context

    workspace = bootstrap(engine)
    if identity is None:
        identity = uuid4()
        create_portfolio(
            engine,
            portfolio_id=identity,
            workspace_id=workspace,
            strategy_version_id=DEFAULT_VERSION_ID,
            name="SYNTHETIC_DATA_ONLY",
            opening_cash_usd=cash,
            created_at=NOW,
        )
    manifest_value = json.loads((ROOT / "snapshot/manifest.json").read_text())
    manifest_value["calendar"]["version"] = calendar_digest(calendar())
    manifest_value["coverage"]["asset_ids"] = sorted(
        [*manifest_value["coverage"]["asset_ids"], "A", "B"]
    )
    for artifact in manifest_value["artifacts"]:
        if artifact["role"] == "calendar":
            artifact["sha256"] = calendar_digest(calendar())
    manifest = SnapshotManifestV1.model_validate(manifest_value)
    ctx = context(
        decision=decision,
        snapshot_id=manifest.snapshot_id(),
        snapshot_sha256=manifest.manifest_hash(),
    )
    state = read_portfolio(engine, identity)
    rec, batch, order_id = uuid4(), uuid4(), uuid4()
    intent = OrderIntent.model_validate(
        dict(
            key="authored-order",
            asset_id="A",
            sector="Unknown",
            side=side,
            requested_quantity=shares,
        )
    )
    contents = {"label": "SYNTHETIC_DATA_ONLY", "purpose": "explicit #44 execution fixture"}
    extra_intent = intent.model_copy(
        update={"key": "authored-extra", "asset_id": "B", "side": "BUY"}
    )
    approved_intent = {
        "orders": [
            item.model_dump(mode="json")
            for item in ((intent, extra_intent) if extra_buy else (intent,))
        ]
    }
    with Session(engine) as session, session.begin():
        if session.get(DatasetSnapshot, manifest.snapshot_id()) is None:
            session.add(
                DatasetSnapshot(
                    id=manifest.snapshot_id(),
                    manifest_hash=manifest.manifest_hash(),
                    manifest=manifest.model_dump(mode="json"),
                    source_mode="synthetic_fixture",
                    quality=manifest.quality,
                    registered_at=NOW,
                )
            )
            session.flush()
        session.add(
            RecommendationReference(
                id=rec,
                portfolio_id=identity,
                strategy_version_id=DEFAULT_VERSION_ID,
                snapshot_id=manifest.snapshot_id(),
                as_of_session=ctx.decision_session,
                decision_cutoff=ctx.decision_cutoff,
                portfolio_revision=state.revision,
                source_mode="synthetic_fixture",
                content=contents,
                content_sha256=digest(contents),
                disposition="applied",
                created_at=ctx.approved_at,
            )
        )
        session.flush()
        session.add(
            PaperOrderBatch(
                id=batch,
                portfolio_id=identity,
                recommendation_id=rec,
                strategy_version_id=DEFAULT_VERSION_ID,
                snapshot_id=manifest.snapshot_id(),
                snapshot_sha256=ctx.snapshot_sha256,
                calendar_sha256=ctx.calendar_sha256,
                approved_revision=state.revision,
                approved_at=ctx.approved_at,
                decision_cutoff=ctx.decision_cutoff,
                eligible_open_at=next_eligible_session(
                    calendar(), ctx.decision_cutoff, ctx.approved_at
                ).open_at,
                idempotency_key=uuid4(),
                request_sha256=digest(approved_intent),
                intent=approved_intent,
                intent_sha256=digest(approved_intent),
                context=ctx.model_dump(mode="json"),
                policy=DEFAULT_EXECUTION_POLICY.model_dump(mode="json"),
                status="pending",
                terminal=False,
                reason=None,
                created_at=ctx.approved_at,
            )
        )
        session.flush()
        session.add(
            PaperOrder(
                id=order_id,
                batch_id=batch,
                ordinal=0,
                asset_id="A",
                sector="Unknown",
                side=side,
                intent_key=intent.key,
                requested_quantity=Decimal(shares),
                filled_quantity=Decimal(0),
                pending_quantity=Decimal(shares),
                closed_quantity=Decimal(0),
                status="pending",
                terminal=False,
                reason=None,
            )
        )
        if extra_buy:
            session.add(
                PaperOrder(
                    id=uuid4(),
                    batch_id=batch,
                    ordinal=1,
                    asset_id="B",
                    sector="Unknown",
                    side="BUY",
                    intent_key=extra_intent.key,
                    requested_quantity=Decimal(shares),
                    filled_quantity=Decimal(0),
                    pending_quantity=Decimal(shares),
                    closed_quantity=Decimal(0),
                    status="pending",
                    terminal=False,
                    reason=None,
                )
            )
    return identity, order_id


def evidence_for(
    engine: Engine, order_id: UUID, *, price: str = "100", day: int = 4
) -> MarketEvidence:
    from backend.persistence.models.ledger import PaperOrder, PaperOrderBatch
    from backend.tests.portfolio.test_execution import bar, market

    with Session(engine) as session:
        order = session.get(PaperOrder, order_id)
        assert order is not None
        batch = session.get(PaperOrderBatch, order.batch_id)
        assert batch is not None
        return market(
            bar(day=day, price=price),
            snapshot_id=batch.snapshot_id,
            snapshot_sha256=batch.snapshot_sha256,
        )


def test_fill_retry_concurrency_independent_fold_and_average_basis(database: Engine) -> None:
    from concurrent.futures import ThreadPoolExecutor

    from backend.portfolio.ledger import LedgerConflict, post_order, read_portfolio, reconcile
    from backend.tests.portfolio.test_execution import at, calendar

    identity, order = seed_batch(database)
    evidence = evidence_for(database, order)

    def post() -> UUID | None:
        return post_order(database, order, calendar=calendar(), market=evidence, observed_at=at(4))

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _: post(), range(2)))
    assert results[0] is not None and results[0] == results[1] == post()
    bought = read_portfolio(database, identity)
    assert bought.revision == bought.last_sequence == 2
    assert bought.state.cash_usd == "799.80"
    assert [(p.quantity, p.total_basis_usd) for p in bought.state.positions] == [
        ("2.000000", "200.20")
    ]
    with pytest.raises(LedgerConflict):
        post_order(
            database,
            order,
            calendar=calendar(),
            market=evidence_for(database, order, price="101"),
            observed_at=at(4),
        )
    assert reconcile(database, identity) == bought
    _, sell = seed_batch(database, identity=identity, side="SELL", decision=4)
    post_order(
        database,
        sell,
        calendar=calendar(),
        market=evidence_for(database, sell, day=8),
        observed_at=at(8),
    )
    sold = reconcile(database, identity)
    assert sold.state.cash_usd == "999.60" and sold.state.positions == ()
    with database.connect() as connection:
        # Independent SQL sums, not production replay as its own oracle.
        assert connection.execute(
            text("SELECT sum(delta_usd) FROM cash_ledger_entry")
        ).scalar_one() == Decimal("999.60")
        assert connection.execute(
            text("SELECT sum(quantity_delta),sum(basis_delta_usd) FROM position_event")
        ).one() == (Decimal(0), Decimal(0))
        assert connection.execute(
            text("SELECT count(*),sum(realized_pnl_usd) FROM paper_fill")
        ).one() == (2, Decimal("-0.40"))
        assert connection.execute(text("SELECT count(*) FROM ledger_event")).scalar_one() == 3


def test_cash_constrained_partial_is_terminal_and_missing_open_is_pending(database: Engine) -> None:
    from backend.portfolio.ledger import post_order, read_portfolio
    from backend.tests.portfolio.test_execution import at, calendar

    identity, order = seed_batch(database, cash="100.00", shares="1.000000")
    evidence = evidence_for(database, order)
    missing = evidence.model_copy(update={"bars": ()})
    assert (
        post_order(database, order, calendar=calendar(), market=missing, observed_at=at(4)) is None
    )
    assert read_portfolio(database, identity).state.cash_usd == "100.00"
    posted = post_order(database, order, calendar=calendar(), market=evidence, observed_at=at(4))
    assert posted is not None
    actual = read_portfolio(database, identity)
    assert actual.state.cash_usd == "0.00"
    assert actual.state.positions[0].quantity == "0.999000"
    assert (
        post_order(database, order, calendar=calendar(), market=evidence, observed_at=at(8))
        == posted
    )
    with database.connect() as connection:
        assert connection.execute(
            text(
                "SELECT filled_quantity,closed_quantity,pending_quantity,status,terminal "
                "FROM paper_order WHERE id=:id"
            ),
            {"id": order},
        ).one() == (Decimal("0.999000"), Decimal("0.001000"), Decimal(0), "partially_filled", True)
        assert connection.execute(text("SELECT count(*) FROM paper_fill")).scalar_one() == 1


def test_split_entitlement_payment_correction_and_source_retention(database: Engine) -> None:
    from backend.portfolio.ledger import correct_dividend, post_action, post_order, reconcile
    from backend.tests.portfolio.test_execution import action, at, calendar

    identity, order = seed_batch(database)
    market = evidence_for(database, order)
    post_order(database, order, calendar=calendar(), market=market, observed_at=at(4))
    split = action(effective_session=date(2030, 1, 8))

    def post(source: CorporateAction, day: int) -> UUID | None:
        return post_action(
            database,
            identity,
            snapshot_id=market.snapshot_id,
            action=source,
            calendar=calendar(),
            session_date=date(2030, 1, day),
            observed_at=at(day),
            live=True,
        )

    split_id = post(split, 8)
    assert split_id is not None and post(split, 8) == split_id
    state = reconcile(database, identity).state
    assert state.cash_usd == "799.80"
    assert [(p.quantity, p.total_basis_usd) for p in state.positions] == [("4.000000", "200.20")]
    dividend = action("dividend", effective_session=date(2030, 1, 9))
    entitlement = post(dividend, 9)
    assert entitlement is not None and post(dividend, 9) is None
    assert reconcile(database, identity).state.cash_usd == "799.80"
    # Sell after entitlement: payable recognition must retain the four shares.
    _, sell = seed_batch(database, identity=identity, side="SELL", shares="4.000000", decision=8)
    post_order(
        database,
        sell,
        calendar=calendar(),
        market=evidence_for(database, sell, day=9),
        observed_at=at(9),
    )
    assert reconcile(database, identity).state.positions == ()
    paid = post(dividend, 15)
    assert paid is not None and post(dividend, 15) == paid
    assert reconcile(database, identity).state.cash_usd == "1204.40"
    revised = dividend.model_copy(update={"per_share": "1.00"})
    command = uuid4()
    corrected = correct_dividend(
        database,
        identity,
        target_event_id=paid,
        command_id=command,
        revised_action=revised,
        reason="SYNTHETIC_DATA_ONLY authored revision",
        observed_at=at(15),
    )
    assert (
        correct_dividend(
            database,
            identity,
            target_event_id=paid,
            command_id=command,
            revised_action=revised,
            reason="SYNTHETIC_DATA_ONLY authored revision",
            observed_at=at(15),
        )
        == corrected
    )
    assert reconcile(database, identity).state.cash_usd == "1203.40"
    with pytest.raises(ValueError, match="explicit correction"):
        post(revised, 15)
    with database.connect() as connection:
        assert connection.execute(
            text("SELECT delta_usd FROM cash_ledger_entry WHERE event_id=:id"), {"id": paid}
        ).scalar_one() == Decimal("5.00")
        assert connection.execute(
            text("SELECT delta_usd FROM cash_ledger_entry WHERE event_id=:id"), {"id": corrected}
        ).scalar_one() == Decimal("-1.00")
        assert connection.execute(
            text("SELECT sum(delta_usd) FROM cash_ledger_entry")
        ).scalar_one() == Decimal("1203.40")
    for table in (
        "paper_fill",
        "position_event",
        "paper_action_evidence",
        "dataset_snapshot",
        "strategy_version",
        "recommendation",
        "paper_order_batch",
        "paper_order",
        "paper_portfolio",
    ):
        with pytest.raises(DBAPIError), database.begin() as connection:
            connection.execute(text(f"DELETE FROM {table}"))


def test_post_commit_append_cannot_change_sealed_cash_tuple(database: Engine) -> None:
    _, opening = authored_funding(database)
    with pytest.raises(DBAPIError), database.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO cash_ledger_entry(id,event_id,purpose,delta_usd) "
                "VALUES(:id,:event,'late',1.00)"
            ),
            {"id": uuid4(), "event": opening},
        )
    with database.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM cash_ledger_entry")).scalar_one() == 1


@pytest.mark.parametrize(
    "boundary",
    [
        "INSERT INTO ledger_event",
        "INSERT INTO cash_ledger_entry",
        "INSERT INTO position_event",
        "DELETE FROM paper_position",
        "INSERT INTO paper_position",
        "UPDATE paper_portfolio",
        "INSERT INTO paper_fill",
        "UPDATE paper_order SET",
        "UPDATE paper_order_batch",
    ],
)
def test_each_fill_write_failure_rolls_back_entire_posting(database: Engine, boundary: str) -> None:
    from sqlalchemy import event

    from backend.portfolio.ledger import post_order, read_portfolio
    from backend.tests.portfolio.test_execution import at, calendar

    identity, order = seed_batch(database)
    market = evidence_for(database, order)
    original = read_portfolio(database, identity)

    def fail(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        if boundary in statement:
            raise RuntimeError("Injected fill write failure")

    event.listen(database, "after_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="Injected fill write failure"):
            post_order(database, order, calendar=calendar(), market=market, observed_at=at(4))
    finally:
        event.remove(database, "after_cursor_execute", fail)
    assert read_portfolio(database, identity) == original
    with database.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM ledger_event")).scalar_one() == 1
        assert connection.execute(text("SELECT count(*) FROM cash_ledger_entry")).scalar_one() == 1
        for table in ("position_event", "paper_fill", "paper_position"):
            assert connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0
        assert connection.execute(
            text("SELECT status,terminal,pending_quantity FROM paper_order")
        ).one() == ("pending", False, Decimal("2.000000"))
    # Once the fault disappears, the same semantic command posts normally.
    assert (
        post_order(database, order, calendar=calendar(), market=market, observed_at=at(4))
        is not None
    )


def commit_then_exit(url: str, order_id: UUID, market_json: str) -> None:
    """A real process loses its acknowledgment after the database commits."""
    import os

    from backend.persistence.database import database_engine
    from backend.portfolio.ledger import post_order
    from backend.tests.portfolio.test_execution import at, calendar

    engine = database_engine(url)
    assert (
        post_order(
            engine,
            order_id,
            calendar=calendar(),
            market=MarketEvidence.model_validate_json(market_json),
            observed_at=at(4),
        )
        is not None
    )
    os._exit(19)


def test_process_crash_after_commit_retry_retains_original_approval(database: Engine) -> None:
    import multiprocessing

    from backend.portfolio.ledger import post_order, reconcile
    from backend.tests.portfolio.test_execution import at, calendar

    identity, order = seed_batch(database)
    market = evidence_for(database, order)
    process = multiprocessing.get_context("spawn").Process(
        target=commit_then_exit,
        args=(database.url.render_as_string(hide_password=False), order, market.model_dump_json()),
    )
    process.start()
    process.join(20)
    assert not process.is_alive() and process.exitcode == 19
    replayed = post_order(database, order, calendar=calendar(), market=market, observed_at=at(8))
    assert replayed is not None
    assert reconcile(database, identity).state.cash_usd == "799.80"
    with database.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM paper_fill")).scalar_one() == 1
        assert connection.execute(
            text("SELECT approved_at FROM paper_order_batch")
        ).scalar_one() == at(3)


def test_prepare_paper_ledger_database_restart() -> None:
    from backend.persistence.database import database_engine
    from backend.portfolio.ledger import post_action, post_order, reconcile
    from backend.tests.integration.test_bootstrap import isolated_url
    from backend.tests.portfolio.test_execution import action, at, calendar

    engine = database_engine(isolated_url())
    try:
        identity, order = seed_batch(engine)
        market = evidence_for(engine, order)
        posted = post_order(engine, order, calendar=calendar(), market=market, observed_at=at(4))
        assert posted is not None
        for source, day in (
            (action(effective_session=date(2030, 1, 8)), 8),
            (action("dividend", effective_session=date(2030, 1, 9)), 9),
            (action("dividend", effective_session=date(2030, 1, 9)), 15),
        ):
            assert (
                post_action(
                    engine,
                    identity,
                    snapshot_id=market.snapshot_id,
                    action=source,
                    calendar=calendar(),
                    session_date=date(2030, 1, day),
                    observed_at=at(day),
                    live=True,
                )
                is not None
            )
        view = reconcile(engine, identity)
        Path("/evidence/paper-ledger.json").write_text(
            json.dumps(
                {
                    "portfolio_id": str(identity),
                    "order_id": str(order),
                    "event_id": str(posted),
                    "market": market.model_dump(mode="json"),
                    "state": view.state.model_dump(mode="json"),
                    "revision": view.revision,
                    "last_sequence": view.last_sequence,
                }
            )
        )
    finally:
        engine.dispose()


@pytest.mark.restart_verify
def test_paper_ledger_after_actual_database_restart() -> None:
    from backend.persistence.database import database_engine
    from backend.portfolio.ledger import post_order, reconcile
    from backend.tests.integration.test_bootstrap import isolated_url
    from backend.tests.portfolio.test_execution import at, calendar

    engine = database_engine(isolated_url())
    try:
        proof = json.loads(Path("/evidence/paper-ledger.json").read_text())
        identity = UUID(proof["portfolio_id"])
        actual = reconcile(engine, identity)
        assert actual.state.model_dump(mode="json") == proof["state"]
        assert (
            actual.state.cash_usd == "804.80" and actual.state.positions[0].quantity == "4.000000"
        )
        assert actual.revision == proof["revision"] == 5
        assert actual.last_sequence == proof["last_sequence"] == 5
        assert post_order(
            engine,
            UUID(proof["order_id"]),
            calendar=calendar(),
            market=MarketEvidence.model_validate(proof["market"]),
            observed_at=at(8),
        ) == UUID(proof["event_id"])
        assert reconcile(engine, identity) == actual
    finally:
        engine.dispose()


def test_unsupported_correction_blocks_posting_without_mutating_evidence(database: Engine) -> None:
    from backend.portfolio.ledger import (
        ReconciliationFailure,
        correct_dividend,
        post_order,
        read_portfolio,
    )
    from backend.tests.portfolio.test_execution import action, at, calendar

    identity, order = seed_batch(database)
    market = evidence_for(database, order)
    posted = post_order(database, order, calendar=calendar(), market=market, observed_at=at(4))
    assert posted is not None
    with pytest.raises(ReconciliationFailure):
        correct_dividend(
            database,
            identity,
            target_event_id=posted,
            command_id=uuid4(),
            revised_action=action("dividend"),
            reason="Unsupported fill correction",
            observed_at=at(15),
        )
    state = read_portfolio(database, identity)
    assert state.reconciliation_failed and state.state.cash_usd == "799.80"
    # Already committed exact retries are still recognizable; new financial work
    # is blocked until explicit reconciliation, without deleting the fill.
    assert (
        post_order(database, order, calendar=calendar(), market=market, observed_at=at(15))
        == posted
    )
    _, new_order = seed_batch(database, identity=identity, side="SELL", decision=4)
    with pytest.raises(ReconciliationFailure):
        post_order(
            database,
            new_order,
            calendar=calendar(),
            market=evidence_for(database, new_order, day=8),
            observed_at=at(8),
        )
    with database.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM paper_fill")).scalar_one() == 1
        assert (
            connection.execute(
                text("SELECT count(*) FROM ledger_event WHERE kind='correction'")
            ).scalar_one()
            == 0
        )


def test_competing_buys_never_spend_cash_twice(database: Engine) -> None:
    from concurrent.futures import ThreadPoolExecutor

    from backend.persistence.models.ledger import PaperOrder
    from backend.portfolio.ledger import post_order, reconcile
    from backend.tests.portfolio.test_execution import at, calendar

    identity, first = seed_batch(database, cash="100.00", shares="1.000000", extra_buy=True)
    with Session(database) as session:
        second = session.scalar(select(PaperOrder.id).where(PaperOrder.asset_id == "B"))
        assert second is not None
    evidence = evidence_for(database, first)
    both = evidence.model_copy(
        update={"bars": (evidence.bars[0], evidence.bars[0].model_copy(update={"asset_id": "B"}))}
    )

    def post(order: UUID) -> UUID | None:
        return post_order(database, order, calendar=calendar(), market=both, observed_at=at(4))

    with ThreadPoolExecutor(max_workers=2) as workers:
        list(workers.map(post, (second, first)))
    # If B acquired the lock first it waits for A; otherwise it already records
    # insufficient cash. Either schedule must converge to the same durable state.
    assert post(second) is not None
    state = reconcile(database, identity).state
    assert state.cash_usd == "0.00"
    assert [(row.asset_id, row.quantity) for row in state.positions] == [("A", "0.999000")]
    with database.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM paper_fill")).scalar_one() == 1
        assert connection.execute(
            text("SELECT sum(delta_usd) FROM cash_ledger_entry")
        ).scalar_one() == Decimal(0)
        assert connection.execute(
            text("SELECT status,terminal FROM paper_order WHERE id=:id"), {"id": second}
        ).one() == ("rejected", True)


def test_revised_unpaid_entitlement_cannot_accelerate_payment(database: Engine) -> None:
    from backend.portfolio.ledger import post_action, post_order, reconcile
    from backend.tests.portfolio.test_execution import action, at, calendar

    identity, order = seed_batch(database)
    market = evidence_for(database, order)
    post_order(database, order, calendar=calendar(), market=market, observed_at=at(4))
    original = action("dividend")
    assert (
        post_action(
            database,
            identity,
            snapshot_id=market.snapshot_id,
            action=original,
            calendar=calendar(),
            session_date=date(2030, 1, 8),
            observed_at=at(8),
            live=True,
        )
        is not None
    )
    before = reconcile(database, identity)
    revised = original.model_copy(update={"payable_session": date(2030, 1, 9)})
    with pytest.raises(ValueError, match="explicit correction"):
        post_action(
            database,
            identity,
            snapshot_id=market.snapshot_id,
            action=revised,
            calendar=calendar(),
            session_date=date(2030, 1, 9),
            observed_at=at(9),
            live=True,
        )
    assert reconcile(database, identity) == before


def test_missing_payable_date_can_be_learned_once_without_early_cash(database: Engine) -> None:
    from backend.portfolio.ledger import post_action, post_order, reconcile
    from backend.tests.portfolio.test_execution import action, at, calendar

    identity, order = seed_batch(database)
    market = evidence_for(database, order)
    post_order(database, order, calendar=calendar(), market=market, observed_at=at(4))
    unavailable = action("dividend", payable_session=None)

    def post(source: CorporateAction, day: int) -> UUID | None:
        return post_action(
            database,
            identity,
            snapshot_id=market.snapshot_id,
            action=source,
            calendar=calendar(),
            session_date=date(2030, 1, day),
            observed_at=at(day),
            live=True,
        )

    assert post(unavailable, 8) is not None
    before = reconcile(database, identity)
    learned = action("dividend")
    assert post(learned, 9) is None
    assert reconcile(database, identity) == before
    # Learning the initially absent date is supported. Once observed, moving it
    # earlier is a substantive revision even though no payment has posted yet.
    with pytest.raises(ValueError, match="explicit correction"):
        post(learned.model_copy(update={"payable_session": date(2030, 1, 9)}), 9)
    assert post(learned, 15) is not None
    assert reconcile(database, identity).state.cash_usd == "802.30"


def test_account_source_mode_is_immutable_and_cannot_mix_fixture_fills(database: Engine) -> None:
    from backend.portfolio.ledger import (
        LedgerConflict,
        create_portfolio,
        post_order,
        read_portfolio,
    )
    from backend.tests.portfolio.test_execution import at, calendar

    workspace = bootstrap(database)
    identity = uuid4()
    create_portfolio(
        database,
        portfolio_id=identity,
        workspace_id=workspace,
        strategy_version_id=DEFAULT_VERSION_ID,
        name="research paper capital",
        source_mode="research_market_data",
        created_at=NOW,
    )
    _, order = seed_batch(database, identity=identity)
    with pytest.raises(LedgerConflict, match="lineage"):
        post_order(
            database,
            order,
            calendar=calendar(),
            market=evidence_for(database, order),
            observed_at=at(4),
        )
    assert read_portfolio(database, identity).state == PortfolioState(
        cash_usd="1000.00", positions=()
    )
    with pytest.raises(DBAPIError), database.begin() as connection:
        connection.execute(
            text("UPDATE paper_portfolio SET source_mode='synthetic_fixture' WHERE id=:id"),
            {"id": identity},
        )


def test_concurrent_oversize_sale_revalidates_holdings_and_never_shorts(database: Engine) -> None:
    from concurrent.futures import ThreadPoolExecutor

    from backend.portfolio.ledger import post_order, reconcile
    from backend.tests.portfolio.test_execution import at, calendar

    identity, buy = seed_batch(database)
    post_order(
        database, buy, calendar=calendar(), market=evidence_for(database, buy), observed_at=at(4)
    )
    _, sell = seed_batch(database, identity=identity, side="SELL", shares="5.000000", decision=4)
    evidence = evidence_for(database, sell, day=8)

    def post() -> UUID | None:
        return post_order(database, sell, calendar=calendar(), market=evidence, observed_at=at(8))

    with ThreadPoolExecutor(max_workers=2) as workers:
        result = list(workers.map(lambda _: post(), range(2)))
    assert result[0] is not None and result[0] == result[1]
    assert reconcile(database, identity).state == PortfolioState(cash_usd="999.60", positions=())
    with database.connect() as connection:
        assert connection.execute(
            text("SELECT filled_quantity,closed_quantity,terminal FROM paper_order WHERE id=:id"),
            {"id": sell},
        ).one() == (Decimal("2.000000"), Decimal("3.000000"), True)
        assert connection.execute(text("SELECT count(*) FROM paper_fill")).scalar_one() == 2


def test_negative_cash_correction_is_blocked_without_unexplained_funding(database: Engine) -> None:
    from backend.portfolio.ledger import (
        ReconciliationFailure,
        correct_dividend,
        post_action,
        post_order,
        read_portfolio,
    )
    from backend.tests.portfolio.test_execution import action, at, calendar

    identity, buy = seed_batch(database)
    evidence = evidence_for(database, buy)
    post_order(database, buy, calendar=calendar(), market=evidence, observed_at=at(4))
    dividend = action("dividend", per_share="500.00", payable_session=date(2030, 1, 9))
    for day in (8, 9):
        paid = post_action(
            database,
            identity,
            snapshot_id=evidence.snapshot_id,
            action=dividend,
            calendar=calendar(),
            session_date=date(2030, 1, day),
            observed_at=at(day),
            live=True,
        )
        assert paid is not None
    assert paid is not None
    assert read_portfolio(database, identity).state.cash_usd == "1799.80"
    _, spend = seed_batch(database, identity=identity, shares="1000.000000", decision=9)
    post_order(
        database,
        spend,
        calendar=calendar(),
        market=evidence_for(database, spend, day=15),
        observed_at=at(15),
    )
    assert read_portfolio(database, identity).state.cash_usd == "0.00"
    with pytest.raises(ReconciliationFailure, match="negative cash"):
        correct_dividend(
            database,
            identity,
            target_event_id=paid,
            command_id=uuid4(),
            revised_action=dividend.model_copy(update={"per_share": "0.00"}),
            reason="SYNTHETIC_DATA_ONLY negative compensation",
            observed_at=at(15),
        )
    actual = read_portfolio(database, identity)
    assert actual.state.cash_usd == "0.00" and actual.reconciliation_failed
    with database.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM ledger_event WHERE kind='correction'")
            ).scalar_one()
            == 0
        )
        assert connection.execute(
            text("SELECT delta_usd FROM cash_ledger_entry WHERE event_id=:id"), {"id": paid}
        ).scalar_one() == Decimal("1000.00")


def test_fully_rejected_batch_preserves_domain_required_reason(database: Engine) -> None:
    from backend.portfolio.ledger import post_order, read_portfolio
    from backend.tests.portfolio.test_execution import at, calendar

    identity, order = seed_batch(database, cash="1.00")
    assert (
        post_order(
            database,
            order,
            calendar=calendar(),
            market=evidence_for(database, order),
            observed_at=at(4),
        )
        is not None
    )
    assert read_portfolio(database, identity).state == PortfolioState(cash_usd="1.00", positions=())
    with database.connect() as connection:
        status, terminal, reason = connection.execute(
            text("SELECT status,terminal,reason FROM paper_order_batch")
        ).one()
        assert (status, terminal) == ("rejected", True)
        assert reason == "BELOW_MIN_TRADE"
        assert connection.execute(text("SELECT count(*) FROM paper_fill")).scalar_one() == 0
