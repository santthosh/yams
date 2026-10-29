"""Closed server-owned scenario inputs; public recommendation admission belongs to #49."""

from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from backend.domain.forecast import ForecastAllocation
from backend.domain.types import (
    Contract,
    Hash256,
    Money,
    SessionDate,
    SourceMode,
    UTCTimestamp,
    canonical_json,
    load_json,
)


class ForecastInputs(Contract):
    portfolio_id: UUID
    portfolio_revision: Annotated[int, Field(strict=True, ge=1, le=9223372036854775807)]
    strategy_version_id: UUID
    config_sha256: Hash256
    snapshot_id: UUID
    snapshot_sha256: Hash256
    calendar_sha256: Hash256
    source_mode: SourceMode
    as_of_session: SessionDate
    decision_cutoff_utc: UTCTimestamp
    valuation_as_of_session: SessionDate | None
    initial_value_usd: Money | None
    current_allocation: ForecastAllocation
    proposed_allocation: ForecastAllocation
    seed: Annotated[int, Field(strict=True, ge=0, le=18446744073709551615)] = 42

    @model_validator(mode="after")
    def supported_accounting_inputs(self) -> Self:
        if max(len(self.current_allocation.weights), len(self.proposed_allocation.weights)) > 1000:
            raise ValueError("Oversized allocation input")
        if self.initial_value_usd is not None and Decimal(self.initial_value_usd) <= 0:
            raise ValueError("Initial NAV must be positive")
        hold = self.current_allocation.upfront_cost_usd
        proposed = self.proposed_allocation.upfront_cost_usd
        if hold is not None and Decimal(hold) != 0:
            raise ValueError("Holding unchanged has zero upfront cost")
        if self.initial_value_usd is not None and proposed is not None:
            if Decimal(proposed) >= Decimal(self.initial_value_usd):
                raise ValueError("Proposed cost must leave positive capital")
        return self

    def canonical_bytes(self) -> bytes:
        return canonical_json(load_json(self.model_dump_json()))


class ForecastPayload(Contract):
    schema_version: Literal[1] = 1
    forecast_id: UUID
    inputs_canonical_json: Annotated[str, Field(strict=True, min_length=1, max_length=262144)]
    engine_version: Hash256

    @property
    def inputs(self) -> ForecastInputs:
        return ForecastInputs.model_validate_json(self.inputs_canonical_json)

    @model_validator(mode="after")
    def pinned_inputs(self) -> Self:
        if self.inputs.canonical_bytes().decode() != self.inputs_canonical_json:
            raise ValueError("Forecast inputs require their complete canonical JSON")
        return self
