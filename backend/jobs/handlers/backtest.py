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
