"""Public experiment projections; bulk financial samples stay in bounded pages."""

from typing import Literal, Self
from uuid import UUID

from pydantic import model_validator

from backend.backtesting.benchmark import ComparisonTerms
from backend.backtesting.metrics import MetricsPeriods
from backend.domain.common import ErrorDetail, JobStatus, Page
from backend.domain.experiment import ExperimentRequest, ExperimentRunV1, MetricValue
from backend.domain.strategy import StrategyConfigV1
from backend.domain.types import (
    Contract,
    FractionString,
    Hash256,
    Money,
    Reason,
    SessionDate,
    SourceMode,
    UTCTimestamp,
)
from backend.portfolio.execution import ExecutionResult, Position


class ExperimentAccepted(Contract):
    experiment_id: UUID
    job_id: UUID


class JobCancelRequest(Contract):
    """Explicit empty JSON command; extra fields are forbidden."""


class WeightValue(Contract):
    value: FractionString | None
    unavailable_reason: Reason | None

    @model_validator(mode="after")
    def reason_for_null(self) -> Self:
        if (self.value is None) != (self.unavailable_reason is not None):
            raise ValueError("Unavailable weight requires a reason")
        return self


class ExperimentBenchmarkSummaryV1(Contract):
    asset_id: str
    available: bool
    unavailable_reason: Reason | None
    periods: MetricsPeriods | None
    warnings: tuple[Reason, ...]

    @model_validator(mode="after")
    def complete_or_unavailable(self) -> Self:
        if self.available:
            if self.unavailable_reason is not None or self.periods is None:
                raise ValueError("Available benchmark requires its complete metrics")
        elif self.unavailable_reason is None or self.periods is not None:
            raise ValueError("Unavailable benchmark requires a reason and no metrics")
        return self


class ExperimentReportSummaryV1(Contract):
    reporting_version: Literal["q12_v1"]
    core_manifest_sha256: Hash256
    reporting_engine_version: Hash256
    comparison: ComparisonTerms
    comparison_sha256: Hash256
    portfolio: MetricsPeriods
    benchmark: ExperimentBenchmarkSummaryV1
    cash: MetricsPeriods
    warnings: tuple[Reason, ...]

    @model_validator(mode="after")
    def pinned_comparison(self) -> Self:
        if (
            self.comparison_sha256 != self.comparison.fingerprint()
            or self.reporting_engine_version != self.comparison.reporting_engine_version
        ):
            raise ValueError("Report comparison differs from its pinned provenance")
        return self


class ExperimentDetailV1(ExperimentRunV1):
    currency: Literal["USD"] = "USD"
    provider: str
    strategy_config: StrategyConfigV1
    report: ExperimentReportSummaryV1 | None

    @model_validator(mode="after")
    def complete_report(self) -> Self:
        if (self.status == "completed") != (self.report is not None):
            raise ValueError("Only completed public experiments expose a complete report")
        if self.strategy_config.config_hash() != self.config_sha256:
            raise ValueError("Experiment config differs from its immutable fingerprint")
        if self.report is not None and (
            self.metrics != self.report.portfolio.total.metrics
            or self.snapshot_sha256 != self.report.comparison.snapshot_sha256
            or self.engine_version != self.report.comparison.core_engine_version
            or self.data_status != self.report.comparison.source_mode
        ):
            raise ValueError("Experiment report differs from its pinned financial evidence")
        return self


class ExperimentSummaryV1(Contract):
    id: UUID
    job_id: UUID
    status: JobStatus
    inputs: ExperimentRequest
    config_sha256: Hash256
    snapshot_sha256: Hash256
    data_status: SourceMode
    created_at: UTCTimestamp
    engine_version: str
    error: ErrorDetail | None

    @model_validator(mode="after")
    def failed_error(self) -> Self:
        if (self.status == "failed") != (self.error is not None):
            raise ValueError("Only failed experiment summaries include an error")
        return self


class ExperimentCurvePointV1(Contract):
    session_date: SessionDate
    currency: Literal["USD"] = "USD"
    phase: Literal["development", "holdout"]
    portfolio_nav_usd: Money
    cash_usd: Money
    positions: tuple[Position, ...]
    benchmark_nav_usd: Money | None
    benchmark_unavailable_reason: Reason | None
    cash_baseline_nav_usd: Money
    drawdown_fraction: MetricValue
    cash_weight: WeightValue
    max_position_weight: WeightValue

    @model_validator(mode="after")
    def benchmark_gap_reason(self) -> Self:
        if (self.benchmark_nav_usd is None) != (self.benchmark_unavailable_reason is not None):
            raise ValueError("Missing benchmark point requires an explicit reason")
        return self


class ExperimentTradeV1(ExecutionResult):
    id: UUID
    currency: Literal["USD"] = "USD"


class ExperimentReproducibilityV1(Contract):
    schema_version: Literal[1] = 1
    inputs: ExperimentRequest
    strategy_config: StrategyConfigV1
    config_sha256: Hash256
    snapshot_sha256: Hash256
    calendar_sha256: Hash256
    core_manifest_sha256: Hash256
    engine_version: Hash256
    reporting_engine_version: Hash256
    source_mode: SourceMode
    provider: str
    core_policy_version: Literal["walk_forward_v1"]
    reporting_version: Literal["q12_v1"]
    decision_clock_policy: Literal["next_pinned_open_minus_one_hour"]
    warnings: tuple[Reason, ...]


class ExperimentPageV1(Page[ExperimentSummaryV1]):
    pass


class ExperimentSeriesPageV1(Page[ExperimentCurvePointV1]):
    pass


class ExperimentTradesPageV1(Page[ExperimentTradeV1]):
    pass
