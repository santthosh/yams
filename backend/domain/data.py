"""Data discovery envelopes; underlying evidence stays in immutable snapshots."""

from typing import Literal
from uuid import UUID

from backend.domain.common import JobV1, Page
from backend.domain.market import AssetV1, SnapshotCoverage
from backend.domain.types import (
    Contract,
    Hash256,
    NonnegativeInt,
    Reason,
    SessionDate,
    SourceMode,
    UTCTimestamp,
)


class SnapshotV1(Contract):
    id: UUID
    provider: str
    mode: SourceMode
    latest_completed_session: SessionDate | None
    published_at: UTCTimestamp
    quality: Literal["usable", "usable_with_warnings", "blocked"]
    warnings: tuple[Reason, ...]
    asset_count: NonnegativeInt
    manifest_sha256: Hash256
    coverage: SnapshotCoverage


class DataHealthV1(Contract):
    mode: SourceMode
    checked_at: UTCTimestamp
    status: Literal["empty", "ready", "refreshing", "failed"]
    current_snapshot: SnapshotV1 | None
    latest_job: JobV1 | None
    warnings: tuple[Reason, ...]
    # Inspection metadata is not a claim of up-to-date real exchange coverage.
    freshness: Literal["synthetic", "unknown", "refresh_failed"]


class AssetPageV1(Page[AssetV1]):
    snapshot_id: UUID
    mode: SourceMode
