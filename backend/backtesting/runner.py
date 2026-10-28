"""Strict-gap chronological replay through the shared strategy/portfolio kernel."""

from collections import Counter
from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from backend.backtesting.schedule import ExperimentSchedule, build_schedule
from backend.domain.experiment import ExperimentRequest
from backend.domain.strategy import StrategyConfigV1
from backend.domain.types import Contract, Hash256, Money, Reason, SourceMode, load_json
from backend.jobs.registry import validate_workload
from backend.market_data.repository import MarketRepository, MarketView
from backend.portfolio.allocation import AllocatedMomentum, allocate_momentum
from backend.portfolio.corporate_actions import ActionResult, action_key, apply_action
from backend.portfolio.execution import (
    DEFAULT_EXECUTION_POLICY,
    ExecutionContext,
    ExecutionResult,
    MarketEvidence,
    PortfolioState,
    calendar_digest,
    simulate_batch,
)
from backend.portfolio.planner import OrderPlan, plan_orders
from backend.portfolio.valuation import value_close
from backend.strategies.clock import decision_cutoff
from backend.strategies.momentum import evaluate_strategy


class BacktestFailure(ValueError):
    """Safe inspectable reason; no partially completed financial result."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class EquityPoint(Contract):
    session_date: date
    phase: Literal["development", "holdout"]
    nav_usd: Money
    state: PortfolioState


class BacktestDecision(Contract):
    measured: AllocatedMomentum
    plan: OrderPlan


class BacktestCoreResult(Contract):
    """Internal sealed-core input to #40, never a completed public experiment."""

    schema_version: Literal[1] = 1
    policy_version: Literal["walk_forward_v1"] = "walk_forward_v1"
    inputs: ExperimentRequest
    config_sha256: Hash256
    snapshot_sha256: Hash256
    calendar_sha256: Hash256
    engine_version: str
    source_mode: SourceMode
    holdout_start_session: date | None
    warnings: tuple[Reason, ...]
    points: tuple[EquityPoint, ...]
    decisions: tuple[BacktestDecision, ...]
    executions: tuple[ExecutionResult, ...]
    actions: tuple[ActionResult, ...]


def validate_source(repository: MarketRepository) -> None:
    manifest = repository.snapshot.manifest
    if manifest.quality == "blocked" or manifest.price_basis.ohlc != "raw_as_traded":
        raise BacktestFailure("UNSUPPORTED_ACCOUNTING_SOURCE")
    if manifest.mode == "synthetic_fixture":
        return  # PinnedSnapshot/manifest validation owns authored synthetic provenance.
    if (
        manifest.source.rights_status != "verified_local_use"
        or not manifest.source.rights_reference
    ):
        raise BacktestFailure("UNSUPPORTED_ACCOUNTING_SOURCE")
    evidence = next(
        row
        for row in manifest.artifacts
        if row.role == "provenance" and row.sha256 == manifest.source.capabilities_sha256
    )
    capabilities = load_json(repository.snapshot.artifacts[evidence.path])
    if not isinstance(capabilities, dict) or any(
        capabilities.get(key) is not True
        for key in (
            "raw_execution_prices",
            "complete_action_accounting",
            "historical_membership",
            "historical_publication_times",
        )
    ):
        raise BacktestFailure("UNSUPPORTED_ACCOUNTING_SOURCE")


def _warnings(
    schedule: ExperimentSchedule, config: StrategyConfigV1, repository: MarketRepository
) -> set[str]:
    result = set(repository.snapshot.manifest.warnings)
    first = schedule.sessions[0].session_date
    prior = sum(row.session_date < first for row in repository.calendar.sessions)
    if prior < config.universe.min_history_sessions:
        result.add("LIMITED_WARMUP")
    if schedule.holdout_sessions < 252:
        result.add("INSUFFICIENT_HOLDOUT")
    result.update(("HOLDOUT_REPEATED_SELECTION_CAVEAT", "ZERO_CASH_RETURN"))
    if repository.snapshot.manifest.mode == "synthetic_fixture":
        result.add("SYNTHETIC_DATA_ONLY")
    return result


def run_backtest(
    repository: MarketRepository,
    request: ExperimentRequest,
    config: StrategyConfigV1,
    *,
    engine_version: str,
    cancelled: Callable[[], bool] = lambda: False,
) -> BacktestCoreResult:
    """No DB/network writes. A missing required mark/open fails the whole core.

    Daily bars may arrive after the originally eligible open but must be known by
    that session's overnight cutoff. Later evidence never revises a sealed NAV.
    No raw/action capability is inferred from diagnostic support.
    """
    validate_source(repository)
    manifest, calendar = repository.snapshot.manifest, repository.calendar
    if request.snapshot_id != manifest.snapshot_id():
        raise BacktestFailure("SNAPSHOT_IDENTITY_MISMATCH")
    validate_workload(assets=len(manifest.coverage.asset_ids), sessions=len(calendar.sessions))
    if (
        manifest.coverage.first_session is None
        or manifest.coverage.last_session is None
        or request.start_session < manifest.coverage.first_session
        or request.end_session_exclusive > manifest.coverage.last_session + timedelta(days=1)
    ):
        raise BacktestFailure("UNCOVERED_EXPERIMENT_INTERVAL")
    schedule = build_schedule(request, calendar)
    if (
        manifest.coverage.first_session is None
        or manifest.coverage.last_session is None
        or schedule.sessions[0].session_date < manifest.coverage.first_session
        or schedule.sessions[-1].session_date > manifest.coverage.last_session
        or manifest.coverage.latest_completed_session is None
        or schedule.sessions[-1].session_date > manifest.coverage.latest_completed_session
    ):
        raise BacktestFailure("UNCOVERED_EXPERIMENT_INTERVAL")
    if request.execution_policy_id != DEFAULT_EXECUTION_POLICY.id:
        raise BacktestFailure("UNSUPPORTED_EXECUTION_POLICY")
    warnings = _warnings(schedule, config, repository)
    state = PortfolioState(cash_usd=request.initial_capital_usd, positions=())
    points: list[EquityPoint] = []
    decisions: list[BacktestDecision] = []
    executions: list[ExecutionResult] = []
    actions: list[ActionResult] = []
    pending: OrderPlan | None = None
    digest = calendar_digest(calendar)
    first = schedule.sessions[0].session_date

    def context(day: date) -> ExecutionContext:
        cutoff = decision_cutoff(calendar, day)
        return ExecutionContext(
            snapshot_id=request.snapshot_id,
            snapshot_sha256=manifest.manifest_hash(),
            calendar_sha256=digest,
            mode=manifest.mode,
            engine_version=engine_version,
            execution_mode="historical_replay",
            decision_session=day,
            decision_cutoff=cutoff,
            approved_at=cutoff,
        )

    def market(view: MarketView) -> MarketEvidence:
        return MarketEvidence(
            snapshot_id=request.snapshot_id,
            snapshot_sha256=manifest.manifest_hash(),
            mode=manifest.mode,
            freshness="fixture" if manifest.mode == "synthetic_fixture" else "fresh",
            bars=view.bars,
        )

    for index, session in enumerate(schedule.sessions):
        if cancelled():
            raise BacktestFailure("CANCELLED")
        clock = context(session.session_date)
        accounting = repository.accounting_as_of(clock.decision_cutoff, session.session_date)
        relevant = tuple(
            row
            for row in accounting.actions
            if first <= row.effective_session <= session.session_date
        )
        held = {row.asset_id for row in state.positions if Decimal(row.quantity) > 0}
        today = Counter(
            row.asset_id for row in relevant if row.effective_session == session.session_date
        )
        if any(count > 1 and identity in held for identity, count in today.items()):
            raise BacktestFailure("AMBIGUOUS_ACTION_ORDER")
        # Entitlements and share transforms precede all session trading. No inferred
        # ratio adjustment of an approval made on the pre-action basis.
        pending_ids = {row.asset_id for row in pending.orders} if pending else set()
        for action in sorted(relevant, key=lambda row: (row.effective_session, action_key(row))):
            if (
                action.kind == "split"
                and action.effective_session == session.session_date
                and action.asset_id in pending_ids
            ):
                raise BacktestFailure("ORDER_ACTION_CONFLICT")
            result = apply_action(
                state,
                action,
                session=session.session_date,
                observed_at=clock.decision_cutoff,
                live=False,
                calendar=calendar,
            )
            state = result.state_after
            if result.status != "already_applied":
                actions.append(result)
            if result.status == "pending" and result.reason not in {"WAITING_FOR_PAYABLE_SESSION"}:
                # Unknown zero-share dividends cannot create a cash liability.
                zero_entitlement = any(
                    row.key == action_key(action) and Decimal(row.quantity) == 0
                    for row in state.entitlements
                )
                if not (action.kind == "dividend" and zero_entitlement):
                    raise BacktestFailure(result.reason or "UNRESOLVED_CORPORATE_ACTION")
                warnings.add("UNRESOLVED_ZERO_ENTITLEMENT")
        if pending is not None:
            batch = simulate_batch(
                state,
                pending.orders,
                pending.context,
                calendar,
                market(accounting),
                observed_at=clock.decision_cutoff,
                min_trade_usd=config.portfolio.min_trade_usd,
            )
            if any(not row.terminal for row in batch):
                raise BacktestFailure("MISSING_ELIGIBLE_OPEN")
            executions.extend(batch)
            if batch:
                state = batch[-1].state_after
            pending = None
        valuation = value_close(state, clock, calendar, market(accounting))
        nav = valuation.money_value()
        if nav is None:
            raise BacktestFailure("MISSING_HELD_CLOSE")
        points.append(
            EquityPoint(
                session_date=session.session_date,
                phase="development" if index < schedule.development_sessions else "holdout",
                nav_usd=nav,
                state=state,
            )
        )
        if session.session_date in schedule.decision_sessions:
            measured = allocate_momentum(
                evaluate_strategy(
                    repository.as_of(clock.decision_cutoff, session.session_date),
                    calendar,
                    config,
                    engine_version=engine_version,
                ),
                config,
            )
            plan = plan_orders(
                state,
                measured.allocation.targets,
                measured.allocation.cash_weight,
                config.portfolio,
                clock,
                calendar,
                market(accounting),
            )
            if plan.status != "ready":
                raise BacktestFailure("MISSING_DECISION_CLOSE")
            decisions.append(BacktestDecision(measured=measured, plan=plan))
            warnings.update(measured.momentum.warnings)
            pending = plan
    if cancelled():
        raise BacktestFailure("CANCELLED")
    return BacktestCoreResult(
        inputs=request,
        config_sha256=config.config_hash(),
        snapshot_sha256=manifest.manifest_hash(),
        calendar_sha256=digest,
        engine_version=engine_version,
        source_mode=manifest.mode,
        holdout_start_session=schedule.holdout_start_session,
        warnings=tuple(sorted(warnings)),
        points=tuple(points),
        decisions=tuple(decisions),
        executions=tuple(executions),
        actions=tuple(actions),
    )
