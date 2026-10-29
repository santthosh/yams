"""Closed server-owned single-order publication job; no prices or credentials."""

from typing import Literal, Self
from uuid import UUID

from pydantic import model_validator

from backend.domain.types import AssetId, Contract, Hash256, SessionDate, SourceMode, UTCTimestamp


class ScheduledFillPayload(Contract):
    schema_version: Literal[1] = 1
    portfolio_id: UUID
    batch_id: UUID
    order_id: UUID
    asset_id: AssetId
    eligible_session: SessionDate
    source_mode: SourceMode
    decision_snapshot_id: UUID
    decision_snapshot_sha256: Hash256
    execution_snapshot_id: UUID
    execution_snapshot_sha256: Hash256
    fixture_observed_at: UTCTimestamp | None = None

    @model_validator(mode="after")
    def clock(self) -> Self:
        if (self.fixture_observed_at is not None) != (self.source_mode == "synthetic_fixture"):
            raise ValueError("Only explicit fixture replay has a pinned observation clock")
        return self
