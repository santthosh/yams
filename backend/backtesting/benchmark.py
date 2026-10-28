"""Aligned SPY/cash references and readonly report composition under ADR-013."""

import hashlib
from decimal import Decimal
from fractions import Fraction
from typing import Literal, Self

from pydantic import StrictBool, TypeAdapter, model_validator

from backend.backtesting.contracts import BacktestCorePayload
from backend.backtesting.metrics import MetricsPeriods, metrics_periods, statistic, unavailable
from backend.backtesting.runner import BacktestCoreResult, validate_source
from backend.backtesting.service import CoreRun, validate_result
from backend.domain.experiment import EvaluationSplit, MetricValue
from backend.domain.market import AssetV1
from backend.domain.strategy import StrategyConfigV1
from backend.domain.types import (
    AssetId,
    Contract,
    Hash256,
    Money,
    Reason,
    SessionDate,
    SourceMode,
    canonical_json,
    load_json,
)
from backend.market_data.repository import MarketRepository
from backend.portfolio.execution import (
    DEFAULT_EXECUTION_POLICY,
    ExecutionContext,
    ExecutionPolicy,
    MarketEvidence,
    arithmetic,
    calendar_digest,
    money,
)
from backend.portfolio.valuation import value_close
from backend.strategies.build import engine_fingerprint
from backend.strategies.clock import decision_cutoff

REPORTING_VERSION = "q12_v1"
BENCHMARK_WARNINGS = (
    "BENCHMARK_ADJUSTED_TOTAL_RETURN_APPROXIMATION",
    "BENCHMARK_DIVIDEND_RECOGNITION_DIFFERS",
    "BENCHMARK_FRICTION_FREE_FULLY_INVESTED",
    "BENCHMARK_INITIAL_CLOSE_DIFFERS_FROM_NEXT_OPEN",
)


class BenchmarkCurve(Contract):
    asset_id: AssetId
    sessions: tuple[SessionDate, ...]
    nav_usd: tuple[Money | None, ...]
    available: StrictBool
    unavailable_reason: Reason | None
    periods: MetricsPeriods | None
    warnings: tuple[Reason, ...]

    @model_validator(mode="after")
    def complete_alignment(self) -> Self:
        if len(self.sessions) != len(self.nav_usd):
            raise ValueError("Benchmark retains every original core session")
        if self.available:
            if self.unavailable_reason is not None or self.periods is None:
                raise ValueError("Benchmark availability requires complete statistics")
        elif self.unavailable_reason is None or self.periods is not None:
            raise ValueError("Unavailable benchmark requires a reason and no statistics")
        if self.available and any(value is None for value in self.nav_usd):
            raise ValueError("Available benchmark cannot contain a gap")
        return self


class ExposurePoint(Contract):
    session_date: SessionDate
    cash_weight: MetricValue
    max_position_weight: MetricValue


class ComparisonTerms(Contract):
    snapshot_sha256: Hash256
    calendar_sha256: Hash256
    core_engine_version: str
    reporting_engine_version: Hash256
    core_policy_version: Literal["walk_forward_v1"]
    reporting_version: Literal["q12_v1"] = "q12_v1"
    source_mode: SourceMode
    sessions: tuple[SessionDate, ...]
    start_session: SessionDate
    end_session_exclusive: SessionDate
    initial_capital_usd: Money
    universe_canonical_json: str
    execution_policy: ExecutionPolicy
    benchmark_asset_id: AssetId
    evaluation_split: EvaluationSplit
    holdout_start_session: SessionDate | None

    def fingerprint(self) -> str:
        return hashlib.sha256(canonical_json(load_json(self.model_dump_json()))).hexdigest()

    def differences(self, other: "ComparisonTerms") -> tuple[Reason, ...]:
        return tuple(
            "INCOMPARABLE_" + field.upper()
            for field in type(self).model_fields
            if getattr(self, field) != getattr(other, field)
        )


class BacktestMetricsReport(Contract):
    schema_version: Literal[1] = 1
    reporting_version: Literal["q12_v1"] = "q12_v1"
    core_manifest_sha256: Hash256
    reporting_engine_version: Hash256
    comparison: ComparisonTerms
    comparison_sha256: Hash256
    portfolio: MetricsPeriods
    benchmark: BenchmarkCurve
    cash_nav_usd: tuple[Money, ...]
    cash: MetricsPeriods
    exposures: tuple[ExposurePoint, ...]
    warnings: tuple[Reason, ...]


def comparison_terms(core: BacktestCoreResult, config: StrategyConfigV1) -> ComparisonTerms:
    if config.config_hash() != core.config_sha256:
        raise ValueError("Comparison config differs from sealed core")
    canonical = load_json(config.canonical_bytes())
    if not isinstance(canonical, dict):
        raise ValueError("Expected a canonical strategy object")
    return ComparisonTerms(
        snapshot_sha256=core.snapshot_sha256,
        calendar_sha256=core.calendar_sha256,
        core_engine_version=core.engine_version,
        reporting_engine_version=engine_fingerprint(),
        core_policy_version=core.policy_version,
        source_mode=core.source_mode,
        sessions=tuple(row.session_date for row in core.points),
        start_session=core.inputs.start_session,
        end_session_exclusive=core.inputs.end_session_exclusive,
        initial_capital_usd=money(Decimal(core.inputs.initial_capital_usd)),
        universe_canonical_json=canonical_json(canonical["universe"]).decode(),
        execution_policy=DEFAULT_EXECUTION_POLICY,
        benchmark_asset_id=core.inputs.benchmark_asset_id,
        evaluation_split=core.inputs.evaluation_split,
        holdout_start_session=core.holdout_start_session,
    )


def _verify_source(repository: MarketRepository, core: BacktestCoreResult) -> None:
    validate_source(repository)
    manifest = repository.snapshot.manifest
    if (
        manifest.manifest_hash() != core.snapshot_sha256
        or manifest.snapshot_id() != core.inputs.snapshot_id
        or manifest.mode != core.source_mode
        or calendar_digest(repository.calendar) != core.calendar_sha256
    ):
        raise ValueError("Report source differs from immutable core")


def benchmark_curve(repository: MarketRepository, core: BacktestCoreResult) -> BenchmarkCurve:
    _verify_source(repository, core)
    manifest = repository.snapshot.manifest
    inventory = next(
        row for row in manifest.artifacts if row.role == "assets" and row.schema_version == 1
    )
    assets = TypeAdapter(tuple[AssetV1, ...]).validate_json(
        repository.snapshot.artifacts[inventory.path]
    )
    identity = next((row for row in assets if row.asset_id == core.inputs.benchmark_asset_id), None)
    sessions = tuple(row.session_date for row in core.points)
    warnings = set(BENCHMARK_WARNINGS)
    if identity is None or identity.instrument != "etf" or identity.symbol != "SPY":
        return BenchmarkCurve(
            asset_id=core.inputs.benchmark_asset_id,
            sessions=sessions,
            nav_usd=tuple(None for _ in sessions),
            available=False,
            unavailable_reason="UNSUPPORTED_BENCHMARK",
            periods=None,
            warnings=tuple(sorted(warnings | {"UNSUPPORTED_BENCHMARK"})),
        )
    prices: list[str | None] = []
    for day in sessions:
        view = repository.accounting_as_of(decision_cutoff(repository.calendar, day), day)
        bar = next(
            (
                row
                for row in view.bars
                if row.asset_id == identity.asset_id and row.session_date == day
            ),
            None,
        )
        prices.append(
            bar.adjusted_close
            if bar is not None and not set(bar.quality_flags) - {"SYNTHETIC_DATA_ONLY"}
            else None
        )
    values: list[str | None] = []
    for price in prices:
        if not prices or prices[0] is None or price is None:
            values.append(None)
        else:
            with arithmetic(core.inputs.initial_capital_usd, price, prices[0]):
                value = money(
                    Decimal(core.inputs.initial_capital_usd) * Decimal(price) / Decimal(prices[0])
                )
            try:
                values.append(TypeAdapter(Money).validate_python(value))
            except ValueError:
                values.append(None)
                warnings.add("NUMERICAL_RANGE")
    available = all(value is not None for value in values) and bool(values)
    periods = (
        metrics_periods(
            core, tuple(value for value in values if value is not None), include_trades=False
        )
        if available
        else None
    )
    if not available:
        warnings.add("INSUFFICIENT_MARKET_DATA")
    return BenchmarkCurve(
        asset_id=identity.asset_id,
        sessions=sessions,
        nav_usd=tuple(values),
        available=available,
        unavailable_reason=None if available else "INSUFFICIENT_MARKET_DATA",
        periods=periods,
        warnings=tuple(sorted(warnings)),
    )


def exposure_series(
    repository: MarketRepository, core: BacktestCoreResult
) -> tuple[ExposurePoint, ...]:
    _verify_source(repository, core)
    points = []
    for point in core.points:
        cutoff = decision_cutoff(repository.calendar, point.session_date)
        view = repository.accounting_as_of(cutoff, point.session_date)
        context = ExecutionContext(
            snapshot_id=core.inputs.snapshot_id,
            snapshot_sha256=core.snapshot_sha256,
            calendar_sha256=core.calendar_sha256,
            mode=core.source_mode,
            engine_version=core.engine_version,
            execution_mode="historical_replay",
            decision_session=point.session_date,
            decision_cutoff=cutoff,
            approved_at=cutoff,
        )
        marks = MarketEvidence(
            snapshot_id=core.inputs.snapshot_id,
            snapshot_sha256=core.snapshot_sha256,
            mode=core.source_mode,
            freshness="fixture" if core.source_mode == "synthetic_fixture" else "fresh",
            bars=view.bars,
        )
        valuation = value_close(point.state, context, repository.calendar, marks)
        if valuation.nav is None or valuation.money_value() != point.nav_usd:
            cash = concentration = unavailable("INSUFFICIENT_MARKET_DATA")
        elif valuation.nav == 0:
            cash = concentration = unavailable("ZERO_NAV")
        else:
            cash = statistic(Fraction(point.state.cash_usd) / valuation.nav)
            concentration = statistic(
                max(valuation.values.values(), default=Fraction()) / valuation.nav
            )
        points.append(
            ExposurePoint(
                session_date=point.session_date, cash_weight=cash, max_position_weight=concentration
            )
        )
    return tuple(points)


def calculate_report(
    payload: BacktestCorePayload,
    core: BacktestCoreResult,
    core_manifest_sha256: str,
    repository: MarketRepository,
) -> BacktestMetricsReport:
    """Compose complete validated core evidence within a still-running report job.

    The caller owns the verified core seal; this calculation does not publish it
    or complete a job. #41 can seal core plus report atomically after calculation.
    """
    _verify_source(repository, core)
    validate_result(payload, core, repository.calendar)
    rules = StrategyConfigV1.from_json(payload.config_canonical_json)
    terms = comparison_terms(core, rules)
    benchmark = benchmark_curve(repository, core)
    cash = tuple(money(Decimal(core.inputs.initial_capital_usd)) for _ in core.points)
    return BacktestMetricsReport(
        core_manifest_sha256=core_manifest_sha256,
        reporting_engine_version=engine_fingerprint(),
        comparison=terms,
        comparison_sha256=terms.fingerprint(),
        portfolio=metrics_periods(core),
        benchmark=benchmark,
        cash_nav_usd=cash,
        cash=metrics_periods(core, cash, include_trades=False),
        exposures=exposure_series(repository, core),
        warnings=tuple(sorted(set(core.warnings) | set(benchmark.warnings))),
    )


def build_report(run: CoreRun, repository: MarketRepository) -> BacktestMetricsReport:
    """Readonly reporting of an already persisted complete internal core."""
    if run.job.status != "completed" or run.result is None or run.manifest_sha256 is None:
        raise ValueError("Reporting requires a complete sealed core")
    return calculate_report(run.payload, run.result, run.manifest_sha256, repository)
