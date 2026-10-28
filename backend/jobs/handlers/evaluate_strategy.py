"""Read-only pinned diagnostics inside the supervised resource-limited child."""

from datetime import UTC, datetime
from multiprocessing.synchronize import Event
from pathlib import Path
from typing import Any, Literal

from backend.domain.evaluation import StrategyEvaluationPayload
from backend.domain.strategy import StrategyConfigV1
from backend.market_data.files import PinnedSnapshot
from backend.market_data.models import Calendar
from backend.portfolio.allocation import allocate_momentum
from backend.portfolio.execution import calendar_digest
from backend.strategies.build import engine_fingerprint
from backend.strategies.clock import decision_cutoff
from backend.strategies.evaluations import MAX_RESULT_BYTES, result_from_engine
from backend.strategies.momentum import evaluate_snapshot


class EvaluationFailure(Exception):
    def __init__(self, code: Literal["VALIDATION_ERROR", "STALE_DATA"]):
        self.code = code
        super().__init__(code)


def evaluate_strategy(payload: dict[str, Any], cancelled: Event, *, root: Path) -> str:
    config = StrategyEvaluationPayload.model_validate(payload)
    rules = StrategyConfigV1.from_json(config.config_canonical_json)
    if cancelled.is_set():
        raise EvaluationFailure("VALIDATION_ERROR")
    pinned = PinnedSnapshot.open(
        root / "snapshots" / config.snapshot_sha256, config.snapshot_sha256
    )
    manifest = pinned.manifest
    calendar = Calendar.model_validate_json(pinned.artifacts[manifest.calendar.artifact_path])
    cutoff = decision_cutoff(calendar, config.inputs.as_of_session)
    if (
        manifest.snapshot_id() != config.inputs.snapshot_id
        or manifest.mode != config.source_mode
        or rules.config_hash() != config.config_sha256
        or calendar_digest(calendar) != config.calendar_sha256
        or engine_fingerprint() != config.engine_version
        or cutoff != config.decision_cutoff_utc
    ):
        raise EvaluationFailure("VALIDATION_ERROR")
    if manifest.quality == "blocked":
        raise EvaluationFailure("STALE_DATA")
    if manifest.mode == "research_market_data" and cutoff > datetime.now(UTC):
        raise EvaluationFailure("VALIDATION_ERROR")
    measured = allocate_momentum(
        evaluate_snapshot(
            pinned,
            rules,
            cutoff,
            config.inputs.as_of_session,
            engine_version=config.engine_version,
        ),
        rules,
    )
    if cancelled.is_set():
        raise EvaluationFailure("VALIDATION_ERROR")
    value = result_from_engine(config, measured).model_dump_json()
    if len(value.encode()) > MAX_RESULT_BYTES:
        raise EvaluationFailure("VALIDATION_ERROR")
    return value
