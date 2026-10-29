"""Pure frozen-state recommendation evaluation within the bounded Linux child."""

from collections.abc import Callable
from multiprocessing.synchronize import Event
from pathlib import Path
from typing import Any

from backend.forecasting.bootstrap import ForecastCancelled
from backend.market_data.files import PinnedSnapshot
from backend.portfolio.recommendation_contracts import (
    MAX_RECOMMENDATION_BYTES,
    RecommendationComputed,
    RecommendationPayload,
)
from backend.portfolio.recommendation_engine import compose_recommendation, prepare_recommendation
from backend.portfolio.recommendation_errors import (
    SAFE_RECOMMENDATION_REASONS,
    RecommendationFailure,
)
from backend.strategies.build import engine_fingerprint


def evaluate_portfolio(
    payload: dict[str, Any],
    cancelled: Event,
    progress: Callable[[int, int], None] = lambda done, total: None,
    *,
    root: Path,
) -> str:
    frozen = RecommendationPayload.model_validate(payload)
    if engine_fingerprint() != frozen.engine_version:
        raise RecommendationFailure("INPUT_FINGERPRINT_MISMATCH")
    if frozen.source_mode != "synthetic_fixture":
        raise RecommendationFailure("UNSUPPORTED_ACCOUNTING_SOURCE")
    if cancelled.is_set():
        raise ForecastCancelled()
    pinned = PinnedSnapshot.open(
        root / "snapshots" / frozen.snapshot_sha256, frozen.snapshot_sha256
    )
    progress(5, 100)
    try:
        prepared = prepare_recommendation(pinned, frozen, cancelled=cancelled.is_set)
        progress(80, 100)
        result, forecast = compose_recommendation(frozen, prepared, pinned)
    except InterruptedError:
        raise ForecastCancelled() from None
    except ValueError as error:
        if str(error) in SAFE_RECOMMENDATION_REASONS:
            raise RecommendationFailure(str(error)) from None
        raise
    if cancelled.is_set():
        raise ForecastCancelled()
    encoded = RecommendationComputed(
        prepared=prepared, recommendation=result, forecast_inputs=forecast
    ).model_dump_json()
    if len(encoded.encode()) > MAX_RECOMMENDATION_BYTES:
        raise RecommendationFailure("WORKLOAD_LIMIT")
    progress(99, 100)
    return encoded
