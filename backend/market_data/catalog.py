"""Registered metadata only; never discover filesystem orphans as current data."""

import logging
from pathlib import Path
from uuid import UUID

from pydantic import TypeAdapter
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from backend.domain.data import SnapshotV1
from backend.domain.market import AssetV1
from backend.domain.types import SourceMode
from backend.market_data.files import PinnedSnapshot, SnapshotIntegrityError
from backend.persistence.models.snapshot import DatasetSnapshot

logger = logging.getLogger(__name__)


def verified_snapshot(row: DatasetSnapshot, artifact_root: Path) -> PinnedSnapshot:
    pinned = PinnedSnapshot.open(artifact_root / "snapshots" / row.manifest_hash, row.manifest_hash)
    if (
        pinned.manifest.snapshot_id() != row.id
        or pinned.manifest.model_dump(mode="json") != row.manifest
    ):
        raise SnapshotIntegrityError("Snapshot metadata differs from registered immutable evidence")
    return pinned


def snapshot_envelope(row: DatasetSnapshot, root: Path) -> SnapshotV1:
    try:
        manifest = verified_snapshot(row, root).manifest
    except SnapshotIntegrityError:
        logger.warning("Snapshot integrity check failed snapshot_id=%s", row.id)
        raise
    return SnapshotV1(
        id=row.id,
        provider=manifest.source.provider,
        mode=manifest.mode,
        latest_completed_session=manifest.coverage.latest_completed_session,
        published_at=row.registered_at,
        quality=manifest.quality,
        warnings=manifest.warnings,
        asset_count=len(manifest.coverage.asset_ids),
        manifest_sha256=row.manifest_hash,
        coverage=manifest.coverage,
    )


def discover_assets(
    engine: Engine, root: Path, snapshot_id: UUID, mode: SourceMode
) -> tuple[AssetV1, ...]:
    with Session(engine) as session:
        row = session.get(DatasetSnapshot, snapshot_id)
        if row is None or row.source_mode != mode:
            raise LookupError("Snapshot not found")
        pinned = verified_snapshot(row, root)
        matches = [
            artifact
            for artifact in pinned.manifest.artifacts
            if artifact.role == "assets"
            and artifact.schema_version == 1
            and artifact.format == "json"
        ]
        if len(matches) != 1:
            raise SnapshotIntegrityError("Snapshot asset inventory is unsupported")
        assets = TypeAdapter(tuple[AssetV1, ...]).validate_json(pinned.artifacts[matches[0].path])
        return tuple(sorted(assets, key=lambda asset: asset.asset_id))
