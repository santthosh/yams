"""Private immutable admission/read and filesystem-before-database lease fencing."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from backend.domain.common import JobResult, JobV1
from backend.domain.forecast import ForecastV1
from backend.forecasting.artifacts import StoredForecast, publish_forecast, read_forecast_artifacts
from backend.forecasting.contracts import ForecastInputs, ForecastPayload
from backend.forecasting.horizon import map_horizon
from backend.jobs.queue import Lease, Queue, database_now
from backend.market_data.catalog import verified_snapshot
from backend.market_data.files import PinnedSnapshot
from backend.market_data.models import Calendar
from backend.market_data.snapshots import PublicationFenceError
from backend.persistence.models.forecast import Forecast, ForecastArtifact
from backend.persistence.models.job import Job
from backend.persistence.models.portfolio import PaperPortfolio
from backend.persistence.models.snapshot import DatasetSnapshot
from backend.persistence.models.strategy import StrategyVersion
from backend.portfolio.execution import calendar_digest
from backend.strategies.build import engine_fingerprint
from backend.strategies.clock import decision_cutoff
from backend.strategies.registry import version_view


@dataclass(frozen=True)
class ForecastAccepted:
    forecast_id: UUID
    job_id: UUID


@dataclass(frozen=True)
class ForecastRun:
    id: UUID
    job: JobV1
    payload: ForecastPayload
    result: ForecastV1 | None
    manifest_sha256: str | None


def _snapshot_identity(inputs: ForecastInputs, pinned: PinnedSnapshot) -> Calendar:
    calendar = Calendar.model_validate_json(
        pinned.artifacts[pinned.manifest.calendar.artifact_path]
    )
    if (
        pinned.manifest.snapshot_id() != inputs.snapshot_id
        or pinned.manifest.manifest_hash() != inputs.snapshot_sha256
        or pinned.manifest.mode != inputs.source_mode
        or calendar_digest(calendar) != inputs.calendar_sha256
        or decision_cutoff(calendar, inputs.as_of_session) != inputs.decision_cutoff_utc
    ):
        raise ValueError("INPUT_FINGERPRINT_MISMATCH")
    return calendar


def admit_forecast(engine: Engine, root: Path, inputs: ForecastInputs) -> ForecastAccepted:
    """Caller supplies a coherent frozen valuation/preview, never public price overrides."""
    queue = Queue(engine)
    build = engine_fingerprint()
    # Verify immutable files/build before holding the portfolio lock.
    with Session(engine) as session:
        snapshot = session.get(DatasetSnapshot, inputs.snapshot_id)
        version = session.get(StrategyVersion, inputs.strategy_version_id)
        if snapshot is None or version is None:
            raise ValueError("NOT_FOUND")
        pinned = verified_snapshot(snapshot, root)
        _snapshot_identity(inputs, pinned)
        if version_view(version).config_sha256 != inputs.config_sha256:
            raise ValueError("INPUT_FINGERPRINT_MISMATCH")
    if inputs.source_mode == "research_market_data" and inputs.decision_cutoff_utc > datetime.now(
        UTC
    ):
        raise ValueError("DECISION_CUTOFF_NOT_ELAPSED")
    identity = uuid4()
    payload = ForecastPayload(
        forecast_id=identity,
        inputs_canonical_json=inputs.canonical_bytes().decode(),
        engine_version=build,
    )
    with Session(engine) as session, session.begin():
        portfolio = session.execute(
            select(PaperPortfolio).where(PaperPortfolio.id == inputs.portfolio_id).with_for_update()
        ).scalar_one_or_none()
        if portfolio is None:
            raise ValueError("NOT_FOUND")
        if (
            portfolio.revision != inputs.portfolio_revision
            or portfolio.strategy_version_id != inputs.strategy_version_id
            or portfolio.source_mode != inputs.source_mode
        ):
            raise ValueError("STATE_CONFLICT")
        job_id = queue._enqueue(session, "forecast", payload.model_dump(mode="json"), identity)
        session.add(
            Forecast(
                id=identity,
                job_id=job_id,
                portfolio_id=inputs.portfolio_id,
                portfolio_revision=inputs.portfolio_revision,
                strategy_version_id=inputs.strategy_version_id,
                snapshot_id=inputs.snapshot_id,
                payload=payload.model_dump(mode="json"),
                created_at=database_now(session),
            )
        )
    return ForecastAccepted(identity, job_id)


def validate_result(
    payload: ForecastPayload,
    result: StoredForecast,
    pinned: PinnedSnapshot,
    *,
    archived: bool = False,
) -> None:
    inputs = payload.inputs
    calendar = _snapshot_identity(inputs, pinned)
    if (
        result.manifest.forecast_id != payload.forecast_id
        or result.manifest.engine_version != payload.engine_version
        or result.inputs.canonical_bytes() != inputs.canonical_bytes()
    ):
        raise ValueError("Forecast result differs from admitted inputs")
    forecast, metadata = result.forecast, result.metadata
    if archived:
        # Original results are already DB-sealed. Read their recorded endpoint;
        # a native API/restore may have different host TZ bytes or numerical build.
        from backend.forecasting.horizon import Horizon

        horizon = Horizon(forecast.horizon_end_at, forecast.future_sessions, None)
        if horizon.end_at is not None and horizon.sessions is not None:
            expected_days = tuple(
                row.session_date
                for row in calendar.sessions
                if inputs.decision_cutoff_utc < row.close_at <= horizon.end_at
            )
            if horizon.sessions != expected_days:
                raise ValueError("Archived horizon differs from its pinned UTC schedule")
    else:
        horizon = map_horizon(calendar, inputs.decision_cutoff_utc)
    if (
        forecast.horizon_end_at != horizon.end_at
        or forecast.future_sessions != horizon.sessions
        or forecast.horizon_trading_sessions
        != (len(horizon.sessions) if horizon.sessions is not None else None)
        or not set(pinned.manifest.warnings) <= set(forecast.limitations)
        or metadata.get("limitations") != list(forecast.limitations)
        or metadata.get("horizon_end_at")
        != (horizon.end_at.isoformat() if horizon.end_at else None)
        or metadata.get("future_sessions")
        != ([str(day) for day in horizon.sessions] if horizon.sessions is not None else None)
        or metadata.get("input_array_sha256") != forecast.input_array_sha256
        or metadata.get("sampled_indices_sha256")
        != (forecast.sampled_indices.sha256 if forecast.sampled_indices else None)
        or metadata.get("rng_initial_state_sha256")
        != (forecast.rng.initial_state.sha256 if forecast.rng.initial_state else None)
    ):
        raise ValueError("Forecast calendar/evidence metadata differs from pinned inputs")
    if horizon.unavailable_reason and forecast.unavailable_reason != horizon.unavailable_reason:
        raise ValueError("Forecast must disclose unavailable calendar evidence")
    if forecast.status == "available" and metadata.get("asset_order"):
        days = [row.session_date for row in calendar.sessions]
        position = days.index(inputs.as_of_session)
        if position < 252 or metadata.get("input_row_dates") != [
            str(day) for day in days[position - 251 : position + 1]
        ]:
            raise ValueError("Forecast history is not the required common session window")


def seal_forecast(queue: Queue, lease: Lease, root: Path, stage: Path, digest: str) -> None:
    if lease.kind != "forecast":
        raise ValueError("Forecast requires its owning job kind")
    payload = ForecastPayload.model_validate(lease.payload)
    result = read_forecast_artifacts(stage, digest, verify_numerics=True)
    with Session(queue.engine) as session:
        snapshot = session.get(DatasetSnapshot, payload.inputs.snapshot_id)
        if snapshot is None:
            raise ValueError("Forecast source is unavailable")
        pinned = verified_snapshot(snapshot, root)
    validate_result(payload, result, pinned)
    store = root / "forecasts"
    store.mkdir(mode=0o700, parents=True, exist_ok=True)
    key = int.from_bytes(bytes.fromhex(digest)[:8], "big", signed=True)
    with Session(queue.engine) as session, session.begin():
        if not session.execute(
            text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": key}
        ).scalar_one():
            raise PublicationFenceError("Forecast publication is busy")
        job, now = queue.owned(session, lease)
        if (
            job is None
            or job.kind != "forecast"
            or job.status != "running"
            or job.attempt_deadline is None
            or job.attempt_deadline <= now
        ):
            raise PublicationFenceError("Forecast lease is no longer valid")
        row = session.get(Forecast, payload.forecast_id)
        if (
            row is None
            or row.job_id != job.id
            or row.payload != payload.model_dump(mode="json")
            or job.payload != row.payload
            or row.portfolio_id != payload.inputs.portfolio_id
            or row.portfolio_revision != payload.inputs.portfolio_revision
            or row.strategy_version_id != payload.inputs.strategy_version_id
            or row.snapshot_id != payload.inputs.snapshot_id
        ):
            raise ValueError("Forecast admission linkage differs from immutable inputs")
        publish_forecast(stage, store, digest)
        job, now = queue.owned(session, lease)
        if (
            job is None
            or job.status != "running"
            or job.attempt_deadline is None
            or job.attempt_deadline <= now
        ):
            raise PublicationFenceError("Forecast lease expired during publication")
        session.add(
            ForecastArtifact(
                forecast_id=row.id,
                manifest_sha256=digest,
                attempt_token=lease.token,
                completed_at=now,
            )
        )
        job.result = JobResult(
            kind="resource",
            resource_id=row.id,
            message="Immutable scenario comparison sealed; not a calibrated prediction.",
        ).model_dump(mode="json")
        job.status, job.progress = "completed", 100
        queue.finish_attempt(session, job, now, "completed")


def read_forecast(engine: Engine, root: Path, identity: UUID) -> ForecastRun | None:
    with Session(engine) as session:
        row = session.get(Forecast, identity)
        if row is None:
            return None
        job = session.execute(
            select(Job).where(Job.id == row.job_id).with_for_update(read=True)
        ).scalar_one_or_none()
        artifact = session.get(ForecastArtifact, identity)
        if job is None or job.kind != "forecast" or job.payload != row.payload:
            raise ValueError("Forecast job linkage is unavailable")
        payload = ForecastPayload.model_validate(row.payload)
        view = Queue.view(job)
        if (view.status == "completed") != (artifact is not None):
            raise ValueError("Forecast completion differs from sealed evidence")
        result, digest = None, None
        if artifact is not None:
            if view.result is None or view.result.resource_id != row.id:
                raise ValueError("Forecast resource identity differs from completion")
            digest = artifact.manifest_sha256
            stored = read_forecast_artifacts(root / "forecasts" / digest, digest)
            snapshot = session.get(DatasetSnapshot, payload.inputs.snapshot_id)
            if snapshot is None:
                raise ValueError("Forecast source is unavailable")
            validate_result(payload, stored, verified_snapshot(snapshot, root), archived=True)
            result = stored.forecast
        return ForecastRun(row.id, view, payload, result, digest)
