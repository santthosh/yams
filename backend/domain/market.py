"""Market transport and snapshot-manifest contracts; no provider ingestion."""

import hashlib
from decimal import Decimal
from pathlib import PurePosixPath
from typing import Annotated, Literal, Self
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import Field, StrictStr, StringConstraints, model_validator

from backend.domain.types import (
    AssetId,
    Contract,
    Hash256,
    NonnegativeInt,
    Price,
    Reason,
    SessionDate,
    SourceMode,
    UTCTimestamp,
    canonical_json,
)


class AssetV1(Contract):
    asset_id: AssetId
    venue: Annotated[str, StringConstraints(strict=True, pattern=r"^[A-Z0-9]{4}$")]
    symbol: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=32)]
    currency: Literal["USD"]
    instrument: Literal["ordinary_equity", "etf"]
    sector: Annotated[str, StringConstraints(strict=True, min_length=1)]
    provider: StrictStr
    provider_id: StrictStr


class MarketBarV1(Contract):
    schema_version: Literal[1]
    asset_id: AssetId
    session_date: SessionDate
    open: Price
    high: Price
    low: Price
    close: Price
    adjusted_close: Price
    volume: NonnegativeInt
    currency: Literal["USD"]
    provider: StrictStr
    published_at: UTCTimestamp | None
    available_at: UTCTimestamp
    ingested_at: UTCTimestamp
    availability_basis: Literal["published", "observed", "synthetic"]
    price_basis: Literal["raw_as_traded", "provider_unverified"]
    volume_basis: StrictStr
    quality_flags: tuple[Reason, ...]

    @model_validator(mode="after")
    def coherent_bar(self) -> Self:
        low, high = Decimal(self.low), Decimal(self.high)
        if not low <= Decimal(self.open) <= high or not low <= Decimal(self.close) <= high:
            raise ValueError("OHLC bounds are inconsistent")
        if self.availability_basis == "published" and self.published_at is None:
            raise ValueError("Published availability requires published_at")
        if self.published_at is not None and self.available_at < self.published_at:
            raise ValueError("Availability cannot precede publication")
        if self.availability_basis == "observed" and self.available_at != self.ingested_at:
            raise ValueError("Observed availability must equal original ingestion")
        return self


class SnapshotSource(Contract):
    provider: StrictStr
    adapter_version: StrictStr
    normalization_version: StrictStr
    rights_reference: StrictStr | None
    rights_status: Literal["synthetic_owned", "verified_local_use", "unverified"]
    capabilities_sha256: Hash256


class SnapshotPriceBasis(Contract):
    ohlc: Literal["raw_as_traded", "provider_unverified"]
    adjusted_close: StrictStr
    volume: StrictStr
    currency: Literal["USD"]
    corporate_action_policy: StrictStr


class CalendarReference(Contract):
    id: StrictStr
    timezone: Literal["America/New_York"]
    version: Hash256
    artifact_path: StrictStr


class MissingSession(Contract):
    asset_id: AssetId
    session_date: SessionDate


class SnapshotCoverage(Contract):
    asset_ids: tuple[AssetId, ...]
    first_session: SessionDate | None
    last_session: SessionDate | None
    latest_completed_session: SessionDate | None
    missing_sessions: tuple[MissingSession, ...]
    membership_basis: Literal["point_in_time", "current_only", "synthetic"]

    @model_validator(mode="after")
    def coherent_coverage(self) -> Self:
        if tuple(sorted(set(self.asset_ids))) != self.asset_ids:
            raise ValueError("Asset IDs must be sorted and unique")
        if (self.first_session is None) != (self.last_session is None):
            raise ValueError("Coverage bounds must both be known or both unavailable")
        if self.first_session is not None and self.last_session is not None:
            if self.first_session > self.last_session:
                raise ValueError("Coverage end precedes start")
            if self.latest_completed_session is not None and not (
                self.first_session <= self.latest_completed_session <= self.last_session
            ):
                raise ValueError("Latest completed session is outside coverage")
        elif self.latest_completed_session is not None:
            raise ValueError("Latest completed session requires coverage bounds")
        pairs = tuple((item.asset_id, item.session_date) for item in self.missing_sessions)
        if tuple(sorted(set(pairs))) != pairs:
            raise ValueError("Missing sessions must be sorted and unique")
        if any(asset_id not in self.asset_ids for asset_id, _ in pairs):
            raise ValueError("Missing session refers to an unknown asset")
        return self


class SnapshotArtifact(Contract):
    path: Annotated[str, StringConstraints(strict=True, pattern=r"^[A-Za-z0-9_./-]+$")]
    role: Literal["bars", "assets", "actions", "universe", "calendar", "provenance", "coverage"]
    format: Literal["parquet", "json"]
    schema_version: Annotated[int, Field(strict=True, ge=1)]
    sha256: Hash256
    size_bytes: NonnegativeInt
    row_count: NonnegativeInt | None

    @model_validator(mode="after")
    def lexical_path(self) -> Self:
        parts = self.path.split("/")
        if PurePosixPath(self.path).is_absolute() or any(part in {"", ".", ".."} for part in parts):
            raise ValueError("Artifact path must be a contained relative path")
        if self.path.casefold() == "manifest.json":
            raise ValueError("Manifest cannot include itself")
        if self.format == "parquet" and self.row_count is None:
            raise ValueError("Tabular artifacts require row count")
        return self


class SnapshotManifestV1(Contract):
    schema_version: Literal[1]
    mode: SourceMode
    source: SnapshotSource
    price_basis: SnapshotPriceBasis
    calendar: CalendarReference
    coverage: SnapshotCoverage
    quality: Literal["usable", "usable_with_warnings", "blocked"]
    warnings: tuple[Reason, ...]
    artifacts: Annotated[tuple[SnapshotArtifact, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def coherent_manifest(self) -> Self:
        paths = tuple(artifact.path for artifact in self.artifacts)
        if paths != tuple(sorted(paths)) or len({path.casefold() for path in paths}) != len(paths):
            raise ValueError("Artifact paths must be sorted and unique without case collisions")
        roles = {artifact.role for artifact in self.artifacts}
        if not {"bars", "assets", "universe", "calendar", "provenance"} <= roles:
            raise ValueError("Missing required artifact role")
        if self.warnings != tuple(sorted(set(self.warnings))):
            raise ValueError("Warnings must be sorted and unique")
        if self.mode == "synthetic_fixture" and (
            "SYNTHETIC_DATA_ONLY" not in self.warnings
            or self.source.rights_status != "synthetic_owned"
        ):
            raise ValueError("Synthetic snapshots require authored provenance and warning")
        if (
            self.coverage.membership_basis == "current_only"
            and "SURVIVORSHIP_BIAS_RISK" not in self.warnings
        ):
            raise ValueError("Current-only membership requires survivorship warning")
        calendar = [item for item in self.artifacts if item.path == self.calendar.artifact_path]
        if (
            len(calendar) != 1
            or calendar[0].role != "calendar"
            or calendar[0].sha256 != self.calendar.version
        ):
            raise ValueError("Calendar reference does not match an enumerated schedule")
        if not any(
            item.role == "provenance" and item.sha256 == self.source.capabilities_sha256
            for item in self.artifacts
        ):
            raise ValueError("Source capability hash must reference provenance artifact")
        if self.source.rights_status == "unverified" and self.quality != "blocked":
            raise ValueError("Unverified data rights cannot be usable")
        return self

    def canonical_bytes(self) -> bytes:
        return canonical_json(self.model_dump(mode="json"))

    def manifest_hash(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    def snapshot_id(self) -> UUID:
        return uuid5(NAMESPACE_URL, "urn:yams:dataset:sha256:" + self.manifest_hash())
