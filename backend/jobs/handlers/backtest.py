"""Supervised pinned core computation; child can stage but cannot register output."""

from collections.abc import Callable
from multiprocessing.synchronize import Event
from pathlib import Path
from typing import Any

from backend.backtesting.artifacts import stage_core
from backend.backtesting.contracts import BacktestCorePayload
from backend.backtesting.errors import BacktestFailure
from backend.backtesting.runner import run_backtest
from backend.domain.strategy import StrategyConfigV1
from backend.market_data.files import PinnedSnapshot
from backend.market_data.models import Calendar
from backend.market_data.repository import MarketRepository
from backend.portfolio.execution import calendar_digest
from backend.strategies.build import engine_fingerprint


def backtest_core(
    payload: dict[str, Any],
    cancelled: Event,
    progress: Callable[[int, int], None] = lambda completed, total: None,
    *,
    root: Path,
    stage: Path,
) -> str:
    pinned_input = BacktestCorePayload.model_validate(payload)
    if pinned_input.engine_version != engine_fingerprint():
        raise BacktestFailure("INPUT_FINGERPRINT_MISMATCH")
    snapshot = PinnedSnapshot.open(
        root / "snapshots" / pinned_input.snapshot_sha256, pinned_input.snapshot_sha256
    )
    calendar = Calendar.model_validate_json(
        snapshot.artifacts[snapshot.manifest.calendar.artifact_path]
    )
    if (
        snapshot.manifest.mode != pinned_input.source_mode
        or snapshot.manifest.snapshot_id() != pinned_input.inputs.snapshot_id
        or calendar_digest(calendar) != pinned_input.calendar_sha256
    ):
        raise BacktestFailure("INPUT_FINGERPRINT_MISMATCH")
    with MarketRepository(snapshot) as repository:
        result = run_backtest(
            repository,
            pinned_input.inputs,
            StrategyConfigV1.from_json(pinned_input.config_canonical_json),
            engine_version=pinned_input.engine_version,
            cancelled=cancelled.is_set,
            progress=progress,
        )
    if cancelled.is_set():
        raise BacktestFailure("CANCELLED")
    return stage_core(stage, result)


def backtest(
    payload: dict[str, Any],
    cancelled: Event,
    progress: Callable[[int, int], None] = lambda completed, total: None,
    *,
    root: Path,
    stage: Path,
) -> str:
    """One bounded job computes all output; only the supervisor can publish it."""
    from backend.backtesting.artifacts import read_core
    from backend.backtesting.benchmark import calculate_report
    from backend.backtesting.report_artifacts import stage_report
    from backend.backtesting.reports import project_report

    stage.mkdir(mode=0o700, exist_ok=False)
    digest = backtest_core(
        payload,
        cancelled,
        lambda completed, total: progress(completed * 80 // total, 100),
        root=root,
        stage=stage / "core",
    )
    core = read_core(stage / "core", digest)
    pinned = BacktestCorePayload.model_validate(payload)
    snapshot = PinnedSnapshot.open(
        root / "snapshots" / pinned.snapshot_sha256, pinned.snapshot_sha256
    )
    if cancelled.is_set():
        raise BacktestFailure("CANCELLED")
    with MarketRepository(snapshot) as repository:
        report = calculate_report(pinned, core, digest, repository)
    progress(95, 100)
    output = project_report(pinned, core, report, snapshot.manifest.source.provider)
    if cancelled.is_set():
        raise BacktestFailure("CANCELLED")
    report_digest = stage_report(stage / "report", *output)
    progress(99, 100)
    return report_digest
