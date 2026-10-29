"""Atomic frozen-state admission and lease-fenced immutable recommendation publication."""

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4, uuid5

from sqlalchemy import Engine, and_, exists, or_, select
from sqlalchemy.orm import Session

from backend.domain.common import ErrorCode, JobResult
from backend.domain.recommendation_api import RecommendationAccepted, RecommendationRequest
from backend.domain.types import canonical_json, load_json
from backend.forecasting.contracts import ForecastPayload
from backend.forecasting.service import _enqueue_frozen_forecast
from backend.jobs.queue import IdempotencyConflict, Lease, Queue, database_now
from backend.jobs.registry import validate_workload
from backend.jobs.review_admission import (
    link_scheduled_admission,
    review_schema_available,
    scheduled_admission,
)
from backend.market_data.catalog import verified_snapshot
from backend.market_data.models import Calendar
from backend.market_data.snapshots import PublicationFenceError
from backend.persistence.models.job import Job
from backend.persistence.models.ledger import LedgerEvent, RecommendationReference
from backend.persistence.models.recommendation import RecommendationPublication, RecommendationRun
from backend.persistence.models.review import (
    PortfolioReviewOccurrence,
    PortfolioReviewTarget,
    RecommendationRequestAlias,
)
from backend.persistence.models.snapshot import CurrentSnapshot, DatasetSnapshot
from backend.portfolio.accounts import account_record
from backend.portfolio.batches import ExecutionIntentV1
from backend.portfolio.execution import calendar_digest
from backend.portfolio.ledger import _locked, digest
from backend.portfolio.paper_clock import replay_floor
from backend.portfolio.recommendation_contracts import (
    MAX_RECOMMENDATION_BYTES,
    RecommendationComputed,
    RecommendationPayload,
)
from backend.portfolio.recommendation_engine import render_recommendation
from backend.strategies.build import engine_fingerprint
from backend.strategies.clock import decision_cutoff


class RecommendationAdmissionError(ValueError):
    def __init__(self, code: ErrorCode, message: str):
        self.code, self.message = code, message
        super().__init__(code)


def _retry(
    session: Session,
    identity: UUID,
    owner: UUID,
    request: RecommendationRequest,
    *,
    key: UUID | None = None,
) -> RecommendationAccepted | None:
    if key is not None and review_schema_available(session):
        alias = session.get(RecommendationRequestAlias, (owner, key))
        if alias is not None:
            if alias.inputs_canonical_json != request.canonical_bytes().decode():
                raise IdempotencyConflict("Recommendation key refers to different request inputs")
            original_run = session.get(RecommendationRun, alias.recommendation_id)
            if original_run is None or original_run.portfolio_id != owner:
                raise ValueError("Original recommendation key binding is unavailable")
            return RecommendationAccepted(
                recommendation_id=original_run.id, job_id=original_run.job_id
            )
    row = session.get(RecommendationRun, identity)
    if row is None:
        return None
    original = RecommendationPayload.model_validate(row.payload)
    if (
        row.portfolio_id != owner
        or original.portfolio_id != owner
        or original.inputs.canonical_bytes() != request.canonical_bytes()
    ):
        raise IdempotencyConflict("Recommendation key refers to different request inputs")
    return RecommendationAccepted(recommendation_id=row.id, job_id=row.job_id)


def admit_recommendation(
    engine: Engine,
    root: Path,
    owner: UUID,
    request: RecommendationRequest,
    *,
    idempotency_key: UUID | None = None,
    schedule_occurrence_id: UUID | None = None,
) -> RecommendationAccepted:
    identity = (
        uuid5(owner, "recommendation:" + str(idempotency_key)) if idempotency_key else uuid4()
    )
    with Session(engine) as session:
        prior = _retry(session, identity, owner, request, key=idempotency_key)
        if prior is not None:
            return prior
    record = account_record(engine, owner)
    if record.status != "active":
        raise RecommendationAdmissionError("STATE_CONFLICT", "Portfolio is not active.")
    if record.mode != "synthetic_fixture":
        raise RecommendationAdmissionError(
            "INSUFFICIENT_MARKET_DATA", "This source has no verified portfolio accounting support."
        )
    if request.clock_mode != "synthetic_replay":
        raise RecommendationAdmissionError(
            "VALIDATION_ERROR", "Synthetic portfolios require explicit synthetic replay mode."
        )
    selected = request.snapshot_id or record.valuation_snapshot_id
    with Session(engine) as session:
        source = session.get(DatasetSnapshot, selected) if selected else None
        if source is None:
            raise RecommendationAdmissionError("NOT_FOUND", "Snapshot was not found.")
        pinned = verified_snapshot(source, root)
        manifest = pinned.manifest
        if (
            manifest.mode != record.mode
            or manifest.quality == "blocked"
            or manifest.price_basis.ohlc != "raw_as_traded"
        ):
            raise RecommendationAdmissionError(
                "STALE_DATA",
                "Snapshot mode, quality or raw price basis cannot support this portfolio.",
            )
        calendar = Calendar.model_validate_json(pinned.artifacts[manifest.calendar.artifact_path])
        try:
            cutoff = decision_cutoff(calendar, request.as_of_session)
        except ValueError:
            raise RecommendationAdmissionError(
                "INSUFFICIENT_MARKET_DATA",
                "Pinned decision session or following opening is unavailable.",
            ) from None
        coverage = manifest.coverage
        if (
            coverage.first_session is None
            or coverage.latest_completed_session is None
            or not coverage.first_session
            <= request.as_of_session
            <= coverage.latest_completed_session
        ):
            raise RecommendationAdmissionError(
                "INSUFFICIENT_MARKET_DATA",
                "Selected session is not covered by completed snapshot data.",
            )
        try:
            validate_workload(assets=len(coverage.asset_ids), sessions=len(calendar.sessions))
            if any(
                row.role == "bars" and (row.row_count or 0) > 2520000 for row in manifest.artifacts
            ):
                raise ValueError("WORKLOAD_LIMIT")
        except ValueError:
            raise RecommendationAdmissionError(
                "WORKLOAD_LIMIT", "Snapshot exceeds portfolio evaluation limits."
            ) from None
        event = session.scalar(
            select(LedgerEvent).where(
                LedgerEvent.portfolio_id == owner, LedgerEvent.sequence == record.last_sequence
            )
        )
        if event is None:
            raise RecommendationAdmissionError(
                "NOT_READY", "Posted portfolio chronology is unavailable."
            )
        observed = max(event.recorded_at, event.effective_at)
        if observed > cutoff:
            raise RecommendationAdmissionError(
                "STATE_CONFLICT",
                "Posted state follows this cutoff; choose a later decision session.",
            )
    queue = Queue(engine)
    # Immutable filesystem/build work occurs before reacquiring the portfolio lock.
    build = engine_fingerprint()
    with Session(engine) as session, session.begin():
        portfolio = _locked(session, owner)
        prior = _retry(session, identity, owner, request, key=idempotency_key)
        if prior is not None:
            return prior
        if (
            portfolio.revision != record.revision
            or portfolio.last_sequence != record.last_sequence
            or portfolio.strategy_version_id != record.strategy_version_id
            or portfolio.source_mode != record.mode
            or portfolio.status != "active"
            or portfolio.reconciliation_failed
        ):
            raise RecommendationAdmissionError(
                "STATE_CONFLICT", "Portfolio changed during admission; refresh and retry."
            )
        now = database_now(session)
        review = (
            scheduled_admission(
                session, portfolio, schedule_occurrence_id, request, manifest, calendar, now
            )
            if schedule_occurrence_id is not None
            else None
        )
        payload = RecommendationPayload(
            recommendation_id=identity,
            forecast_id=uuid5(identity, "forecast"),
            portfolio_id=owner,
            portfolio_revision=record.revision,
            last_sequence=record.last_sequence,
            state_observed_at=observed,
            state=record.state,
            inputs=request,
            strategy_version_id=record.strategy_version_id,
            config_canonical_json=record.config.canonical_bytes().decode(),
            config_sha256=record.config.config_hash(),
            snapshot_id=manifest.snapshot_id(),
            snapshot_sha256=manifest.manifest_hash(),
            calendar_sha256=calendar_digest(calendar),
            source_mode=record.mode,
            decision_cutoff_utc=cutoff,
            engine_version=build,
            requested_at=max(now, replay_floor(session, owner, cutoff)),
        )
        if len(payload.model_dump_json().encode()) > MAX_RECOMMENDATION_BYTES:
            raise RecommendationAdmissionError(
                "WORKLOAD_LIMIT", "Frozen portfolio inputs exceed the evaluation limit."
            )
        reusable = _matching_review_run(session, payload, scheduled_only=review is None)
        if reusable is not None:
            accepted = RecommendationAccepted(recommendation_id=reusable.id, job_id=reusable.job_id)
            _remember_request_alias(session, owner, idempotency_key, request, accepted, now)
            if review is not None:
                link_scheduled_admission(session, review, accepted)
            else:
                _remember_explicit_clock(session, owner, cutoff, now)
            return accepted
        job_id = queue._enqueue(
            session, "evaluate_portfolio", payload.model_dump(mode="json"), identity
        )
        session.add(
            RecommendationRun(
                id=identity,
                job_id=job_id,
                portfolio_id=owner,
                payload=payload.model_dump(mode="json"),
                created_at=now,
            )
        )
        session.flush()
        accepted = RecommendationAccepted(recommendation_id=identity, job_id=job_id)
        _remember_request_alias(session, owner, idempotency_key, request, accepted, now)
        if review is not None:
            link_scheduled_admission(session, review, accepted)
        else:
            _remember_explicit_clock(session, owner, cutoff, now)
    return accepted


def _remember_explicit_clock(
    session: Session, owner: UUID, cutoff: datetime, actual_at: datetime
) -> None:
    """Caller holds the portfolio lock; accepted manual input is a durable observation."""
    if not review_schema_available(session):
        return
    target = session.get(PortfolioReviewTarget, owner)
    if target is None:
        target = PortfolioReviewTarget(
            portfolio_id=owner,
            last_observed_at=actual_at,
            status="unobserved",
            reason="NOT_YET_OBSERVED",
        )
        session.add(target)
    target.last_explicit_review_cutoff = max(target.last_explicit_review_cutoff or cutoff, cutoff)
    session.flush()


def _matching_review_run(
    session: Session, payload: RecommendationPayload, *, scheduled_only: bool
) -> RecommendationRun | None:
    if not review_schema_available(session):
        return None
    frozen = payload.model_dump(mode="json")
    conditions = [RecommendationRun.portfolio_id == payload.portfolio_id]
    for field in (
        "portfolio_revision",
        "last_sequence",
        "strategy_version_id",
        "config_sha256",
        "snapshot_id",
        "snapshot_sha256",
        "calendar_sha256",
        "source_mode",
        "engine_version",
        "decision_cutoff_utc",
    ):
        conditions.append(RecommendationRun.payload[field].as_string() == str(frozen[field]))
    for field in ("as_of_session", "clock_mode", "seed"):
        conditions.append(
            RecommendationRun.payload["inputs"][field].as_string() == str(frozen["inputs"][field])
        )
    if scheduled_only:
        conditions.append(
            exists(
                select(PortfolioReviewOccurrence.id).where(
                    PortfolioReviewOccurrence.recommendation_id == RecommendationRun.id,
                    PortfolioReviewOccurrence.outcome == "admitted",
                )
            )
        )
    row = session.scalar(
        select(RecommendationRun)
        .join(Job, Job.id == RecommendationRun.job_id)
        .outerjoin(RecommendationReference, RecommendationReference.id == RecommendationRun.id)
        .where(
            *conditions,
            or_(
                Job.status.in_(("queued", "running")),
                and_(Job.status == "completed", RecommendationReference.disposition == "ready"),
            ),
        )
        .order_by(RecommendationRun.created_at.desc(), RecommendationRun.id.desc())
        .limit(1)
    )
    if row is not None:
        job = session.get(Job, row.job_id)
        if job is None or job.kind != "evaluate_portfolio" or job.payload != row.payload:
            raise ValueError("Reusable review linkage is unavailable")
        original = RecommendationPayload.model_validate(row.payload)
        if original.portfolio_id != payload.portfolio_id:
            raise ValueError("Reusable review owner differs")
        if job.status == "completed":
            reference = session.get(RecommendationReference, row.id)
            if (
                reference is None
                or digest(reference.content) != reference.content_sha256
                or job.result is None
                or job.result.get("resource_id") != str(row.id)
            ):
                raise ValueError("Reusable completed review evidence is unavailable")
    return row


def _remember_request_alias(
    session: Session,
    owner: UUID,
    key: UUID | None,
    request: RecommendationRequest,
    accepted: RecommendationAccepted,
    actual_at: datetime,
) -> None:
    if key is not None and review_schema_available(session):
        session.add(
            RecommendationRequestAlias(
                portfolio_id=owner,
                idempotency_key=key,
                recommendation_id=accepted.recommendation_id,
                inputs_canonical_json=request.canonical_bytes().decode(),
                created_at=actual_at,
            )
        )
        session.flush()


def validate_computed(payload: RecommendationPayload, computed: RecommendationComputed) -> None:
    if render_recommendation(payload, computed.prepared) != computed.recommendation:
        raise ValueError("Recommendation differs from original measured evidence")
    forecast = computed.forecast_inputs
    if (
        forecast.portfolio_id != payload.portfolio_id
        or forecast.portfolio_revision != payload.portfolio_revision
        or forecast.strategy_version_id != payload.strategy_version_id
        or forecast.config_sha256 != payload.config_sha256
        or forecast.snapshot_id != payload.snapshot_id
        or forecast.snapshot_sha256 != payload.snapshot_sha256
        or forecast.calendar_sha256 != payload.calendar_sha256
        or forecast.source_mode != payload.source_mode
        or forecast.as_of_session != payload.inputs.as_of_session
        or forecast.valuation_as_of_session != payload.inputs.as_of_session
        or forecast.decision_cutoff_utc != payload.decision_cutoff_utc
        or forecast.seed != payload.inputs.seed
        or forecast.initial_value_usd != computed.prepared.plan.portfolio_value_usd
        or forecast.current_allocation.upfront_cost_usd is None
        or Decimal(forecast.current_allocation.upfront_cost_usd) != 0
        or forecast.proposed_allocation.upfront_cost_usd
        != computed.recommendation.estimated_total_trade_cost_usd
    ):
        raise ValueError("Forecast differs from original recommendation context")


def seal_recommendation(queue: Queue, lease: Lease, encoded: str) -> None:
    if lease.kind != "evaluate_portfolio" or len(encoded.encode()) > MAX_RECOMMENDATION_BYTES:
        raise ValueError("Invalid recommendation completion")
    payload = RecommendationPayload.model_validate(lease.payload)
    computed = RecommendationComputed.model_validate_json(encoded)
    validate_computed(payload, computed)
    forecast_payload = ForecastPayload(
        forecast_id=payload.forecast_id,
        inputs_canonical_json=computed.forecast_inputs.canonical_bytes().decode(),
        engine_version=payload.engine_version,
    )
    with Session(queue.engine) as session, session.begin():
        # Same portfolio -> job lock order as the economic posting controller.
        portfolio = _locked(session, payload.portfolio_id)
        job, now = queue.owned(session, lease)
        if (
            job is None
            or job.kind != "evaluate_portfolio"
            or job.status != "running"
            or job.attempt_deadline is None
            or job.attempt_deadline <= now
        ):
            raise PublicationFenceError("Recommendation lease is no longer valid")
        run = session.get(RecommendationRun, payload.recommendation_id)
        if (
            run is None
            or run.job_id != job.id
            or run.portfolio_id != payload.portfolio_id
            or run.payload != payload.model_dump(mode="json")
            or job.payload != run.payload
        ):
            raise ValueError("Recommendation job linkage differs from original inputs")
        current = session.get(CurrentSnapshot, payload.source_mode)
        disposition = (
            "ready"
            if (
                portfolio.revision == payload.portfolio_revision
                and portfolio.last_sequence == payload.last_sequence
                and portfolio.strategy_version_id == payload.strategy_version_id
                and portfolio.source_mode == payload.source_mode
                and portfolio.status == "active"
                and not portfolio.reconciliation_failed
                and current is not None
                and current.snapshot_id == payload.snapshot_id
            )
            else "expired"
        )
        plan = computed.prepared.plan
        intent = (
            ExecutionIntentV1(engine_version=payload.engine_version, orders=plan.orders).model_dump(
                mode="json"
            )
            if plan.orders
            else None
        )
        # Float statistics live in canonical JSON strings. This preserves exact
        # archived tokens and the existing ledger's float-free content digest.
        content = {
            "schema_version": 1,
            "recommendation_canonical_json": canonical_json(
                load_json(computed.recommendation.model_dump_json())
            ).decode(),
            "prepared_canonical_json": canonical_json(
                load_json(computed.prepared.model_dump_json())
            ).decode(),
            "forecast_inputs_canonical_json": forecast_payload.inputs_canonical_json,
            "request_canonical_json": payload.inputs.canonical_bytes().decode(),
            "computed_at": now.isoformat().replace("+00:00", "Z"),
            "clock_mode": payload.inputs.clock_mode,
            "execution_intent": intent,
        }
        session.add(
            RecommendationReference(
                id=payload.recommendation_id,
                portfolio_id=payload.portfolio_id,
                strategy_version_id=payload.strategy_version_id,
                snapshot_id=payload.snapshot_id,
                as_of_session=payload.inputs.as_of_session,
                decision_cutoff=payload.decision_cutoff_utc,
                portfolio_revision=payload.portfolio_revision,
                source_mode=payload.source_mode,
                content=content,
                content_sha256=digest(content),
                disposition=disposition,
                created_at=computed.recommendation.created_at,
            )
        )
        _enqueue_frozen_forecast(session, queue, forecast_payload)
        session.flush()
        session.add(
            RecommendationPublication(
                recommendation_id=payload.recommendation_id,
                forecast_id=payload.forecast_id,
                attempt_token=lease.token,
                completed_at=now,
            )
        )
        session.flush()
        job, completed_at = queue.owned(session, lease)
        if (
            job is None
            or job.kind != "evaluate_portfolio"
            or job.status != "running"
            or job.attempt_deadline is None
            or job.attempt_deadline <= completed_at
        ):
            raise PublicationFenceError("Recommendation lease expired during publication")
        job.result = JobResult(
            kind="resource",
            resource_id=payload.recommendation_id,
            message="Immutable recommendation published; forecast has its own observable job.",
        ).model_dump(mode="json")
        job.status, job.progress = "completed", 100
        queue.finish_attempt(session, job, completed_at, "completed")
