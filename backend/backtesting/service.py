"""Atomic internal core admission and lease-fenced immutable publication."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from backend.backtesting.artifacts import publish_core, read_core
from backend.backtesting.contracts import BacktestCorePayload
from backend.backtesting.errors import BacktestFailure
from backend.backtesting.runner import BacktestCoreResult, prepare_backtest
from backend.backtesting.schedule import build_schedule
from backend.domain.common import JobResult, JobV1
from backend.domain.experiment import ExperimentRequest
from backend.domain.strategy import StrategyConfigV1
from backend.domain.types import canonical_json, load_json
from backend.jobs.queue import Lease, Queue, database_now
from backend.market_data.catalog import verified_snapshot
from backend.market_data.models import Calendar
from backend.market_data.snapshots import PublicationFenceError
from backend.persistence.models.experiment import Experiment, ExperimentCore
from backend.persistence.models.job import Job
from backend.persistence.models.snapshot import DatasetSnapshot
from backend.persistence.models.strategy import StrategyVersion
from backend.portfolio.execution import (
    DEFAULT_EXECUTION_POLICY,
    ExecutionContext,
    calendar_digest,
    next_eligible_session,
)
from backend.portfolio.risk import assess_targets
from backend.strategies.build import engine_fingerprint
from backend.strategies.clock import decision_cutoff
from backend.strategies.registry import version_view


@dataclass(frozen=True)
class CoreAccepted:
    experiment_id: UUID
    job_id: UUID


@dataclass(frozen=True)
class CoreRun:
    id: UUID
    job: JobV1
    payload: BacktestCorePayload
    result: BacktestCoreResult | None
    manifest_sha256: str | None


def admit_core(engine: Engine, root: Path, request: ExperimentRequest) -> CoreAccepted:
    """Compatibility entry point for independently sealed internal cores."""
    return admit_experiment(engine, root, request, kind="backtest_core")


def admit_experiment(
    engine: Engine,
    root: Path,
    request: ExperimentRequest,
    *,
    kind: Literal["backtest_core", "backtest"] = "backtest",
) -> CoreAccepted:
    """Pin all immutable inputs and queue the owning job in one transaction."""
    queue = Queue(engine)
    with Session(engine) as session, session.begin():
        version = session.get(StrategyVersion, request.strategy_version_id)
        snapshot = session.get(DatasetSnapshot, request.snapshot_id)
        if version is None or snapshot is None:
            raise ValueError("NOT_FOUND")
        published = version_view(version)
        pinned = verified_snapshot(snapshot, root)
        try:
            calendar, schedule = prepare_backtest(pinned, request)
        except BacktestFailure:
            raise
        except ValueError as error:
            if str(error) == "WORKLOAD_LIMIT":
                raise
            raise ValueError("INVALID_EXPERIMENT_WINDOW") from None
        if pinned.manifest.mode == "research_market_data" and decision_cutoff(
            calendar, schedule.sessions[-1].session_date
        ) > datetime.now(UTC):
            raise ValueError("DECISION_CUTOFF_NOT_ELAPSED")
        identity = uuid4()
        payload = BacktestCorePayload(
            experiment_id=identity,
            inputs_canonical_json=canonical_json(load_json(request.model_dump_json())).decode(),
            source_mode=pinned.manifest.mode,
            config_sha256=published.config_sha256,
            snapshot_sha256=snapshot.manifest_hash,
            calendar_sha256=calendar_digest(calendar),
            engine_version=engine_fingerprint(),
            config_canonical_json=published.config.canonical_bytes().decode(),
        )
        job_id = queue._enqueue(session, kind, payload.model_dump(mode="json"), identity)
        session.add(
            Experiment(
                id=identity,
                job_id=job_id,
                strategy_version_id=request.strategy_version_id,
                snapshot_id=request.snapshot_id,
                payload=payload.model_dump(mode="json"),
                created_at=database_now(session),
            )
        )
        return CoreAccepted(identity, job_id)


def validate_result(
    payload: BacktestCorePayload, result: BacktestCoreResult, calendar: Calendar
) -> None:
    schedule = build_schedule(payload.inputs, calendar)
    if (
        result.inputs != payload.inputs
        or result.source_mode != payload.source_mode
        or result.config_sha256 != payload.config_sha256
        or result.snapshot_sha256 != payload.snapshot_sha256
        or result.calendar_sha256 != payload.calendar_sha256
        or result.engine_version != payload.engine_version
        or calendar_digest(calendar) != payload.calendar_sha256
        or tuple(row.session_date for row in result.points)
        != tuple(row.session_date for row in schedule.sessions)
        or result.holdout_start_session != schedule.holdout_start_session
        or tuple(row.plan.context.decision_session for row in result.decisions)
        != schedule.decision_sessions
        or any(
            row.phase != ("development" if index < schedule.development_sessions else "holdout")
            for index, row in enumerate(result.points)
        )
        or Decimal(result.points[0].nav_usd) != Decimal(payload.inputs.initial_capital_usd)
        or Decimal(result.points[0].state.cash_usd) != Decimal(payload.inputs.initial_capital_usd)
        or result.points[0].state.positions
        or any(not row.terminal for row in result.executions)
    ):
        raise ValueError("Core result differs from pinned complete input window")
    rules = StrategyConfigV1.from_json(payload.config_canonical_json)
    expected_executions = {}
    for decision in result.decisions:
        measured, plan = decision.measured, decision.plan
        cutoff = decision_cutoff(calendar, plan.context.decision_session)
        expected_context = ExecutionContext(
            snapshot_id=payload.inputs.snapshot_id,
            snapshot_sha256=payload.snapshot_sha256,
            calendar_sha256=payload.calendar_sha256,
            mode=payload.source_mode,
            engine_version=payload.engine_version,
            execution_mode="historical_replay",
            decision_session=plan.context.decision_session,
            decision_cutoff=cutoff,
            approved_at=cutoff,
        )
        evidence = measured.momentum
        risk = assess_targets(
            measured.allocation.targets, measured.allocation.cash_weight, rules.portfolio
        )
        if (
            plan.context != expected_context
            or plan.policy != DEFAULT_EXECUTION_POLICY
            or plan.status != "ready"
            or evidence.config_sha256 != payload.config_sha256
            or evidence.snapshot_id != payload.inputs.snapshot_id
            or evidence.manifest_sha256 != payload.snapshot_sha256
            or evidence.calendar_sha256 != payload.calendar_sha256
            or evidence.mode != payload.source_mode
            or evidence.engine_version != payload.engine_version
            or evidence.session_date != plan.context.decision_session
            or evidence.cutoff != cutoff
            or not risk.compliant
            or risk != measured.allocation.risk
        ):
            raise ValueError("Core decision lineage differs from pinned input")
        for order in plan.orders:
            key = (plan.context.decision_session, order.key)
            if key in expected_executions:
                raise ValueError("Duplicate core order identity")
            expected_executions[key] = (plan, order)
    if len(result.executions) != len(expected_executions):
        raise ValueError("Core execution trace is incomplete")
    for execution in result.executions:
        expected = expected_executions.pop(
            (execution.context.decision_session, execution.order.key), None
        )
        eligible = next_eligible_session(
            calendar, execution.context.decision_cutoff, execution.context.approved_at
        )
        if (
            expected is None
            or execution.context != expected[0].context
            or execution.order != expected[1]
            or execution.policy != DEFAULT_EXECUTION_POLICY
            or execution.eligible_session != eligible
        ):
            raise ValueError("Core execution lineage differs from approved intent")
        fill = execution.fill
        if fill is not None and (
            fill.execution_session != eligible.session_date
            or fill.execution_at != eligible.open_at
            or fill.execution_at <= execution.context.approved_at
            or fill.evidence_available_at > fill.proposed_at
            or fill.proposed_at != decision_cutoff(calendar, eligible.session_date)
        ):
            raise ValueError("Core fill chronology differs from approved intent")


def seal_core(queue: Queue, lease: Lease, root: Path, stage: Path, digest: str) -> None:
    payload = BacktestCorePayload.model_validate(lease.payload)
    if lease.kind != "backtest_core":
        raise ValueError("Core publication requires its owning job kind")
    result = read_core(stage, digest)
    # Always validate against the registered snapshot, not a child-supplied calendar.
    with Session(queue.engine) as session:
        snapshot = session.get(DatasetSnapshot, payload.inputs.snapshot_id)
        if snapshot is None:
            raise ValueError("Core snapshot is unavailable")
        pinned = verified_snapshot(snapshot, root)
    calendar = Calendar.model_validate_json(
        pinned.artifacts[pinned.manifest.calendar.artifact_path]
    )
    validate_result(payload, result, calendar)
    store = root / "experiments"
    store.mkdir(mode=0o700, parents=True, exist_ok=True)
    key = int.from_bytes(bytes.fromhex(digest)[:8], "big", signed=True)
    with Session(queue.engine) as session, session.begin():
        if not session.execute(
            text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": key}
        ).scalar_one():
            raise PublicationFenceError("Core publication is busy")
        job, now = queue.owned(session, lease)
        if (
            job is None
            or job.kind != "backtest_core"
            or job.status != "running"
            or job.attempt_deadline is None
            or job.attempt_deadline <= now
        ):
            raise PublicationFenceError("Core lease is no longer valid")
        row = session.get(Experiment, payload.experiment_id)
        if (
            row is None
            or row.job_id != job.id
            or row.payload != payload.model_dump(mode="json")
            or row.strategy_version_id != payload.inputs.strategy_version_id
            or row.snapshot_id != payload.inputs.snapshot_id
            or job.payload != row.payload
        ):
            raise ValueError("Core admission linkage differs from immutable payload")
        publish_core(stage, store, digest)
        job, now = queue.owned(session, lease)
        if (
            job is None
            or job.status != "running"
            or job.attempt_deadline is None
            or job.attempt_deadline <= now
        ):
            raise PublicationFenceError("Core lease expired during publication")
        session.add(
            ExperimentCore(
                experiment_id=row.id,
                manifest_sha256=digest,
                attempt_token=lease.token,
                completed_at=now,
            )
        )
        job.result = JobResult(
            kind="resource",
            resource_id=row.id,
            message="Immutable backtest core sealed; report composition is separate.",
        ).model_dump(mode="json")
        job.status, job.progress = "completed", 100
        queue.finish_attempt(session, job, now, "completed")


def read_core_run(engine: Engine, root: Path, identity: UUID) -> CoreRun | None:
    with Session(engine) as session:
        row = session.get(Experiment, identity)
        if row is None:
            return None
        # A share lock serializes the status/core read with the completing
        # transaction; READ COMMITTED queries must not observe two different states.
        job = session.execute(
            select(Job).where(Job.id == row.job_id).with_for_update(read=True)
        ).scalar_one_or_none()
        core = session.get(ExperimentCore, identity)
        if job is None or job.kind != "backtest_core" or job.payload != row.payload:
            raise ValueError("Core job linkage is unavailable")
        payload = BacktestCorePayload.model_validate(row.payload)
        view = Queue.view(job)
        if (view.status == "completed") != (core is not None):
            raise ValueError("Core completion differs from sealed evidence")
        result = None
        digest = None
        if core is not None:
            if view.result is None or view.result.resource_id != row.id:
                raise ValueError("Core resource identity differs from completion")
            digest = core.manifest_sha256
            result = read_core(root / "experiments" / digest, digest)
            snapshot = session.get(DatasetSnapshot, payload.inputs.snapshot_id)
            if snapshot is None:
                raise ValueError("Core snapshot is unavailable")
            pinned = verified_snapshot(snapshot, root)
            calendar = Calendar.model_validate_json(
                pinned.artifacts[pinned.manifest.calendar.artifact_path]
            )
            validate_result(payload, result, calendar)
        return CoreRun(row.id, view, payload, result, digest)
