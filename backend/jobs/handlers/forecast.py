"""Read-only scenario computation in the supervised child; parent alone publishes."""

from collections.abc import Callable
from multiprocessing.synchronize import Event
from pathlib import Path
from typing import Any

from backend.forecasting.artifacts import stage_forecast
from backend.forecasting.bootstrap import ForecastCancelled
from backend.forecasting.contracts import ForecastPayload
from backend.forecasting.errors import ForecastFailure
from backend.forecasting.scenarios import compare_scenarios
from backend.market_data.files import PinnedSnapshot
from backend.market_data.repository import MarketRepository
from backend.strategies.build import engine_fingerprint


def forecast(
    payload: dict[str, Any],
    cancelled: Event,
    progress: Callable[[int, int], None] = lambda completed, total: None,
    *,
    root: Path,
    stage: Path,
) -> str:
    pinned = ForecastPayload.model_validate(payload)
    if pinned.engine_version != engine_fingerprint():
        raise ForecastFailure("INPUT_FINGERPRINT_MISMATCH")
    if cancelled.is_set():
        raise ForecastCancelled()
    inputs = pinned.inputs
    snapshot = PinnedSnapshot.open(
        root / "snapshots" / inputs.snapshot_sha256, inputs.snapshot_sha256
    )
    with MarketRepository(snapshot) as repository:
        bundle = compare_scenarios(
            repository,
            inputs,
            forecast_id=pinned.forecast_id,
            engine_version=pinned.engine_version,
            cancelled=cancelled.is_set,
            progress=lambda done, total: progress(done * 95 // total, 100),
        )
    if cancelled.is_set():
        raise ForecastCancelled()
    digest = stage_forecast(stage, pinned, bundle)
    progress(99, 100)
    return digest
