"""Fenced filesystem-before-database publication; never adopt arbitrary orphans."""

import hashlib
import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.domain.common import JobResult
from backend.domain.types import canonical_json
from backend.jobs.queue import Lease, Queue
from backend.jobs.registry import RefreshPayload
from backend.market_data.files import PinnedSnapshot, SnapshotIntegrityError
from backend.market_data.publication import publish_sealed
from backend.persistence.models.snapshot import (
    CurrentSnapshot,
    DatasetSnapshot,
    SnapshotArtifactReference,
    SnapshotPublication,
)


class PublicationFenceError(RuntimeError):
    pass


def publish_snapshot(queue: Queue, lease: Lease, stage: Path, store: Path, digest: str) -> UUID:
    """Called by the supervisor for a sealed refresh result, not by child handlers.

    Private stage/store ownership is required. Retrying a verified stage after a
    post-rename crash reuses its content-addressed orphan. Lock contention fails
    promptly so a waiting publisher cannot silently consume its remaining lease.
    """
    pinned = PinnedSnapshot.open(stage, digest)
    manifest = pinned.manifest
    config = RefreshPayload.model_validate(lease.payload)
    if config.source_mode == "synthetic_fixture":
        if config.expected_manifest_hash != digest:
            raise SnapshotIntegrityError("Snapshot differs from pinned refresh request")
    else:
        assert config.research_config is not None
        expected = hashlib.sha256(
            canonical_json(config.research_config.model_dump(mode="json"))
        ).hexdigest()
        provenance = json.loads(pinned.artifacts["provenance.json"])
        if provenance.get("request_hash") != expected:
            raise SnapshotIntegrityError("Research snapshot differs from pinned configuration")
    if lease.kind != "refresh_market_data":
        raise ValueError("Publication requires a refresh lease")
    lock_key = int.from_bytes(bytes.fromhex(digest)[:8], "big", signed=True)
    with Session(queue.engine) as session, session.begin():
        locked = session.execute(
            text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": lock_key}
        ).scalar_one()
        if not locked:
            raise PublicationFenceError("Snapshot publication is busy")
        row, now = queue.owned(session, lease)
        if (
            row is None
            or row.kind != "refresh_market_data"
            or row.status != "running"
            or row.attempt_deadline is None
            or row.attempt_deadline <= now
        ):
            raise PublicationFenceError("Refresh lease is no longer valid")
        if row.source_mode != manifest.mode:
            raise SnapshotIntegrityError("Refresh source mode differs from snapshot")
        publish_sealed(stage, store, digest)
        # Files may now exist without metadata. Any failure below rolls back only DB
        # state, preserving the previous pointer and leaving a recoverable orphan.
        row, now = queue.owned(session, lease)
        if (
            row is None
            or row.kind != "refresh_market_data"
            or row.status != "running"
            or row.attempt_deadline is None
            or row.attempt_deadline <= now
        ):
            raise PublicationFenceError("Refresh lease expired during publication")
        identity = manifest.snapshot_id()
        session.execute(
            insert(DatasetSnapshot)
            .values(
                id=identity,
                manifest_hash=digest,
                manifest=manifest.model_dump(mode="json"),
                source_mode=manifest.mode,
                quality=manifest.quality,
                registered_at=now,
            )
            .on_conflict_do_nothing(index_elements=["manifest_hash"])
        )
        existing = session.get(DatasetSnapshot, identity)
        if existing is None or existing.manifest != manifest.model_dump(mode="json"):
            raise SnapshotIntegrityError("Registered snapshot identity mismatch")
        for artifact in manifest.artifacts:
            session.execute(
                insert(SnapshotArtifactReference)
                .values(
                    snapshot_id=identity,
                    path=artifact.path,
                    sha256=artifact.sha256,
                    size_bytes=artifact.size_bytes,
                )
                .on_conflict_do_nothing(index_elements=["snapshot_id", "path"])
            )
        session.add(
            SnapshotPublication(
                job_id=row.id,
                snapshot_id=identity,
                attempt_token=lease.token,
                published_at=now,
            )
        )
        session.flush()
        if manifest.quality != "blocked":
            statement = insert(CurrentSnapshot).values(
                source_mode=manifest.mode,
                snapshot_id=identity,
                publication_job_id=row.id,
            )
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=["source_mode"],
                    set_={
                        "snapshot_id": identity,
                        "publication_job_id": row.id,
                    },
                )
            )
        row.result = JobResult(
            kind="resource", resource_id=identity, message="Immutable market snapshot registered."
        ).model_dump(mode="json")
        row.status = "completed"
        row.progress = 100
        queue.finish_attempt(session, row, now, "completed")
        return identity
