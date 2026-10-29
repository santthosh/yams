"""Real PostgreSQL authorization/reservation/cancel proofs, SYNTHETIC_DATA_ONLY."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, Engine, select
from sqlalchemy.orm import Session

from backend.jobs.queue import Queue
from backend.market_data.catalog import verified_snapshot
from backend.market_data.files import PinnedSnapshot
from backend.market_data.models import Calendar
from backend.persistence.models.ledger import (
    LedgerEvent,
    PaperOrder,
    PaperOrderBatch,
    RecommendationReference,
)
from backend.persistence.models.snapshot import DatasetSnapshot
from backend.persistence.readiness import read_workspace
from backend.portfolio.batches import ExecutionIntentV1, approve_batch, cancel_batch
from backend.portfolio.execution import OrderIntent
from backend.portfolio.ledger import LedgerConflict, create_portfolio, digest, read_portfolio
from backend.strategies.clock import decision_cutoff
from backend.strategies.registry import DEFAULT_VERSION_ID
from backend.tests.integration.test_bootstrap import database as database
from backend.tests.integration.test_evaluations import prepare

pytestmark = pytest.mark.integration


def job_status(queue: Queue, identity: UUID) -> str:
    job = queue.get(identity)
    assert job is not None
    return job.status


def pending_recommendation(
    database: Engine, tmp_path: Path, *, decision_only: bool = False, cash: str = "1000.00"
) -> tuple[UUID, UUID, PinnedSnapshot, datetime]:
    source = prepare(database, tmp_path)
    if decision_only:
        source = source.model_copy(
            update={"snapshot_id": publish_decision_only(database, tmp_path, source.as_of_session)}
        )
    with Session(database) as session:
        row = session.get(DatasetSnapshot, source.snapshot_id)
        assert row is not None
        pinned = verified_snapshot(row, tmp_path)
    calendar = Calendar.model_validate_json(
        pinned.artifacts[pinned.manifest.calendar.artifact_path]
    )
    cutoff = decision_cutoff(calendar, source.as_of_session)
    owner = uuid4()
    create_portfolio(
        database,
        portfolio_id=owner,
        workspace_id=read_workspace(database).id,
        strategy_version_id=DEFAULT_VERSION_ID,
        name="SYNTHETIC_DATA_ONLY",
        opening_cash_usd=cash,
        created_at=cutoff,
    )
    intent = ExecutionIntentV1(
        engine_version="authored-test-1",
        orders=(
            OrderIntent(
                key="BUY:SYN:AAA",
                asset_id="SYN:AAA",
                sector="Technology",
                side="BUY",
                requested_quantity="2.000000",
            ),
        ),
    )
    rec_id = uuid4()
    content = {"label": "SYNTHETIC_DATA_ONLY", "execution_intent": intent.model_dump(mode="json")}
    with Session(database) as session, session.begin():
        session.add(
            RecommendationReference(
                id=rec_id,
                portfolio_id=owner,
                strategy_version_id=DEFAULT_VERSION_ID,
                snapshot_id=source.snapshot_id,
                as_of_session=source.as_of_session,
                decision_cutoff=cutoff,
                portfolio_revision=1,
                source_mode="synthetic_fixture",
                content=content,
                content_sha256=digest(content),
                disposition="ready",
                created_at=cutoff,
            )
        )
    return owner, rec_id, pinned, cutoff


def test_approval_is_one_reservation_not_a_fill_and_retry_preserves_time(
    database: Engine, tmp_path: Path
) -> None:
    owner, rec, pinned, cutoff = pending_recommendation(database, tmp_path)
    key = uuid4()
    batch = approve_batch(
        database,
        owner,
        rec,
        expected_revision=1,
        idempotency_key=key,
        pinned=pinned,
        approved_at=cutoff,
    )
    state = read_portfolio(database, owner)
    assert state.state.cash_usd == "1000.00" and not state.state.positions
    assert state.revision == 2
    assert (
        approve_batch(
            database,
            owner,
            rec,
            expected_revision=1,
            idempotency_key=key,
            pinned=pinned,
            approved_at=cutoff + timedelta(days=5),
        )
        == batch
    )
    assert approve_batch(database, owner, rec, expected_revision=1, idempotency_key=key) == batch
    with Session(database) as session:
        stored = session.get(PaperOrderBatch, batch)
        assert stored is not None and stored.approved_at == cutoff and not stored.terminal
        assert stored.eligible_open_at > cutoff
        assert len(list(session.scalars(select(PaperOrder)))) == 1
        assert len(list(session.scalars(select(LedgerEvent)))) == 2
    with pytest.raises(LedgerConflict, match="different inputs"):
        approve_batch(
            database,
            owner,
            rec,
            expected_revision=2,
            idempotency_key=key,
            pinned=pinned,
            approved_at=cutoff,
        )
    with pytest.raises(LedgerConflict):
        approve_batch(
            database,
            owner,
            rec,
            expected_revision=2,
            idempotency_key=uuid4(),
            pinned=pinned,
            approved_at=cutoff,
        )
    assert cancel_batch(database, batch, cancelled_at=cutoff + timedelta(seconds=1)) == batch
    assert cancel_batch(database, batch, cancelled_at=cutoff + timedelta(seconds=2)) == batch
    after = read_portfolio(database, owner)
    assert after.state == state.state and after.revision == 3
    with Session(database) as session:
        order = session.scalar(select(PaperOrder).where(PaperOrder.batch_id == batch))
        assert order is not None and order.terminal and order.status == "cancelled"
        assert str(order.closed_quantity) == "2.000000" and order.pending_quantity == 0


def test_concurrent_approval_same_key_is_one_batch_and_distinct_key_cannot_reauthorize(
    database: Engine, tmp_path: Path
) -> None:
    owner, rec, pinned, cutoff = pending_recommendation(database, tmp_path)
    key = uuid4()

    def approve(_: int) -> UUID:
        return approve_batch(
            database,
            owner,
            rec,
            expected_revision=1,
            idempotency_key=key,
            pinned=pinned,
            approved_at=cutoff,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        identities = list(pool.map(approve, range(2)))
    assert identities[0] == identities[1]
    assert read_portfolio(database, owner).revision == 2
    with pytest.raises(LedgerConflict):
        approve_batch(
            database,
            owner,
            rec,
            expected_revision=1,
            idempotency_key=uuid4(),
            pinned=pinned,
            approved_at=cutoff,
        )


def test_late_approval_selects_later_validated_open(database: Engine, tmp_path: Path) -> None:
    owner, rec, pinned, cutoff = pending_recommendation(database, tmp_path)
    calendar = Calendar.model_validate_json(
        pinned.artifacts[pinned.manifest.calendar.artifact_path]
    )
    first = next(row for row in calendar.sessions if row.open_at > cutoff)
    batch = approve_batch(
        database,
        owner,
        rec,
        expected_revision=1,
        idempotency_key=uuid4(),
        pinned=pinned,
        approved_at=first.open_at + timedelta(seconds=1),
    )
    with Session(database) as session:
        row = session.get(PaperOrderBatch, batch)
        assert row is not None and row.eligible_open_at > first.open_at
        assert row.decision_cutoff == cutoff


def test_supervised_fill_commits_one_truthful_job_and_exact_posting(
    database: Engine, tmp_path: Path
) -> None:
    from backend.jobs.queue import Queue
    from backend.jobs.worker import Worker
    from backend.persistence.models.ledger import PaperFill
    from backend.portfolio.fills import enqueue_batch_attempt

    owner, rec, pinned, cutoff = pending_recommendation(database, tmp_path)
    batch = approve_batch(
        database,
        owner,
        rec,
        expected_revision=1,
        idempotency_key=uuid4(),
        pinned=pinned,
        approved_at=cutoff,
    )
    calendar = Calendar.model_validate_json(
        pinned.artifacts[pinned.manifest.calendar.artifact_path]
    )
    eligible = next(row for row in calendar.sessions if row.open_at > cutoff)
    queue = Queue(database)
    assert enqueue_batch_attempt(queue, batch, fixture_observed_at=cutoff) is None
    identity = enqueue_batch_attempt(
        queue, batch, fixture_observed_at=eligible.close_at + timedelta(seconds=1)
    )
    assert identity is not None
    assert Worker(queue, artifact_root=tmp_path).run_once()
    job = queue.get(identity)
    assert job is not None and job.status == "completed", job
    result = read_portfolio(database, owner)
    # Authored fixture raw70.050 ×1.001×2 =140.24010 ->140.24 debit.
    assert result.state.cash_usd == "859.76"
    assert result.state.positions[0].quantity == "2.000000"
    assert result.state.positions[0].total_basis_usd == "140.24"
    assert result.revision == 3
    with Session(database) as session:
        assert len(list(session.scalars(select(PaperFill)))) == 1
        stored = session.get(PaperOrderBatch, batch)
        assert stored is not None and stored.status == "filled" and stored.terminal
    assert (
        enqueue_batch_attempt(
            queue, batch, fixture_observed_at=eligible.close_at + timedelta(seconds=2)
        )
        is None
    )
    assert cancel_batch(database, batch) == batch
    assert read_portfolio(database, owner) == result


def test_cancellation_wins_fenced_publication_without_posting(
    database: Engine, tmp_path: Path
) -> None:
    import multiprocessing as mp

    from backend.jobs.handlers.apply_scheduled_fills import apply_scheduled_fills
    from backend.jobs.queue import Queue
    from backend.market_data.snapshots import PublicationFenceError
    from backend.portfolio.fills import enqueue_batch_attempt, seal_fill

    owner, rec, pinned, cutoff = pending_recommendation(database, tmp_path)
    batch = approve_batch(
        database,
        owner,
        rec,
        expected_revision=1,
        idempotency_key=uuid4(),
        pinned=pinned,
        approved_at=cutoff,
    )
    calendar = Calendar.model_validate_json(
        pinned.artifacts[pinned.manifest.calendar.artifact_path]
    )
    eligible = next(row for row in calendar.sessions if row.open_at > cutoff)
    queue = Queue(database)
    job_id = enqueue_batch_attempt(
        queue, batch, fixture_observed_at=eligible.close_at + timedelta(seconds=1)
    )
    assert job_id is not None
    lease = queue.claim("cancel-first")
    assert lease is not None
    value = apply_scheduled_fills(lease.payload, mp.get_context("spawn").Event(), root=tmp_path)
    queue.cancel(job_id)
    with pytest.raises(PublicationFenceError):
        seal_fill(queue, lease, value)
    assert read_portfolio(database, owner).state.cash_usd == "1000.00"
    assert not read_portfolio(database, owner).state.positions
    cancel_batch(database, batch, cancelled_at=eligible.close_at)


def publish_decision_only(database: Engine, root: Path, session_date: date) -> UUID:
    """Independently slice committed synthetic prices, then publish real artifacts."""
    import hashlib
    import json
    import shutil

    import duckdb

    from backend.domain.market import SnapshotManifestV1
    from backend.domain.types import canonical_json
    from backend.jobs.queue import Queue
    from backend.market_data.snapshots import publish_snapshot
    from backend.tests.market_data.test_files import FIXTURES

    stage = root / "decision-stage"
    shutil.copytree(FIXTURES / "snapshot", stage)
    with duckdb.connect() as connection:
        connection.execute(
            "CREATE TABLE bars AS SELECT * FROM read_parquet(?) WHERE session_date<=?",
            [str(stage / "bars.parquet"), session_date],
        )
        count_row = connection.execute("SELECT count(*) FROM bars").fetchone()
        assert count_row is not None
        count = count_row[0]
        (stage / "bars.parquet").unlink()
        connection.execute("COPY bars TO ? (FORMAT PARQUET)", [str(stage / "bars.parquet")])
    value = json.loads((stage / "manifest.json").read_text())
    value["coverage"]["last_session"] = session_date.isoformat()
    value["coverage"]["latest_completed_session"] = session_date.isoformat()
    for artifact in value["artifacts"]:
        if artifact["role"] == "bars":
            data = (stage / artifact["path"]).read_bytes()
            artifact.update(
                sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data), row_count=count
            )
    manifest = SnapshotManifestV1.model_validate(value)
    (stage / "manifest.json").write_bytes(canonical_json(manifest.model_dump(mode="json")))
    queue = Queue(database)
    queue.enqueue(
        "refresh_market_data",
        dict(
            schema_version=1,
            source_mode="synthetic_fixture",
            expected_manifest_hash=manifest.manifest_hash(),
        ),
        uuid4(),
    )
    lease = queue.claim("decision-only-test")
    assert lease is not None
    return publish_snapshot(queue, lease, stage, root / "snapshots", manifest.manifest_hash())


def test_two_immutable_snapshots_fill_without_future_decision_prices(
    database: Engine, tmp_path: Path
) -> None:
    import hashlib

    from backend.jobs.queue import Queue
    from backend.jobs.worker import Worker
    from backend.market_data.repository import MarketRepository
    from backend.persistence.models.ledger import PaperFill
    from backend.portfolio.fills import enqueue_batch_attempt
    from backend.tests.market_data.test_files import IDENTITY

    owner, rec, pinned, cutoff = pending_recommendation(database, tmp_path, decision_only=True)
    decision_hash = pinned.manifest.manifest_hash()
    assert decision_hash != IDENTITY
    before = hashlib.sha256(
        (tmp_path / "snapshots" / decision_hash / "bars.parquet").read_bytes()
    ).hexdigest()
    latest = pinned.manifest.coverage.latest_completed_session
    assert latest is not None
    with MarketRepository(pinned) as repository:
        assert all(row.session_date <= latest for row in repository._rows.values())
    batch = approve_batch(
        database,
        owner,
        rec,
        expected_revision=1,
        idempotency_key=uuid4(),
        pinned=pinned,
        approved_at=cutoff,
    )
    # The next publication is the full, independently authored committed fixture.
    execution = prepare(database, tmp_path)
    calendar = Calendar.model_validate_json(
        pinned.artifacts[pinned.manifest.calendar.artifact_path]
    )
    eligible = next(row for row in calendar.sessions if row.open_at > cutoff)
    queue = Queue(database)
    job = enqueue_batch_attempt(
        queue, batch, fixture_observed_at=eligible.close_at + timedelta(seconds=1)
    )
    assert job is not None and Worker(queue, artifact_root=tmp_path).run_once()
    assert job_status(queue, job) == "completed"
    result = read_portfolio(database, owner)
    assert result.state.cash_usd == "859.76" and result.revision == 3
    assert (
        hashlib.sha256(
            (tmp_path / "snapshots" / decision_hash / "bars.parquet").read_bytes()
        ).hexdigest()
        == before
    )
    with Session(database) as session:
        original = session.get(PaperOrderBatch, batch)
        assert (
            original is not None
            and original.snapshot_sha256 == decision_hash
            and original.approved_at == cutoff
        )
        fill = session.scalar(select(PaperFill))
        assert fill is not None
        event = session.get(LedgerEvent, fill.event_id)
        assert event is not None
        assert (
            event.snapshot_id == execution.snapshot_id and event.snapshot_id != original.snapshot_id
        )
        assert event.payload["details"]["execution"]["context"]["execution_snapshot_id"] == str(
            execution.snapshot_id
        )
        assert event.payload["details"]["execution"]["context"]["snapshot_id"] == str(
            original.snapshot_id
        )


def test_job_result_write_failure_rolls_back_entire_fill_then_exact_retry(
    database: Engine, tmp_path: Path
) -> None:
    import multiprocessing as mp

    from sqlalchemy import event

    from backend.jobs.handlers.apply_scheduled_fills import apply_scheduled_fills
    from backend.jobs.queue import Queue
    from backend.persistence.models.ledger import PaperFill
    from backend.portfolio.fills import enqueue_batch_attempt, seal_fill

    owner, rec, pinned, cutoff = pending_recommendation(database, tmp_path)
    batch = approve_batch(
        database,
        owner,
        rec,
        expected_revision=1,
        idempotency_key=uuid4(),
        pinned=pinned,
        approved_at=cutoff,
    )
    calendar = Calendar.model_validate_json(
        pinned.artifacts[pinned.manifest.calendar.artifact_path]
    )
    eligible = next(row for row in calendar.sessions if row.open_at > cutoff)
    queue = Queue(database)
    job_id = enqueue_batch_attempt(
        queue, batch, fixture_observed_at=eligible.close_at + timedelta(seconds=1)
    )
    assert job_id is not None
    lease = queue.claim("atomic-result-test")
    assert lease is not None
    value = apply_scheduled_fills(lease.payload, mp.get_context("spawn").Event(), root=tmp_path)

    def fail_completion(
        connection: Connection,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        if statement.startswith("UPDATE job SET") and "result=" in statement:
            raise RuntimeError("Injected completion failure")

    event.listen(database, "after_cursor_execute", fail_completion)
    try:
        with pytest.raises(RuntimeError, match="Injected completion failure"):
            seal_fill(queue, lease, value)
    finally:
        event.remove(database, "after_cursor_execute", fail_completion)
    state = read_portfolio(database, owner)
    assert state.revision == 2 and state.state.cash_usd == "1000.00" and not state.state.positions
    with Session(database) as session:
        assert not list(session.scalars(select(PaperFill)))
    assert job_status(queue, job_id) == "running"
    seal_fill(queue, lease, value)
    assert job_status(queue, job_id) == "completed"
    assert read_portfolio(database, owner).state.cash_usd == "859.76"
    assert queue.claim("lost-ack-retry") is None


def test_distinct_competing_approvals_lock_one_revision(database: Engine, tmp_path: Path) -> None:
    owner, rec, pinned, cutoff = pending_recommendation(database, tmp_path)
    second = uuid4()
    with Session(database) as session, session.begin():
        original = session.get(RecommendationReference, rec)
        assert original is not None
        session.add(
            RecommendationReference(
                id=second,
                portfolio_id=owner,
                strategy_version_id=original.strategy_version_id,
                snapshot_id=original.snapshot_id,
                as_of_session=original.as_of_session,
                decision_cutoff=original.decision_cutoff,
                portfolio_revision=1,
                source_mode=original.source_mode,
                content=original.content,
                content_sha256=original.content_sha256,
                disposition="ready",
                created_at=cutoff,
            )
        )

    def attempt(identity: UUID) -> UUID | None:
        try:
            return approve_batch(
                database,
                owner,
                identity,
                expected_revision=1,
                idempotency_key=uuid4(),
                pinned=pinned,
                approved_at=cutoff,
            )
        except LedgerConflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, [rec, second]))
    assert sum(row is not None for row in results) == 1
    assert read_portfolio(database, owner).revision == 2
    with Session(database) as session:
        assert len(list(session.scalars(select(PaperOrderBatch)))) == 1


def test_missing_open_remains_pending_then_new_publication_resumes_same_approval(
    database: Engine, tmp_path: Path
) -> None:
    from backend.jobs.queue import Queue
    from backend.jobs.worker import Worker
    from backend.portfolio.batches import read_batch
    from backend.portfolio.fills import enqueue_batch_attempt, enqueue_due_batches

    owner, rec, pinned, cutoff = pending_recommendation(database, tmp_path, decision_only=True)
    batch = approve_batch(
        database,
        owner,
        rec,
        expected_revision=1,
        idempotency_key=uuid4(),
        pinned=pinned,
        approved_at=cutoff,
    )
    calendar = Calendar.model_validate_json(
        pinned.artifacts[pinned.manifest.calendar.artifact_path]
    )
    eligible = next(row for row in calendar.sessions if row.open_at > cutoff)
    queue = Queue(database)
    observed = eligible.close_at + timedelta(seconds=1)
    job = enqueue_batch_attempt(queue, batch, fixture_observed_at=observed)
    assert job is not None and Worker(queue, artifact_root=tmp_path).run_once()
    assert job_status(queue, job) == "completed"
    waiting = read_batch(database, batch)
    assert not waiting.terminal and waiting.orders[0].pending_quantity == "2.000000"
    assert waiting.orders[0].reason is not None
    assert read_portfolio(database, owner).state.cash_usd == "1000.00"
    assert enqueue_batch_attempt(queue, batch, fixture_observed_at=observed) == job
    prepare(database, tmp_path)
    assert enqueue_due_batches(queue) == 1
    assert Worker(queue, artifact_root=tmp_path).run_once()
    complete = read_batch(database, batch)
    assert complete.terminal and complete.status == "filled"
    assert complete.approved_at == cutoff and complete.snapshot_id == waiting.snapshot_id
    assert read_portfolio(database, owner).state.cash_usd == "859.76"


def test_prepare_paper_batch_actual_database_restart() -> None:
    import json

    from sqlalchemy import text
    from sqlalchemy.engine import make_url

    from backend.jobs.queue import Queue
    from backend.jobs.worker import Worker
    from backend.persistence.database import database_engine
    from backend.portfolio.fills import enqueue_batch_attempt
    from backend.tests.integration.test_bootstrap import isolated_url

    root = database_engine(isolated_url())
    with root.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text("CREATE DATABASE paper_batch_restart_46"))
    url = (
        make_url(isolated_url())
        .set(database="paper_batch_restart_46")
        .render_as_string(hide_password=False)
    )
    engine = database_engine(url)
    directory = Path("/evidence/paper-batch-restart")
    directory.mkdir(parents=True, exist_ok=True)
    records = []
    try:
        for name in ["posted", "pending"]:
            account, rec, pinned, cutoff = pending_recommendation(engine, directory / name)
            batch = approve_batch(
                engine,
                account,
                rec,
                expected_revision=1,
                idempotency_key=uuid4(),
                pinned=pinned,
                approved_at=cutoff,
            )
            calendar = Calendar.model_validate_json(
                pinned.artifacts[pinned.manifest.calendar.artifact_path]
            )
            eligible = next(row for row in calendar.sessions if row.open_at > cutoff)
            records.append(
                dict(
                    name=name,
                    account=str(account),
                    batch=str(batch),
                    observation=(eligible.close_at + timedelta(seconds=1)).isoformat(),
                )
            )
        queue = Queue(engine)
        for record in records:
            from datetime import datetime
            from uuid import UUID

            job = enqueue_batch_attempt(
                queue,
                UUID(record["batch"]),
                fixture_observed_at=datetime.fromisoformat(record["observation"]),
            )
            assert job is not None
            record["job"] = str(job)
            if record["name"] == "posted":
                assert Worker(queue, artifact_root=directory / "posted").run_once()
                assert job_status(queue, job) == "completed"
        (directory / "records.json").write_text(json.dumps(records))
    finally:
        engine.dispose()
        root.dispose()


@pytest.mark.restart_verify
def test_paper_batch_posted_and_pending_jobs_survive_actual_restart() -> None:
    import json
    from uuid import UUID

    from sqlalchemy.engine import make_url

    from backend.jobs.queue import Queue
    from backend.jobs.worker import Worker
    from backend.persistence.database import database_engine
    from backend.portfolio.batches import read_batch
    from backend.tests.integration.test_bootstrap import isolated_url

    directory = Path("/evidence/paper-batch-restart")
    records = json.loads((directory / "records.json").read_text())
    url = (
        make_url(isolated_url())
        .set(database="paper_batch_restart_46")
        .render_as_string(hide_password=False)
    )
    engine = database_engine(url)
    try:
        queue = Queue(engine)
        posted, pending = records
        assert job_status(queue, UUID(posted["job"])) == "completed"
        assert read_portfolio(engine, UUID(posted["account"])).state.cash_usd == "859.76"
        assert job_status(queue, UUID(pending["job"])) == "queued"
        assert read_portfolio(engine, UUID(pending["account"])).state.cash_usd == "1000.00"
        assert Worker(queue, artifact_root=directory / "pending").run_once()
        for record in records:
            batch = read_batch(engine, UUID(record["batch"]))
            assert batch.terminal and batch.status == "filled"
            assert read_portfolio(engine, UUID(record["account"])).state.cash_usd == "859.76"
            assert read_portfolio(engine, UUID(record["account"])).revision == 3
            assert job_status(queue, UUID(record["job"])) == "completed"
        assert queue.claim("duplicate-after-restart") is None
    finally:
        engine.dispose()


@pytest.mark.parametrize("cancel_remaining", [False, True])
def test_committed_sell_proceeds_fund_next_job_or_remain_after_cancel(
    database: Engine, tmp_path: Path, cancel_remaining: bool
) -> None:
    """Accounting-only authored intent isolates Q01, not an allocation proposal."""
    from backend.jobs.worker import Worker
    from backend.portfolio.batches import read_batch
    from backend.portfolio.fills import enqueue_batch_attempt, enqueue_due_batches

    owner, rec, pinned, cutoff = pending_recommendation(database, tmp_path, cash="140.25")
    calendar = Calendar.model_validate_json(
        pinned.artifacts[pinned.manifest.calendar.artifact_path]
    )
    first = next(row for row in calendar.sessions if row.open_at > cutoff)
    batch = approve_batch(
        database,
        owner,
        rec,
        expected_revision=1,
        idempotency_key=uuid4(),
        pinned=pinned,
        approved_at=cutoff,
    )
    queue = Queue(database)
    assert (
        enqueue_batch_attempt(
            queue, batch, fixture_observed_at=first.close_at + timedelta(seconds=1)
        )
        is not None
    )
    assert Worker(queue, artifact_root=tmp_path).run_once()
    assert read_portfolio(database, owner).state.cash_usd == "0.01"
    assert read_portfolio(database, owner).state.positions[0].quantity == "2.000000"
    second_cutoff = decision_cutoff(calendar, first.session_date)
    next_open = next(row for row in calendar.sessions if row.open_at > second_cutoff)
    rec = uuid4()
    content = {
        "label": "SYNTHETIC_DATA_ONLY",
        "execution_intent": {
            "schema_version": 1,
            "engine_version": "authored-accounting-1",
            "orders": [
                {
                    "key": "BUY:BBB",
                    "asset_id": "SYN:BBB",
                    "sector": "Technology",
                    "side": "BUY",
                    "requested_quantity": "1.000000",
                },
                {
                    "key": "SELL:AAA",
                    "asset_id": "SYN:AAA",
                    "sector": "Technology",
                    "side": "SELL",
                    "requested_quantity": "2.000000",
                },
            ],
        },
    }
    with Session(database) as session, session.begin():
        session.add(
            RecommendationReference(
                id=rec,
                portfolio_id=owner,
                strategy_version_id=DEFAULT_VERSION_ID,
                snapshot_id=pinned.manifest.snapshot_id(),
                as_of_session=first.session_date,
                decision_cutoff=second_cutoff,
                portfolio_revision=3,
                source_mode="synthetic_fixture",
                content=content,
                content_sha256=digest(content),
                disposition="ready",
                created_at=second_cutoff,
            )
        )
    batch = approve_batch(
        database,
        owner,
        rec,
        expected_revision=3,
        idempotency_key=uuid4(),
        pinned=pinned,
        approved_at=second_cutoff,
    )
    observed = next_open.close_at + timedelta(seconds=1)
    assert enqueue_batch_attempt(queue, batch, fixture_observed_at=observed) is not None
    assert Worker(queue, artifact_root=tmp_path).run_once()
    # Raw70.100 ×.999 ×2 =140.0598 ->140.06 sale, plus prior cash0.01.
    sold = read_portfolio(database, owner)
    assert sold.state.cash_usd == "140.07" and not sold.state.positions and sold.revision == 5
    partial = read_batch(database, batch)
    assert not partial.terminal and partial.status == "partially_filled"
    assert partial.orders[0].side == "SELL" and partial.orders[0].terminal
    if cancel_remaining:
        cancel_batch(database, batch, cancelled_at=observed + timedelta(seconds=1))
        final = read_portfolio(database, owner)
        assert final.state == sold.state and final.revision == 6
        closed = read_batch(database, batch)
        assert closed.terminal and closed.status == "partially_filled"
        assert closed.orders[1].status == "cancelled"
        assert enqueue_batch_attempt(queue, batch, fixture_observed_at=observed) is None
    else:
        assert enqueue_due_batches(queue) == 1
        assert Worker(queue, artifact_root=tmp_path).run_once()
        final = read_portfolio(database, owner)
        # Buy one at70.1701 ->70.17, only posted sale proceeds make this feasible.
        assert final.state.cash_usd == "69.90" and final.revision == 6
        assert final.state.positions[0].asset_id == "SYN:BBB"
        assert final.state.positions[0].quantity == "1.000000"
        assert final.state.positions[0].total_basis_usd == "70.17"
        assert read_batch(database, batch).status == "filled"


def test_later_dividend_credit_cannot_finance_original_pending_open(database: Engine) -> None:
    from backend.persistence.models.ledger import PaperFill
    from backend.portfolio.ledger import post_action, post_order
    from backend.tests.integration.test_paper_ledger import evidence_for, seed_batch
    from backend.tests.portfolio.test_execution import action, at, calendar

    owner, first_order = seed_batch(database)
    assert (
        post_order(
            database,
            first_order,
            calendar=calendar(),
            market=evidence_for(database, first_order),
            observed_at=at(4),
        )
        is not None
    )
    _, pending_order = seed_batch(database, identity=owner, decision=4)
    with Session(database) as session:
        order = session.get(PaperOrder, pending_order)
        assert order is not None
        batch = session.get(PaperOrderBatch, order.batch_id)
        assert batch is not None
        snapshot = batch.snapshot_id
    assert (
        post_action(
            database,
            owner,
            action=action("dividend"),
            snapshot_id=snapshot,
            calendar=calendar(),
            session_date=date(2030, 1, 8),
            observed_at=at(8),
            live=False,
        )
        is not None
    )
    assert (
        post_action(
            database,
            owner,
            action=action("dividend"),
            snapshot_id=snapshot,
            calendar=calendar(),
            session_date=date(2030, 1, 15),
            observed_at=at(15),
            live=False,
        )
        is not None
    )
    prior = read_portfolio(database, owner)
    assert prior.state.cash_usd == "802.30" and prior.state.positions[0].quantity == "2.000000"
    with pytest.raises(LedgerConflict, match="Later action/correction"):
        post_order(
            database,
            pending_order,
            calendar=calendar(),
            market=evidence_for(database, pending_order, day=8),
            observed_at=at(15),
        )
    assert read_portfolio(database, owner) == prior
    with Session(database) as session:
        assert len(list(session.scalars(select(PaperFill)))) == 1
