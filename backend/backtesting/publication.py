"""Lease-fenced registration of complete core and report as one public result."""

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.backtesting.artifacts import publish_core, read_core
from backend.backtesting.contracts import BacktestCorePayload
from backend.backtesting.metrics import metrics_periods
from backend.backtesting.report_artifacts import (
    publish_report,
    read_artifact,
    verify_report,
)
from backend.backtesting.service import validate_result
from backend.domain.common import JobResult
from backend.domain.experiment_api import (
    ExperimentCurvePointV1,
    ExperimentReportSummaryV1,
    ExperimentReproducibilityV1,
    ExperimentTradeV1,
)
from backend.jobs.queue import Lease, Queue
from backend.market_data.catalog import verified_snapshot
from backend.market_data.models import Calendar
from backend.market_data.snapshots import PublicationFenceError
from backend.persistence.models.experiment import Experiment, ExperimentCore, ExperimentReport
from backend.persistence.models.snapshot import DatasetSnapshot


def seal_report(queue: Queue, lease: Lease, root: Path, stage: Path, digest: str) -> None:
    if lease.kind != "backtest":
        raise ValueError("Report requires its owning job kind")
    payload = BacktestCorePayload.model_validate(lease.payload)
    manifest = verify_report(stage / "report", digest)
    core_digest = manifest.core_manifest_sha256
    core = read_core(stage / "core", core_digest)
    summary = ExperimentReportSummaryV1.model_validate_json(
        read_artifact(stage / "report", manifest, "summary")
    )
    repro = ExperimentReproducibilityV1.model_validate_json(
        read_artifact(stage / "report", manifest, "reproducibility")
    )
    with Session(queue.engine) as session:
        snapshot = session.get(DatasetSnapshot, payload.inputs.snapshot_id)
        if snapshot is None:
            raise ValueError("Report snapshot is unavailable")
        pinned = verified_snapshot(snapshot, root)
    calendar = Calendar.model_validate_json(
        pinned.artifacts[pinned.manifest.calendar.artifact_path]
    )
    validate_result(payload, core, calendar)
    if (
        manifest.config_sha256 != payload.config_sha256
        or manifest.snapshot_sha256 != payload.snapshot_sha256
        or manifest.calendar_sha256 != payload.calendar_sha256
        or manifest.engine_version != payload.engine_version
        or manifest.reporting_engine_version != summary.reporting_engine_version
        or summary.core_manifest_sha256 != core_digest
        or summary.comparison.core_engine_version != payload.engine_version
        or summary.comparison.snapshot_sha256 != payload.snapshot_sha256
        or summary.comparison.calendar_sha256 != payload.calendar_sha256
        or summary.comparison.sessions != tuple(point.session_date for point in core.points)
        or summary.portfolio != metrics_periods(core)
        or repro.inputs != payload.inputs
        or repro.config_sha256 != payload.config_sha256
        or repro.strategy_config.config_hash() != payload.config_sha256
        or repro.snapshot_sha256 != payload.snapshot_sha256
        or repro.calendar_sha256 != payload.calendar_sha256
        or repro.core_manifest_sha256 != core_digest
        or repro.engine_version != payload.engine_version
        or repro.reporting_engine_version != manifest.reporting_engine_version
        or repro.provider != pinned.manifest.source.provider
        or repro.source_mode != payload.source_mode
        or repro.warnings != summary.warnings
    ):
        raise ValueError("Report lineage differs from pinned inputs")
    series = read_artifact(stage / "report", manifest, "series").splitlines()
    if len(series) != len(core.points):
        raise ValueError("Report series is incomplete")
    for raw, point in zip(series, core.points, strict=True):
        sample = ExperimentCurvePointV1.model_validate_json(raw)
        if (
            sample.session_date != point.session_date
            or sample.phase != point.phase
            or sample.portfolio_nav_usd != point.nav_usd
            or sample.cash_usd != point.state.cash_usd
            or sample.positions != point.state.positions
        ):
            raise ValueError("Report series differs from core evidence")
    trades = read_artifact(stage / "report", manifest, "trades").splitlines()
    if len(trades) != len(core.executions):
        raise ValueError("Report trades are incomplete")
    for raw, execution in zip(trades, core.executions, strict=True):
        trade = ExperimentTradeV1.model_validate_json(raw)
        if trade.model_dump(exclude={"id", "currency"}) != execution.model_dump():
            raise ValueError("Report trade differs from core evidence")
    core_store, report_store = root / "experiments", root / "experiment-reports"
    for store in (core_store, report_store):
        store.mkdir(mode=0o700, parents=True, exist_ok=True)
    with Session(queue.engine) as session, session.begin():
        # Fixed sorted lock order also serializes identical cores with distinct reports.
        for identity in sorted({core_digest, digest}):
            key = int.from_bytes(bytes.fromhex(identity)[:8], "big", signed=True)
            if not session.execute(
                text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": key}
            ).scalar_one():
                raise PublicationFenceError("Report publication is busy")
        job, now = queue.owned(session, lease)
        if (
            job is None
            or job.kind != "backtest"
            or job.status != "running"
            or job.attempt_deadline is None
            or job.attempt_deadline <= now
        ):
            raise PublicationFenceError("Report lease is no longer valid")
        row = session.get(Experiment, payload.experiment_id)
        if (
            row is None
            or row.job_id != job.id
            or row.payload != payload.model_dump(mode="json")
            or job.payload != row.payload
            or row.snapshot_id != payload.inputs.snapshot_id
            or row.strategy_version_id != payload.inputs.strategy_version_id
        ):
            raise ValueError("Report admission linkage differs from immutable inputs")
        publish_core(stage / "core", core_store, core_digest)
        publish_report(stage / "report", report_store, digest)
        job, now = queue.owned(session, lease)
        if (
            job is None
            or job.status != "running"
            or job.attempt_deadline is None
            or job.attempt_deadline <= now
        ):
            raise PublicationFenceError("Report lease expired during publication")
        session.add(
            ExperimentCore(
                experiment_id=row.id,
                manifest_sha256=core_digest,
                attempt_token=lease.token,
                completed_at=now,
            )
        )
        session.add(
            ExperimentReport(
                experiment_id=row.id,
                manifest_sha256=digest,
                attempt_token=lease.token,
                completed_at=now,
            )
        )
        job.result = JobResult(
            kind="resource", resource_id=row.id, message="Immutable experiment report sealed."
        ).model_dump(mode="json")
        job.status, job.progress = "completed", 100
        queue.finish_attempt(session, job, now, "completed")
