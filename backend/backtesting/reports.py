"""Public projections of the shared core/report; no financial execution here."""

from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from backend.backtesting.benchmark import BacktestMetricsReport
from backend.backtesting.contracts import BacktestCorePayload
from backend.backtesting.metrics import drawdown_series
from backend.backtesting.runner import BacktestCoreResult
from backend.domain.experiment import MetricValue
from backend.domain.experiment_api import (
    ExperimentBenchmarkSummaryV1,
    ExperimentCurvePointV1,
    ExperimentReportSummaryV1,
    ExperimentReproducibilityV1,
    ExperimentTradeV1,
    WeightValue,
)
from backend.domain.strategy import StrategyConfigV1
from backend.domain.types import decimal_text


def weight(value: MetricValue) -> WeightValue:
    return WeightValue(
        value=decimal_text(Decimal(str(value.value))) if value.value is not None else None,
        unavailable_reason=value.unavailable_reason,
    )


def project_report(
    payload: BacktestCorePayload,
    core: BacktestCoreResult,
    report: BacktestMetricsReport,
    provider: str,
) -> tuple[
    ExperimentReportSummaryV1,
    tuple[ExperimentCurvePointV1, ...],
    tuple[ExperimentTradeV1, ...],
    ExperimentReproducibilityV1,
]:
    summary = ExperimentReportSummaryV1(
        **report.model_dump(exclude={"benchmark", "cash_nav_usd", "exposures", "schema_version"}),
        benchmark=ExperimentBenchmarkSummaryV1(
            **report.benchmark.model_dump(exclude={"sessions", "nav_usd"})
        ),
    )
    drawdowns = drawdown_series(tuple(point.nav_usd for point in core.points))
    series = tuple(
        ExperimentCurvePointV1(
            session_date=point.session_date,
            phase=point.phase,
            portfolio_nav_usd=point.nav_usd,
            cash_usd=point.state.cash_usd,
            positions=point.state.positions,
            benchmark_nav_usd=benchmark,
            benchmark_unavailable_reason=(
                report.benchmark.unavailable_reason if benchmark is None else None
            ),
            cash_baseline_nav_usd=cash,
            drawdown_fraction=drawdown,
            cash_weight=weight(exposure.cash_weight),
            max_position_weight=weight(exposure.max_position_weight),
        )
        for point, benchmark, cash, exposure, drawdown in zip(
            core.points,
            report.benchmark.nav_usd,
            report.cash_nav_usd,
            report.exposures,
            drawdowns,
            strict=True,
        )
    )
    # Content-based IDs remain stable across reruns; resource IDs remain distinct.
    trades = tuple(
        ExperimentTradeV1(
            **execution.model_dump(),
            id=uuid5(NAMESPACE_URL, "yams:execution:" + execution.model_dump_json()),
        )
        for execution in core.executions
    )
    reproducibility = ExperimentReproducibilityV1(
        inputs=payload.inputs,
        strategy_config=StrategyConfigV1.from_json(payload.config_canonical_json),
        config_sha256=payload.config_sha256,
        snapshot_sha256=payload.snapshot_sha256,
        calendar_sha256=payload.calendar_sha256,
        core_manifest_sha256=report.core_manifest_sha256,
        engine_version=payload.engine_version,
        reporting_engine_version=report.reporting_engine_version,
        source_mode=payload.source_mode,
        provider=provider,
        core_policy_version=core.policy_version,
        reporting_version=report.reporting_version,
        decision_clock_policy="next_pinned_open_minus_one_hour",
        warnings=report.warnings,
    )
    return summary, series, trades, reproducibility
