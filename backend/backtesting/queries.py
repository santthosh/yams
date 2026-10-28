"""Read-only public projections over immutable sealed reports, with bounded pages."""

import base64
import hashlib
import json
from datetime import datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import Engine, and_, or_, select
from sqlalchemy.orm import Session

from backend.backtesting.contracts import BacktestCorePayload
from backend.backtesting.report_artifacts import (
    ReportManifest,
    Role,
    read_artifact,
    read_manifest,
)
from backend.domain.common import PageRequest
from backend.domain.experiment_api import (
    ExperimentCurvePointV1,
    ExperimentDetailV1,
    ExperimentPageV1,
    ExperimentReportSummaryV1,
    ExperimentSeriesPageV1,
    ExperimentSummaryV1,
    ExperimentTradesPageV1,
    ExperimentTradeV1,
)
from backend.domain.strategy import StrategyConfigV1
from backend.domain.types import SessionDate, canonical_json
from backend.jobs.queue import Queue
from backend.persistence.models.experiment import Experiment, ExperimentCore, ExperimentReport
from backend.persistence.models.job import Job
from backend.persistence.models.snapshot import DatasetSnapshot


class ExperimentStateConflict(ValueError):
    pass


class ExperimentQueryError(ValueError):
    pass


def encode_cursor(scope: str, position: str) -> str:
    return (
        base64.urlsafe_b64encode(json.dumps([scope, position], separators=(",", ":")).encode())
        .decode()
        .rstrip("=")
    )


def decode_cursor(cursor: str, scope: str) -> str:
    try:
        decoded = base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
        value = json.loads(decoded)
        if (
            not isinstance(value, list)
            or len(value) != 2
            or value[0] != scope
            or not isinstance(value[1], str)
        ):
            raise ValueError
        return value[1]
    except (ValueError, UnicodeError):
        raise ExperimentQueryError("Cursor is invalid for this query") from None


def _summary(row: Experiment, job: Job) -> ExperimentSummaryV1:
    payload = BacktestCorePayload.model_validate(row.payload)
    view = Queue.view(job)
    if job.payload != row.payload or payload.experiment_id != row.id:
        raise ValueError("Experiment job linkage is unavailable")
    return ExperimentSummaryV1(
        id=row.id,
        job_id=row.job_id,
        status=view.status,
        inputs=payload.inputs,
        config_sha256=payload.config_sha256,
        snapshot_sha256=payload.snapshot_sha256,
        data_status=payload.source_mode,
        created_at=row.created_at,
        engine_version=payload.engine_version,
        error=view.error,
    )


def history(engine: Engine, page: PageRequest) -> ExperimentPageV1:
    with Session(engine) as session:
        statement = (
            select(Experiment, Job)
            .join(Job, Job.id == Experiment.job_id)
            .where(Job.kind == "backtest")
        )
        if page.cursor:
            try:
                date, identity = decode_cursor(page.cursor, "experiment-history-v1").split("|", 1)
                timestamp, identifier = datetime.fromisoformat(date), UUID(identity)
                if timestamp.tzinfo is None:
                    raise ValueError
            except ValueError:
                raise ExperimentQueryError("Invalid experiment history cursor") from None
            statement = statement.where(
                or_(
                    Experiment.created_at < timestamp,
                    and_(Experiment.created_at == timestamp, Experiment.id < identifier),
                )
            )
        rows = session.execute(
            statement.order_by(Experiment.created_at.desc(), Experiment.id.desc()).limit(
                page.limit + 1
            )
        ).all()
        items = tuple(_summary(row, job) for row, job in rows[: page.limit])
        cursor = None
        if len(rows) > page.limit:
            last = rows[page.limit - 1][0]
            cursor = encode_cursor(
                "experiment-history-v1", f"{last.created_at.isoformat()}|{last.id}"
            )
        return ExperimentPageV1(items=items, next_cursor=cursor)


def _load(
    session: Session,
    root: Path,
    identity: UUID,
) -> tuple[ExperimentDetailV1, ReportManifest | None, Path | None] | None:
    row = session.get(Experiment, identity)
    if row is None:
        return None
    job = session.execute(
        select(Job).where(Job.id == row.job_id).with_for_update(read=True)
    ).scalar_one_or_none()
    if job is None:
        raise ValueError("Experiment job is unavailable")
    if job.kind != "backtest":
        return None  # Internal core resources are not public completed experiments.
    base = _summary(row, job)
    payload = BacktestCorePayload.model_validate(row.payload)
    report = session.get(ExperimentReport, identity)
    core = session.get(ExperimentCore, identity)
    if (base.status == "completed") != (report is not None and core is not None):
        raise ValueError("Experiment status differs from sealed evidence")
    if base.status != "completed" and (report is not None or core is not None):
        raise ValueError("Incomplete experiment has sealed output")
    snapshot = session.get(DatasetSnapshot, payload.inputs.snapshot_id)
    if snapshot is None:
        raise ValueError("Experiment snapshot is unavailable")
    # Provider is pinned in the immutable snapshot registration, not accepted from clients.
    from backend.domain.market import SnapshotManifestV1

    provider = SnapshotManifestV1.model_validate(snapshot.manifest).source.provider
    manifest = None
    path = None
    summary = None
    if report is not None and core is not None:
        path = root / "experiment-reports" / report.manifest_sha256
        manifest = read_manifest(path, report.manifest_sha256)
        summary = ExperimentReportSummaryV1.model_validate_json(
            read_artifact(path, manifest, "summary")
        )
        if (
            manifest.core_manifest_sha256 != core.manifest_sha256
            or summary.core_manifest_sha256 != core.manifest_sha256
            or manifest.snapshot_sha256 != payload.snapshot_sha256
            or manifest.config_sha256 != payload.config_sha256
            or manifest.calendar_sha256 != payload.calendar_sha256
            or manifest.engine_version != payload.engine_version
        ):
            raise ValueError("Experiment report lineage is unavailable")
    detail = ExperimentDetailV1(
        **base.model_dump(),
        inputs_canonical_json=payload.inputs_canonical_json,
        provider=provider,
        strategy_config=StrategyConfigV1.from_json(payload.config_canonical_json),
        metrics=summary.portfolio.total.metrics if summary else None,
        curve_artifact=manifest.artifact("series").reference if manifest else None,
        trade_artifact=manifest.artifact("trades").reference if manifest else None,
        reproducibility_manifest=manifest.artifact("reproducibility").reference
        if manifest
        else None,
        warnings=summary.warnings if summary else (),
        report=summary,
    )
    return detail, manifest, path


def detail(engine: Engine, root: Path, identity: UUID) -> ExperimentDetailV1 | None:
    with Session(engine) as session:
        result = _load(session, root, identity)
        return result[0] if result is not None else None


def artifact_page(
    engine: Engine,
    root: Path,
    identity: UUID,
    role: Role,
    page: PageRequest,
    start_session: SessionDate | None = None,
    end_session_exclusive: SessionDate | None = None,
) -> ExperimentSeriesPageV1 | ExperimentTradesPageV1 | None:
    if role not in {"series", "trades"}:
        raise ValueError("Unsupported public artifact role")
    with Session(engine) as session:
        loaded = _load(session, root, identity)
        if loaded is None:
            return None
        run, manifest, path = loaded
        if manifest is None or path is None:
            raise ExperimentStateConflict("Experiment has no completed report")
        start = start_session or run.inputs.start_session
        end = end_session_exclusive or run.inputs.end_session_exclusive
        if (
            start >= end
            or start < run.inputs.start_session
            or end > run.inputs.end_session_exclusive
        ):
            raise ExperimentQueryError(
                "Window must be inside the original half-open experiment window"
            )
        scope = hashlib.sha256(
            canonical_json(
                {
                    "experiment": str(identity),
                    "artifact": manifest.artifact(role).reference.sha256,
                    "role": role,
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "limit": page.limit,
                }
            )
        ).hexdigest()
        offset = 0
        if page.cursor:
            try:
                position = decode_cursor(page.cursor, scope)
                if not position.isascii() or not position.isdecimal() or len(position) > 8:
                    raise ValueError
                offset = int(position)
            except ValueError:
                raise ExperimentQueryError("Invalid experiment page cursor") from None
        content = read_artifact(path, manifest, role)
        # Bytes are capped at64MiB; only the requested <=100 models are retained.
        selected: list[ExperimentCurvePointV1 | ExperimentTradeV1] = []
        seen = 0
        import io

        for line in io.BytesIO(content):
            value = (
                ExperimentCurvePointV1.model_validate_json(line)
                if role == "series"
                else ExperimentTradeV1.model_validate_json(line)
            )
            date = (
                value.session_date
                if isinstance(value, ExperimentCurvePointV1)
                else value.eligible_session.session_date
            )
            if start <= date < end:
                if offset <= seen and len(selected) <= page.limit:
                    selected.append(value)
                seen += 1
        if offset > seen or (offset == seen and offset != 0):
            raise ExperimentQueryError("Experiment cursor is outside this result")
        next_cursor = (
            encode_cursor(scope, str(offset + page.limit)) if len(selected) > page.limit else None
        )
        if role == "series":
            return ExperimentSeriesPageV1.model_validate(
                dict(items=selected[: page.limit], next_cursor=next_cursor)
            )
        return ExperimentTradesPageV1.model_validate(
            dict(items=selected[: page.limit], next_cursor=next_cursor)
        )
