"""Closed internal admission envelope; no public experiment endpoint."""

from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from backend.domain.experiment import ExperimentRequest
from backend.domain.strategy import StrategyConfigV1
from backend.domain.types import Contract, Hash256, SourceMode, canonical_json, load_json


class BacktestCorePayload(Contract):
    schema_version: Literal[1] = 1
    experiment_id: UUID
    inputs_canonical_json: Annotated[str, Field(strict=True, min_length=1, max_length=16384)]
    source_mode: SourceMode
    config_sha256: Hash256
    snapshot_sha256: Hash256
    calendar_sha256: Hash256
    engine_version: Hash256
    config_canonical_json: Annotated[str, Field(strict=True, min_length=1, max_length=65536)]

    @property
    def inputs(self) -> ExperimentRequest:
        return ExperimentRequest.model_validate_json(self.inputs_canonical_json)

    @model_validator(mode="after")
    def immutable_config(self) -> Self:
        _ = self.inputs  # validate the complete public input object in its pinned JSON envelope
        if (
            canonical_json(load_json(self.inputs_canonical_json)).decode()
            != self.inputs_canonical_json
        ):
            raise ValueError("Backtest request must use canonical JSON")
        rules = StrategyConfigV1.from_json(self.config_canonical_json)
        if (
            rules.config_hash() != self.config_sha256
            or rules.canonical_bytes().decode() != self.config_canonical_json
        ):
            raise ValueError("Backtest config must match its pinned canonical identity")
        return self
