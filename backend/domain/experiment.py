"""Immutable experiment inputs and lifecycle-dependent results."""

from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, StrictStr, model_validator

from backend.domain.common import ArtifactReference, ErrorDetail, JobStatus
from backend.domain.types import (
    AssetId,
    Contract,
    FiniteNumber,
    Hash256,
    Money,
    Reason,
    SessionDate,
    SourceMode,
    UTCTimestamp,
)


class EvaluationSplit(Contract):
    kind: Literal["chronological"]
    holdout_fraction: Annotated[FiniteNumber, Field(gt=0, lt=1)]


class ExperimentRequest(Contract):
    strategy_version_id: UUID
    snapshot_id: UUID
    start_session: SessionDate
    end_session_exclusive: SessionDate
    initial_capital_usd: Money
    benchmark_asset_id: AssetId
    execution_policy_id: Literal["us_eod_next_open_v1"]
    random_seed: Annotated[int, Field(strict=True, ge=0, le=18446744073709551615)]
    evaluation_split: EvaluationSplit

    @model_validator(mode="after")
    def positive_window_and_capital(self) -> Self:
        if self.start_session >= self.end_session_exclusive:
            raise ValueError("Experiment requires a positive half-open date interval")
        if Decimal(self.initial_capital_usd) <= 0:
            raise ValueError("Initial synthetic capital must be positive")
        return self


class MetricValue(Contract):
    value: FiniteNumber | None
    unavailable_reason: Reason | None

    @model_validator(mode="after")
    def reason_for_null(self) -> Self:
        if (self.value is None) != (self.unavailable_reason is not None):
            raise ValueError("Null metric requires reason; available metric has none")
        return self


class ExperimentMetrics(Contract):
    cumulative_return_fraction: MetricValue
    annualized_return_fraction: MetricValue
    annualized_volatility_fraction: MetricValue
    max_drawdown_fraction: MetricValue
    turnover_fraction: MetricValue
    sharpe_ratio: MetricValue
    slippage_usd: Money
    fees_usd: Money
    trade_count: Annotated[int, Field(strict=True, ge=0)]


class ExperimentRunV1(Contract):
    id: UUID
    job_id: UUID
    status: JobStatus
    inputs: ExperimentRequest
    config_sha256: Hash256
    snapshot_sha256: Hash256
    data_status: SourceMode
    created_at: UTCTimestamp
    engine_version: StrictStr
    metrics: ExperimentMetrics | None
    curve_artifact: ArtifactReference | None
    trade_artifact: ArtifactReference | None
    reproducibility_manifest: ArtifactReference | None
    warnings: tuple[Reason, ...]
    error: ErrorDetail | None

    @model_validator(mode="after")
    def sealed_output(self) -> Self:
        result = (
            self.metrics,
            self.curve_artifact,
            self.trade_artifact,
            self.reproducibility_manifest,
        )
        if self.status == "completed":
            if any(item is None for item in result) or self.error is not None:
                raise ValueError("Completed experiment requires sealed artifacts and metrics")
        elif any(item is not None for item in result):
            raise ValueError("Incomplete experiment cannot publish completed results")
        if (self.status == "failed") != (self.error is not None):
            raise ValueError("Only failed experiments have a terminal error")
        return self
