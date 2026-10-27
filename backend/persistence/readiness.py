"""Read-only readiness probes, with bounded DB I/O and sanitized diagnostics."""

import hashlib
from pathlib import Path

from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from backend.domain.market import SnapshotManifestV1
from backend.domain.workspace import FixtureMetadata, HealthV1, ReadinessCheck, WorkspaceV1
from backend.persistence.bootstrap import expected_revision
from backend.persistence.models.workspace import LocalWorkspace


def fixture_metadata(root: Path) -> FixtureMetadata:
    directory = root / "snapshot"
    if (directory / "manifest.json").is_symlink():
        raise ValueError("Fixture manifest symlinks are unsupported")
    manifest = SnapshotManifestV1.model_validate_json((directory / "manifest.json").read_bytes())
    if manifest.mode != "synthetic_fixture" or manifest.quality == "blocked":
        raise ValueError("Expected usable synthetic fixture")
    for artifact in manifest.artifacts:
        path = directory / artifact.path
        if any(parent.is_symlink() for parent in [path, *path.parents]):
            raise ValueError("Fixture symlinks are unsupported")
        content = path.read_bytes()
        if (
            len(content) != artifact.size_bytes
            or hashlib.sha256(content).hexdigest() != artifact.sha256
        ):
            raise ValueError("Fixture integrity failure")
    assert manifest.coverage.first_session is not None
    assert manifest.coverage.last_session is not None
    return FixtureMetadata(
        label="SYNTHETIC_DATA_ONLY",
        snapshot_id=manifest.snapshot_id(),
        manifest_sha256=manifest.manifest_hash(),
        first_session=manifest.coverage.first_session,
        last_session=manifest.coverage.last_session,
        asset_count=len(manifest.coverage.asset_ids),
    )


def read_workspace(engine: Engine) -> WorkspaceV1:
    with Session(engine) as session:
        row = session.execute(select(LocalWorkspace)).scalar_one()
        return WorkspaceV1(
            id=row.id,
            locale=row.locale,
            default_benchmark=row.default_benchmark,
            preferences=row.preferences,
        )


def readiness(engine: Engine | None, root: Path) -> HealthV1:
    database = ReadinessCheck(status="failed", reason="DATABASE_UNAVAILABLE")
    migration = ReadinessCheck(status="unchecked", reason="DATABASE_UNAVAILABLE")
    workspace = ReadinessCheck(status="unchecked", reason="DATABASE_UNAVAILABLE")
    if engine is not None:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
                database = ReadinessCheck(status="ready", reason=None)
                migration = ReadinessCheck(status="failed", reason="MIGRATION_MISMATCH")
                workspace = ReadinessCheck(status="unchecked", reason="MIGRATION_MISMATCH")
                revisions = (
                    connection.execute(text("SELECT version_num FROM alembic_version"))
                    .scalars()
                    .all()
                )
                if list(revisions) == [expected_revision()]:
                    migration = ReadinessCheck(status="ready", reason=None)
            if migration.status == "ready":
                workspace = ReadinessCheck(status="failed", reason="WORKSPACE_UNAVAILABLE")
                read_workspace(engine)
                workspace = ReadinessCheck(status="ready", reason=None)
        except Exception:
            pass  # Only predetermined diagnostic codes leave this boundary.
    fixtures = ReadinessCheck(status="failed", reason="FIXTURES_UNAVAILABLE")
    metadata = None
    try:
        metadata = fixture_metadata(root)
        fixtures = ReadinessCheck(status="ready", reason=None)
    except (OSError, ValueError, AssertionError):
        pass
    checks = (database, migration, workspace, fixtures)
    return HealthV1(
        status="ready" if all(check.status == "ready" for check in checks) else "not_ready",
        database=database,
        migration=migration,
        workspace=workspace,
        fixtures=fixtures,
        fixture_metadata=metadata,
    )
