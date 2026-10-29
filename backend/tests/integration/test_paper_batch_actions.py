"""Actual published synthetic action evidence across supervised financial jobs."""

import hashlib
import json
import shutil
from datetime import date, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from backend.domain.market import SnapshotManifestV1
from backend.domain.types import canonical_json
from backend.jobs.queue import Queue
from backend.jobs.worker import Worker
from backend.market_data.catalog import verified_snapshot
from backend.market_data.models import Calendar, CorporateAction
from backend.market_data.snapshots import publish_snapshot
from backend.persistence.models.ledger import LedgerEvent, RecommendationReference
from backend.persistence.models.snapshot import DatasetSnapshot
from backend.portfolio.batches import approve_batch, read_batch
from backend.portfolio.fills import enqueue_batch_attempt, enqueue_due_batches
from backend.portfolio.ledger import digest, read_portfolio
from backend.strategies.build import engine_fingerprint
from backend.strategies.clock import decision_cutoff
from backend.strategies.registry import DEFAULT_VERSION_ID
from backend.tests.integration.test_bootstrap import database as database
from backend.tests.integration.test_paper_batches import pending_recommendation
from backend.tests.market_data.test_files import FIXTURES

pytestmark = pytest.mark.integration


def publish_actions(database: Engine, root: Path, action: CorporateAction) -> UUID:
    stage = root / "action-stage"
    shutil.copytree(FIXTURES / "snapshot", stage)
    (stage / "actions.json").write_bytes(canonical_json([action.model_dump(mode="json")]))
    provenance = json.loads((stage / "provenance.json").read_bytes())
    provenance["test_case"] = (
        "Authored dividend accounting only; no adjusted-return or backtest claim."
    )
    (stage / "provenance.json").write_bytes(canonical_json(provenance))
    value = json.loads((stage / "manifest.json").read_bytes())
    value["price_basis"]["corporate_action_policy"] = "authored_synthetic_actions_v1"
    value["price_basis"]["adjusted_close"] = "synthetic_unadjusted_return_observations_v1"
    for artifact in value["artifacts"]:
        if artifact["role"] in {"actions", "provenance"}:
            data = (stage / artifact["path"]).read_bytes()
            artifact.update(sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data))
            if artifact["role"] == "actions":
                artifact["row_count"] = 1
            else:
                value["source"]["capabilities_sha256"] = artifact["sha256"]
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
    lease = queue.claim("authored-action-publication")
    assert lease is not None
    return publish_snapshot(queue, lease, stage, root / "snapshots", manifest.manifest_hash())


@pytest.mark.parametrize("payable_known", [True, False])
def test_ex_date_capture_payment_then_fill_are_separate_chronological_commits(
    database: Engine, tmp_path: Path, payable_known: bool
) -> None:
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
    assert read_portfolio(database, owner).state.cash_usd == "859.76"
    action = CorporateAction(
        asset_id="SYN:AAA",
        event_id="authored-dividend-AAA",
        kind="dividend",
        effective_session=date(2028, 7, 19),
        payable_session=date(2028, 7, 20) if payable_known else None,
        provider=pinned.manifest.source.provider,
        currency="USD",
        per_share="1.25",
        ratio_numerator=None,
        ratio_denominator=None,
        available_at=first.close_at + timedelta(seconds=1),
        ingested_at=first.close_at + timedelta(seconds=1),
    )
    source_id = publish_actions(database, tmp_path, action)
    with Session(database) as session:
        source = session.get(DatasetSnapshot, source_id)
        assert source is not None
        pinned = verified_snapshot(source, tmp_path)
    decision = date(2028, 7, 20)
    cutoff = decision_cutoff(calendar, decision)
    eligible = next(row for row in calendar.sessions if row.open_at > cutoff)
    rec = uuid4()
    content = {
        "label": "SYNTHETIC_DATA_ONLY",
        "execution_intent": {
            "schema_version": 1,
            "engine_version": "authored-action-test-1",
            "orders": [
                {
                    "key": "BUY:BBB",
                    "asset_id": "SYN:BBB",
                    "sector": "Technology",
                    "side": "BUY",
                    "requested_quantity": "1.000000",
                }
            ],
        },
    }
    with Session(database) as session, session.begin():
        session.add(
            RecommendationReference(
                id=rec,
                portfolio_id=owner,
                strategy_version_id=DEFAULT_VERSION_ID,
                snapshot_id=source_id,
                as_of_session=decision,
                decision_cutoff=cutoff,
                portfolio_revision=3,
                source_mode="synthetic_fixture",
                content=content,
                content_sha256=digest(content),
                disposition="ready",
                created_at=cutoff,
            )
        )
    batch = approve_batch(
        database,
        owner,
        rec,
        expected_revision=3,
        idempotency_key=uuid4(),
        pinned=pinned,
        approved_at=cutoff,
    )
    assert (
        enqueue_batch_attempt(
            queue, batch, fixture_observed_at=eligible.close_at + timedelta(seconds=1)
        )
        is not None
    )
    if not payable_known:
        assert Worker(queue, artifact_root=tmp_path).run_once()
        assert read_portfolio(database, owner).revision == 5
        assert enqueue_due_batches(queue) == 1
        assert Worker(queue, artifact_root=tmp_path).run_once()
        blocked = read_batch(database, batch)
        assert not blocked.terminal and blocked.reason == "PAYABLE_DATE_UNAVAILABLE"
        assert read_portfolio(database, owner).state.cash_usd == "859.76"
        assert len(read_portfolio(database, owner).state.positions) == 1
        known = action.model_copy(update={"payable_session": date(2028, 7, 20)})
        publish_actions(database, tmp_path, known)
        assert enqueue_due_batches(queue) == 1
    phases = [(5, "859.76", False)] if payable_known else []
    phases += [(6, "862.26", False), (7, "791.99", True)]
    for revision, cash, terminal in phases:
        assert Worker(queue, artifact_root=tmp_path).run_once()
        actual = read_portfolio(database, owner)
        assert actual.revision == revision and actual.state.cash_usd == cash
        assert actual.state.entitlements[0].quantity == "2.000000"
        assert read_batch(database, batch).terminal is terminal
        if not terminal:
            assert enqueue_due_batches(queue) == 1
    assert [(item.asset_id, item.quantity) for item in actual.state.positions] == [
        ("SYN:AAA", "2.000000"),
        ("SYN:BBB", "1.000000"),
    ]

    with Session(database) as session:
        events = list(
            session.scalars(
                select(LedgerEvent).where(
                    LedgerEvent.portfolio_id == owner,
                    LedgerEvent.kind.in_(("entitlement", "dividend", "fill")),
                )
            )
        )
        assert all(
            event.payload["details"]["execution_engine_version"] == engine_fingerprint()
            for event in events
        )
        fill = next(event for event in events if event.sequence == 7)
        assert (
            fill.payload["details"]["execution"]["context"]["engine_version"]
            == "authored-action-test-1"
        )
