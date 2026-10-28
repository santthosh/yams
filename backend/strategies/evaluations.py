"""Atomic diagnostic admission, immutable sealing and read integrity."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from backend.domain.common import ErrorCode, JobResult
from backend.domain.evaluation import (
    EvaluationCandidateV1,
    EvaluationReproducibilityV1,
    StrategyEvaluationAccepted,
    StrategyEvaluationPayload,
    StrategyEvaluationRequest,
    StrategyEvaluationResultV1,
    StrategyEvaluationV1,
)
from backend.domain.strategy import StrategyConfigV1
from backend.jobs.queue import Lease, Queue, database_now
from backend.jobs.registry import validate_workload
from backend.market_data.catalog import verified_snapshot
from backend.market_data.models import Calendar
from backend.market_data.snapshots import PublicationFenceError
from backend.persistence.models.evaluation import StrategyEvaluation, StrategyEvaluationResult
from backend.persistence.models.job import Job
from backend.persistence.models.snapshot import DatasetSnapshot
from backend.persistence.models.strategy import StrategyVersion
from backend.portfolio.allocation import AllocatedMomentum
from backend.portfolio.execution import calendar_digest
from backend.portfolio.risk import assess_targets
from backend.strategies.build import engine_fingerprint
from backend.strategies.registry import version_view

MAX_RESULT_BYTES = 8 * 1024 * 1024


def result_from_engine(
    payload: StrategyEvaluationPayload, measured: AllocatedMomentum
) -> StrategyEvaluationResultV1:
    """Transport composition only; the caller must supply an approved explicit cutoff."""
    momentum, allocation = measured.momentum, measured.allocation
    return StrategyEvaluationResultV1(
        as_of_session=momentum.session_date,
        decision_cutoff_utc=momentum.cutoff,
        mode=momentum.mode,
        warnings=momentum.warnings,
        candidates=tuple(
            EvaluationCandidateV1.model_validate(row.model_dump()) for row in momentum.candidates
        ),
        selected_ids=allocation.selected_ids,
        target_weights=allocation.targets,
        cash_target_weight=allocation.cash_weight,
        constraint_evidence=allocation.risk,
        allocation_reasons=allocation.reasons,
        allocation_exclusions=allocation.exclusions,
        data_diagnostics=momentum.data_diagnostics,
        reproducibility=EvaluationReproducibilityV1(
            strategy_version_id=payload.inputs.strategy_version_id,
            snapshot_id=momentum.snapshot_id,
            config_sha256=momentum.config_sha256,
            snapshot_sha256=momentum.manifest_sha256,
            calendar_sha256=momentum.calendar_sha256,
            engine_version=momentum.engine_version,
        ),
    )


class EvaluationAdmissionError(ValueError):
    def __init__(self, code: ErrorCode, message: str):
        self.code = code
        self.message = message
        super().__init__(code)


def admit_evaluation(
    engine: Engine, root: Path, request: StrategyEvaluationRequest
) -> StrategyEvaluationAccepted:
    queue = Queue(engine)
    with Session(engine) as session, session.begin():
        version = session.get(StrategyVersion, request.strategy_version_id)
        snapshot = session.get(DatasetSnapshot, request.snapshot_id)
        if version is None or snapshot is None:
            raise EvaluationAdmissionError(
                "NOT_FOUND", "Strategy version or snapshot was not found."
            )
        published = version_view(version)
        pinned = verified_snapshot(snapshot, root)
        manifest = pinned.manifest
        if manifest.quality == "blocked":
            raise EvaluationAdmissionError(
                "STALE_DATA", "The selected snapshot is blocked for evaluation."
            )
        calendar = Calendar.model_validate_json(pinned.artifacts[manifest.calendar.artifact_path])
        scheduled = next(
            (row for row in calendar.sessions if row.session_date == request.as_of_session), None
        )
        coverage = manifest.coverage
        if (
            scheduled is None
            or coverage.first_session is None
            or coverage.last_session is None
            or not coverage.first_session <= request.as_of_session <= coverage.last_session
        ):
            raise EvaluationAdmissionError(
                "INSUFFICIENT_MARKET_DATA", "Session is not covered by this snapshot."
            )
        if manifest.mode == "research_market_data" and scheduled.close_at > datetime.now(UTC):
            raise EvaluationAdmissionError(
                "VALIDATION_ERROR", "A future market session cannot be evaluated."
            )
        if (
            coverage.latest_completed_session is None
            or request.as_of_session > coverage.latest_completed_session
        ):
            raise EvaluationAdmissionError(
                "STALE_DATA", "The snapshot lacks a completed session at that date."
            )
        try:
            validate_workload(assets=len(coverage.asset_ids), sessions=len(calendar.sessions))
            if any(
                item.role == "bars" and (item.row_count or 0) > 2520000
                for item in manifest.artifacts
            ):
                raise ValueError("WORKLOAD_LIMIT")
        except ValueError:
            raise EvaluationAdmissionError(
                "WORKLOAD_LIMIT", "Snapshot exceeds diagnostic workload limits."
            ) from None
        identity = uuid4()
        build = engine_fingerprint()
        payload = StrategyEvaluationPayload(
            evaluation_id=identity,
            inputs=request,
            source_mode=manifest.mode,
            snapshot_sha256=snapshot.manifest_hash,
            config_sha256=published.config_sha256,
            calendar_sha256=calendar_digest(calendar),
            engine_version=build,
            config_canonical_json=published.config.canonical_bytes().decode(),
        )
        # The resource and job must commit together: a runnable job cannot be left
        # without its immutable input row after a lost HTTP response or crash.
        job_id = queue._enqueue(
            session, "evaluate_strategy", payload.model_dump(mode="json"), identity
        )
        session.add(
            StrategyEvaluation(
                id=identity,
                job_id=job_id,
                strategy_version_id=request.strategy_version_id,
                snapshot_id=request.snapshot_id,
                as_of_session=request.as_of_session,
                source_mode=manifest.mode,
                config_sha256=published.config_sha256,
                snapshot_sha256=snapshot.manifest_hash,
                calendar_sha256=payload.calendar_sha256,
                engine_version=build,
                created_at=database_now(session),
            )
        )
        return StrategyEvaluationAccepted(job_id=job_id, evaluation_id=identity)


def seal_evaluation(queue: Queue, lease: Lease, value: str) -> None:
    if len(value.encode()) > MAX_RESULT_BYTES:
        raise ValueError("Diagnostic result exceeds transport limit")
    result = StrategyEvaluationResultV1.model_validate_json(value)
    payload = StrategyEvaluationPayload.model_validate(lease.payload)
    config = StrategyConfigV1.from_json(payload.config_canonical_json)
    if config.config_hash() != payload.config_sha256:
        raise ValueError("Diagnostic payload config hash differs from immutable rules")
    risk = assess_targets(result.target_weights, result.cash_target_weight, config.portfolio)
    if not risk.compliant or risk != result.constraint_evidence:
        raise ValueError("Diagnostic constraints fail the pinned strategy policy")
    if lease.kind != "evaluate_strategy":
        raise ValueError("Diagnostic publication requires its owning job kind")
    with Session(queue.engine) as session, session.begin():
        job, now = queue.owned(session, lease)
        if (
            job is None
            or job.status != "running"
            or job.attempt_deadline is None
            or job.attempt_deadline <= now
        ):
            raise PublicationFenceError("Diagnostic lease is no longer valid")
        row = session.get(StrategyEvaluation, payload.evaluation_id)
        repro = result.reproducibility
        if (
            row is None
            or row.job_id != job.id
            or row.strategy_version_id != payload.inputs.strategy_version_id
            or row.snapshot_id != payload.inputs.snapshot_id
            or row.as_of_session != payload.inputs.as_of_session
            or row.source_mode != payload.source_mode
            or row.engine_version != payload.engine_version
            or row.config_sha256 != payload.config_sha256
            or row.snapshot_sha256 != payload.snapshot_sha256
            or row.calendar_sha256 != payload.calendar_sha256
            or result.as_of_session != row.as_of_session
            or result.mode != row.source_mode
            or repro.strategy_version_id != row.strategy_version_id
            or repro.snapshot_id != row.snapshot_id
            or repro.config_sha256 != row.config_sha256
            or repro.snapshot_sha256 != row.snapshot_sha256
            or repro.calendar_sha256 != row.calendar_sha256
            or repro.engine_version != row.engine_version
        ):
            raise ValueError("Diagnostic output lineage differs from immutable inputs")
        session.add(
            StrategyEvaluationResult(
                evaluation_id=row.id,
                payload=result.model_dump(mode="json"),
                sha256=result.result_hash(),
                completed_at=now,
                attempt_token=lease.token,
            )
        )
        job.result = JobResult(
            kind="resource", resource_id=row.id, message="Immutable strategy diagnostics completed."
        ).model_dump(mode="json")
        job.status, job.progress = "completed", 100
        queue.finish_attempt(session, job, now, "completed")


def read_evaluation(engine: Engine, identity: UUID) -> StrategyEvaluationV1 | None:
    with Session(engine) as session:
        row = session.get(StrategyEvaluation, identity)
        if row is None:
            return None
        job = session.get(Job, row.job_id)
        if job is None or job.kind != "evaluate_strategy":
            raise ValueError("Diagnostic job linkage is unavailable")
        status = Queue.view(job)
        if status.status == "completed" and (
            status.result is None
            or status.result.kind != "resource"
            or status.result.resource_id != row.id
        ):
            raise ValueError("Diagnostic job resource differs from sealed evaluation")
        payload = StrategyEvaluationPayload.model_validate(job.payload)
        snapshot = session.get(DatasetSnapshot, row.snapshot_id)
        if snapshot is None:
            raise ValueError("Diagnostic snapshot metadata is unavailable")
        sealed = session.get(StrategyEvaluationResult, identity)
        result = (
            StrategyEvaluationResultV1.model_validate(sealed.payload)
            if sealed is not None
            else None
        )
        return StrategyEvaluationV1.model_validate(
            dict(
                id=row.id,
                job_id=row.job_id,
                status=status.status,
                inputs=StrategyEvaluationRequest(
                    strategy_version_id=row.strategy_version_id,
                    snapshot_id=row.snapshot_id,
                    as_of_session=row.as_of_session,
                ),
                mode=row.source_mode,
                provider=snapshot.manifest["source"]["provider"],
                config_sha256=row.config_sha256,
                snapshot_sha256=row.snapshot_sha256,
                engine_version=row.engine_version,
                created_at=row.created_at,
                strategy_config=StrategyConfigV1.from_json(payload.config_canonical_json),
                result=result,
                result_sha256=sealed.sha256 if sealed is not None else None,
                error=status.error,
            )
        )
