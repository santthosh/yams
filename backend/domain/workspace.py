from typing import Literal
from uuid import UUID

from pydantic import JsonValue, StrictStr

from backend.domain.types import Contract, Hash256, SessionDate


class ReadinessCheck(Contract):
    status: Literal["ready", "failed", "unchecked"]
    reason: StrictStr | None


class FixtureMetadata(Contract):
    label: Literal["SYNTHETIC_DATA_ONLY"]
    snapshot_id: UUID
    manifest_sha256: Hash256
    first_session: SessionDate
    last_session: SessionDate
    asset_count: int


class HealthV1(Contract):
    status: Literal["ready", "not_ready"]
    paper_only: Literal[True] = True
    database: ReadinessCheck
    migration: ReadinessCheck
    workspace: ReadinessCheck
    fixtures: ReadinessCheck
    fixture_metadata: FixtureMetadata | None


class WorkspaceV1(Contract):
    id: UUID
    locale: StrictStr
    default_benchmark: StrictStr
    preferences: dict[str, JsonValue]
    paper_only: Literal[True] = True
