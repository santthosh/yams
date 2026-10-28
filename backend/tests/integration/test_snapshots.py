"""Real PostgreSQL and filesystem boundaries, with no provider/network dependency."""

import shutil
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from backend.jobs.queue import Queue
from backend.market_data.files import SnapshotIntegrityError
from backend.market_data.snapshots import PublicationFenceError, publish_snapshot
from backend.persistence.bootstrap import bootstrap
from backend.persistence.models.snapshot import (
    CurrentSnapshot,
    DatasetSnapshot,
    SnapshotPublication,
)
from backend.tests.integration.test_bootstrap import database as database
from backend.tests.market_data.test_files import FIXTURES, IDENTITY

pytestmark = pytest.mark.integration


def setup(database: Engine, tmp_path: Path) -> tuple[Queue, Path, Path]:
    bootstrap(database)
    stage = tmp_path / "stage"
    shutil.copytree(FIXTURES / "snapshot", stage)
    store = tmp_path / "store"
    store.mkdir()
    return Queue(database), stage, store


def enqueue(queue: Queue) -> None:
    queue.enqueue(
        "refresh_market_data",
        {
            "schema_version": 1,
            "source_mode": "synthetic_fixture",
            "expected_manifest_hash": IDENTITY,
        },
        uuid4(),
    )


def test_publication_metadata_and_retry_use_one_immutable_snapshot(
    database: Engine, tmp_path: Path
) -> None:
    queue, stage, store = setup(database, tmp_path)
    for _ in range(2):
        if not stage.exists():
            shutil.copytree(FIXTURES / "snapshot", stage)
        enqueue(queue)
        lease = queue.claim("publication-test")
        assert lease is not None
        identity = publish_snapshot(queue, lease, stage, store, IDENTITY)
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(DatasetSnapshot)) == 1
        assert session.scalar(select(func.count()).select_from(SnapshotPublication)) == 2
        pointer = session.get(CurrentSnapshot, "synthetic_fixture")
        assert pointer is not None and pointer.snapshot_id == identity
    with pytest.raises(DBAPIError), database.begin() as connection:
        connection.execute(text("UPDATE dataset_snapshot SET quality = 'blocked'"))


def test_expired_publisher_cannot_rename_or_register(database: Engine, tmp_path: Path) -> None:
    queue, stage, store = setup(database, tmp_path)
    enqueue(queue)
    lease = queue.claim("expired-publisher")
    assert lease is not None
    future = Queue(database, clock=lambda session: queue.clock(session) + timedelta(seconds=31))
    with pytest.raises(PublicationFenceError):
        publish_snapshot(future, lease, stage, store, IDENTITY)
    assert stage.exists() and list(store.iterdir()) == []
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(DatasetSnapshot)) == 0


def test_crash_after_rename_rolls_back_db_and_retry_verifies_orphan(
    database: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.market_data import snapshots

    queue, stage, store = setup(database, tmp_path)
    enqueue(queue)
    lease = queue.claim("crash-publisher")
    assert lease is not None
    from backend.market_data.publication import publish_sealed

    original = publish_sealed

    def crash(*args: object, **kwargs: object) -> None:
        original(stage, store, IDENTITY)
        raise RuntimeError("injected post-rename crash")

    monkeypatch.setattr(snapshots, "publish_sealed", crash)
    with pytest.raises(RuntimeError, match="injected"):
        publish_snapshot(queue, lease, stage, store, IDENTITY)
    assert (store / IDENTITY).is_dir()
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(DatasetSnapshot)) == 0
        assert session.get(CurrentSnapshot, "synthetic_fixture") is None
    shutil.copytree(FIXTURES / "snapshot", stage)
    monkeypatch.setattr(snapshots, "publish_sealed", original)
    (store / IDENTITY / "bars.parquet").write_bytes(b"corrupt orphan")
    with pytest.raises(SnapshotIntegrityError):
        publish_snapshot(queue, lease, stage, store, IDENTITY)
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(DatasetSnapshot)) == 0


def test_supervised_fixture_refresh_registers_only_completed_result(
    database: Engine, tmp_path: Path
) -> None:
    from backend.jobs.worker import Worker
    from backend.persistence.models.job import Job

    bootstrap(database)
    queue = Queue(database)
    identity = queue.enqueue(
        "refresh_market_data",
        {
            "schema_version": 1,
            "source_mode": "synthetic_fixture",
            "expected_manifest_hash": IDENTITY,
        },
        uuid4(),
    )
    assert Worker(queue, artifact_root=tmp_path).run_once()
    with Session(database) as session:
        job = session.get(Job, identity)
        assert job is not None and job.status == "completed"
        pointer = session.get(CurrentSnapshot, "synthetic_fixture")
        assert pointer is not None
        assert pointer.publication_job_id == identity
    assert (tmp_path / "snapshots" / IDENTITY / "manifest.json").is_file()


def test_valid_orphan_requires_explicit_refresh_to_register(
    database: Engine, tmp_path: Path
) -> None:
    from backend.market_data.publication import publish_sealed

    queue, stage, store = setup(database, tmp_path)
    publish_sealed(stage, store, IDENTITY)
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(DatasetSnapshot)) == 0
    shutil.copytree(FIXTURES / "snapshot", stage)
    enqueue(queue)
    lease = queue.claim("orphan-recovery")
    assert lease is not None
    identity = publish_snapshot(queue, lease, stage, store, IDENTITY)
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(SnapshotPublication)) == 1
        pointer = session.get(CurrentSnapshot, "synthetic_fixture")
        assert pointer is not None and pointer.snapshot_id == identity


def test_concurrent_digest_lock_preserves_sealed_stage(database: Engine, tmp_path: Path) -> None:
    queue, stage, store = setup(database, tmp_path)
    enqueue(queue)
    lease = queue.claim("contending-publisher")
    assert lease is not None
    key = int.from_bytes(bytes.fromhex(IDENTITY)[:8], "big", signed=True)
    with database.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
        with pytest.raises(PublicationFenceError, match="busy"):
            publish_snapshot(queue, lease, stage, store, IDENTITY)
    assert stage.is_dir() and list(store.iterdir()) == []
    publish_snapshot(queue, lease, stage, store, IDENTITY)


def test_blocked_refresh_is_inspectable_without_replacing_current(
    database: Engine, tmp_path: Path
) -> None:
    from backend.domain.market import SnapshotManifestV1

    queue, stage, store = setup(database, tmp_path)
    enqueue(queue)
    lease = queue.claim("good-snapshot")
    assert lease is not None
    original = publish_snapshot(queue, lease, stage, store, IDENTITY)
    shutil.copytree(FIXTURES / "snapshot", stage)
    manifest = SnapshotManifestV1.model_validate_json((stage / "manifest.json").read_bytes())
    blocked = manifest.model_copy(update={"quality": "blocked"})
    (stage / "manifest.json").write_bytes(blocked.canonical_bytes())
    digest = blocked.manifest_hash()
    queue.enqueue(
        "refresh_market_data",
        {
            "schema_version": 1,
            "source_mode": "synthetic_fixture",
            "expected_manifest_hash": digest,
        },
        uuid4(),
    )
    lease = queue.claim("blocked-snapshot")
    assert lease is not None
    published = publish_snapshot(queue, lease, stage, store, digest)
    with Session(database) as session:
        assert session.get(DatasetSnapshot, published) is not None
        pointer = session.get(CurrentSnapshot, "synthetic_fixture")
        assert pointer is not None and pointer.snapshot_id == original
