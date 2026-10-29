"""Read-only bounded preparation in the supervised child; no financial DB writes."""

from datetime import UTC, datetime
from multiprocessing.synchronize import Event
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from backend.domain.fill_job import ScheduledFillPayload
from backend.domain.market import AssetV1, MarketBarV1
from backend.jobs.registry import validate_workload
from backend.market_data.files import PinnedSnapshot
from backend.market_data.models import Calendar, CorporateAction
from backend.market_data.repository import MarketRepository
from backend.portfolio.execution import MarketEvidence
from backend.portfolio.fills import PreparedFill
from backend.strategies.build import engine_fingerprint


def apply_scheduled_fills(payload: dict[str, Any], cancelled: Event, *, root: Path) -> str:
    config = ScheduledFillPayload.model_validate(payload)
    if cancelled.is_set():
        raise ValueError("Cancelled preparation")
    original = PinnedSnapshot.open(
        root / "snapshots" / config.decision_snapshot_sha256, config.decision_snapshot_sha256
    )
    execution = PinnedSnapshot.open(
        root / "snapshots" / config.execution_snapshot_sha256, config.execution_snapshot_sha256
    )
    if (original.manifest.snapshot_id(), execution.manifest.snapshot_id()) != (
        config.decision_snapshot_id,
        config.execution_snapshot_id,
    ):
        raise ValueError("Snapshot identities differ")
    if (
        original.manifest.mode != config.source_mode
        or execution.manifest.mode != config.source_mode
    ):
        raise ValueError("Source mode differs")
    if config.source_mode != "synthetic_fixture":
        raise ValueError("Unsupported accounting source")

    def identity(source: PinnedSnapshot) -> tuple[str, ...]:
        artifacts = [
            a
            for a in source.manifest.artifacts
            if a.role == "assets" and a.schema_version == 1 and a.format == "json"
        ]
        if len(artifacts) != 1:
            raise ValueError("Unsupported asset identity inventory")
        assets = TypeAdapter(tuple[AssetV1, ...]).validate_json(source.artifacts[artifacts[0].path])
        matches = [a for a in assets if a.asset_id == config.asset_id]
        if len(matches) != 1:
            raise ValueError("Missing canonical execution asset")
        a = matches[0]
        return (a.asset_id, a.venue, a.currency, a.instrument, a.provider, a.provider_id)

    if identity(original) != identity(execution):
        raise ValueError("Execution asset identity changed")
    calendar = Calendar.model_validate_json(
        original.artifacts[original.manifest.calendar.artifact_path]
    )
    observed = config.fixture_observed_at or datetime.now(UTC)
    with MarketRepository(execution) as repository:
        validate_workload(
            assets=len(execution.manifest.coverage.asset_ids),
            sessions=len(repository.calendar.sessions),
        )
        completed = [
            row.session_date for row in repository.calendar.sessions if row.close_at <= observed
        ]
        bars: tuple[MarketBarV1, ...]
        actions: tuple[CorporateAction, ...]
        if not completed:
            bars = ()
            actions = ()
        else:
            view = repository.accounting_as_of(observed, max(completed))
            bars = tuple(
                row
                for row in view.bars
                if row.asset_id == config.asset_id and row.session_date == config.eligible_session
            )
            actions = tuple(
                row for row in view.actions if row.effective_session <= config.eligible_session
            )
        result = PreparedFill(
            payload=config,
            calendar=calendar,
            execution_calendar=repository.calendar,
            observed_at=observed,
            execution_engine_version=engine_fingerprint(),
            market=MarketEvidence(
                snapshot_id=config.execution_snapshot_id,
                snapshot_sha256=config.execution_snapshot_sha256,
                mode=config.source_mode,
                freshness="fixture",
                bars=bars,
            ),
            actions=actions,
        ).model_dump_json()
    if cancelled.is_set() or len(result.encode()) > 2 * 1024 * 1024:
        raise ValueError("Cancelled or oversized fill preparation")
    return result
