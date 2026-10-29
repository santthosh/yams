"""Pinned-calendar suggestions, never return-based selection or financial mutation."""

from pathlib import Path
from uuid import UUID

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from backend.domain.decision_context import ApprovalPreviewV1, DecisionInputsV1
from backend.forecasting.horizon import map_horizon
from backend.jobs.registry import validate_workload
from backend.market_data.catalog import verified_snapshot
from backend.market_data.models import Calendar
from backend.persistence.models.ledger import LedgerEvent, PaperOrderBatch
from backend.persistence.models.snapshot import DatasetSnapshot
from backend.portfolio.accounts import account_record
from backend.portfolio.execution import next_eligible_session
from backend.portfolio.paper_clock import operator_clock
from backend.portfolio.paper_controls import public_recommendation
from backend.portfolio.recommendation_queries import detail
from backend.strategies.clock import decision_cutoff


def decision_inputs(engine: Engine, root: Path, owner: UUID) -> DecisionInputsV1:
    record = account_record(engine, owner)
    with Session(engine) as session:
        event = session.scalar(
            select(LedgerEvent).where(
                LedgerEvent.portfolio_id == owner, LedgerEvent.sequence == record.last_sequence
            )
        )
        if event is None:
            raise ValueError("Posted chronology unavailable")
        clock, _ = operator_clock(
            session, owner, record.mode, max(event.recorded_at, event.effective_at)
        )
        source = (
            session.get(DatasetSnapshot, record.valuation_snapshot_id)
            if record.valuation_snapshot_id
            else None
        )
    result = DecisionInputsV1(
        portfolio_id=owner,
        data_status=record.mode,
        snapshot_id=source.id if source else None,
        clock_at=clock,
        suggested_session=None,
        suggested_cutoff_utc=None,
        unavailable_reason="SNAPSHOT_UNAVAILABLE",
    )
    if record.mode != "synthetic_fixture":
        return result.model_copy(update={"unavailable_reason": "UNSUPPORTED_ACCOUNTING_SOURCE"})
    if source is None:
        return result
    pinned = verified_snapshot(source, root)
    calendar = Calendar.model_validate_json(
        pinned.artifacts[pinned.manifest.calendar.artifact_path]
    )
    coverage = pinned.manifest.coverage
    if pinned.manifest.quality == "blocked":
        return result.model_copy(update={"unavailable_reason": "SNAPSHOT_BLOCKED"})
    try:
        validate_workload(assets=len(coverage.asset_ids), sessions=len(calendar.sessions))
    except ValueError:
        return result.model_copy(update={"unavailable_reason": "WORKLOAD_LIMIT"})
    # 253 calendar closes can support 252 returns; actual price completeness is
    # still assessed by the engine. Choose earliest, without inspecting returns.
    covered = [
        row
        for row in calendar.sessions
        if coverage.first_session is not None
        and coverage.latest_completed_session is not None
        and coverage.first_session <= row.session_date <= coverage.latest_completed_session
    ]
    for row in covered[252:]:
        try:
            cutoff = decision_cutoff(calendar, row.session_date)
        except ValueError:
            continue
        if cutoff >= clock and map_horizon(calendar, cutoff).unavailable_reason is None:
            return result.model_copy(
                update={
                    "suggested_session": row.session_date,
                    "suggested_cutoff_utc": cutoff,
                    "unavailable_reason": None,
                }
            )
    return result.model_copy(update={"unavailable_reason": "NO_SUPPORTED_REVIEW_SESSION"})


def approval_preview(engine: Engine, root: Path, identity: UUID) -> ApprovalPreviewV1:
    view = detail(engine, root, identity)
    if view is None:
        raise LookupError("Recommendation unavailable")
    reason = next(iter(view.stale_reasons), None)
    if not view.is_current:
        reason = reason or "RECOMMENDATION_NOT_READY"
    opening = None
    with Session(engine) as session:
        rec = public_recommendation(session, identity)
        source = session.get(DatasetSnapshot, rec.snapshot_id)
        if source is None:
            raise ValueError("Decision source unavailable")
        if not rec.content.get("execution_intent"):
            reason = reason or "NO_EXECUTABLE_ORDERS"
        active = session.scalar(
            select(PaperOrderBatch.id).where(
                PaperOrderBatch.portfolio_id == view.portfolio_id, ~PaperOrderBatch.terminal
            )
        )
        if active is not None:
            reason = reason or "ACTIVE_ORDER_BATCH"
        clock, _ = operator_clock(
            session,
            view.portfolio_id,
            view.data_status,
            max(rec.created_at, rec.decision_cutoff),
        )
    pinned = verified_snapshot(source, root)
    calendar = Calendar.model_validate_json(
        pinned.artifacts[pinned.manifest.calendar.artifact_path]
    )
    try:
        opening = next_eligible_session(calendar, view.decision_cutoff_utc, clock).open_at
    except ValueError:
        reason = reason or "CALENDAR_UNAVAILABLE"
    return ApprovalPreviewV1(
        recommendation_id=identity,
        portfolio_id=view.portfolio_id,
        expected_revision=view.portfolio_revision,
        indicative_eligible_open_at=opening,
        unavailable_reason=reason,
    )
