"""Read-only composition of the shared strategy, allocation and order planner."""

from collections.abc import Callable
from decimal import Decimal
from fractions import Fraction
from typing import Literal

from backend.domain.evaluation import StrategyEvaluationPayload, StrategyEvaluationRequest
from backend.domain.forecast import ForecastAllocation, ForecastWeight
from backend.domain.recommendation import (
    ActionEvidence,
    CandidateEvidence,
    FeatureValue,
    RecommendationV1,
    RecommendedAction,
    TargetWeight,
)
from backend.domain.types import decimal_text
from backend.forecasting.contracts import ForecastInputs
from backend.market_data.files import PinnedSnapshot
from backend.market_data.models import Calendar
from backend.market_data.repository import MarketRepository
from backend.portfolio.allocation import allocate_momentum
from backend.portfolio.corporate_actions import action_key, apply_action
from backend.portfolio.execution import (
    ExecutionContext,
    MarketEvidence,
    PortfolioState,
    arithmetic,
    money,
)
from backend.portfolio.planner import plan_orders
from backend.portfolio.recommendation_contracts import RecommendationPayload, RecommendationPrepared
from backend.portfolio.risk import assess_targets
from backend.portfolio.valuation import value_close
from backend.strategies.evaluations import result_from_engine
from backend.strategies.momentum import evaluate_snapshot


def planning_context(payload: RecommendationPayload) -> ExecutionContext:
    # A planner quote assumes immediate simulated approval at the cutoff. It is
    # never a recorded operator approval and cannot post or authorize a fill.
    return ExecutionContext(
        snapshot_id=payload.snapshot_id,
        snapshot_sha256=payload.snapshot_sha256,
        calendar_sha256=payload.calendar_sha256,
        mode=payload.source_mode,
        engine_version=payload.engine_version,
        execution_mode="historical_replay"
        if payload.source_mode == "synthetic_fixture"
        else "current_paper",
        decision_session=payload.inputs.as_of_session,
        decision_cutoff=payload.decision_cutoff_utc,
        approved_at=payload.decision_cutoff_utc,
    )


def prepare_recommendation(
    pinned: PinnedSnapshot,
    payload: RecommendationPayload,
    *,
    cancelled: Callable[[], bool] = lambda: False,
) -> RecommendationPrepared:
    if cancelled():
        raise InterruptedError("Recommendation cancelled")
    config = payload.config
    measured = allocate_momentum(
        evaluate_snapshot(
            pinned,
            config,
            payload.decision_cutoff_utc,
            payload.inputs.as_of_session,
            engine_version=payload.engine_version,
            live=payload.source_mode != "synthetic_fixture",
        ),
        config,
    )
    if cancelled():
        raise InterruptedError("Recommendation cancelled")
    with MarketRepository(pinned) as repository:
        view = repository.accounting_as_of(
            payload.decision_cutoff_utc, payload.inputs.as_of_session
        )
        sectors = repository.accounting_sectors(
            tuple(row.asset_id for row in payload.state.positions),
            payload.decision_cutoff_utc,
            payload.inputs.as_of_session,
        )
    state = payload.state.model_copy(
        update={
            "positions": tuple(
                row.model_copy(update={"sector": sectors[row.asset_id]})
                for row in payload.state.positions
            )
        }
    )
    calendar = Calendar.model_validate_json(
        pinned.artifacts[pinned.manifest.calendar.artifact_path]
    )
    held = {row.asset_id for row in payload.state.positions if Decimal(row.quantity) > 0}
    entitlements = {row.key for row in payload.state.entitlements if Decimal(row.quantity) > 0}
    applied = {row.key for row in payload.state.applied_actions}
    for action in view.actions:
        key = action_key(action)
        if action.effective_session > payload.inputs.as_of_session or (
            action.asset_id not in held and key not in entitlements and key not in applied
        ):
            continue
        try:
            check = apply_action(
                payload.state,
                action,
                session=payload.inputs.as_of_session,
                observed_at=payload.decision_cutoff_utc,
                live=payload.source_mode != "synthetic_fixture",
                calendar=calendar,
            )
        except ValueError:
            raise ValueError("RECONCILIATION_REQUIRED") from None
        if check.status == "already_applied":
            continue
        if check.reason == "WAITING_FOR_PAYABLE_SESSION" and check.state_after == payload.state:
            continue
        # A recommendation cannot post missing split/entitlement/dividend effects
        # or pretend that the old share/cash projection already includes them.
        raise ValueError("RECONCILIATION_REQUIRED")
    marks = MarketEvidence(
        snapshot_id=payload.snapshot_id,
        snapshot_sha256=payload.snapshot_sha256,
        mode=payload.source_mode,
        freshness="fixture" if payload.source_mode == "synthetic_fixture" else "fresh",
        bars=view.bars,
    )
    plan = plan_orders(
        state,
        measured.allocation.targets,
        measured.allocation.cash_weight,
        config.portfolio,
        planning_context(payload),
        calendar,
        marks,
    )
    if (
        plan.status != "ready"
        or plan.portfolio_value_usd is None
        or Decimal(plan.portfolio_value_usd) <= 0
    ):
        raise ValueError("VALUATION_UNAVAILABLE")
    evaluation_payload = StrategyEvaluationPayload(
        evaluation_id=payload.recommendation_id,
        inputs=StrategyEvaluationRequest(
            strategy_version_id=payload.strategy_version_id,
            snapshot_id=payload.snapshot_id,
            as_of_session=payload.inputs.as_of_session,
        ),
        source_mode=payload.source_mode,
        snapshot_sha256=payload.snapshot_sha256,
        config_sha256=payload.config_sha256,
        calendar_sha256=payload.calendar_sha256,
        engine_version=payload.engine_version,
        decision_cutoff_utc=payload.decision_cutoff_utc,
        config_canonical_json=payload.config_canonical_json,
    )
    return RecommendationPrepared(
        evaluation=result_from_engine(evaluation_payload, measured), plan=plan
    )


def _fraction_text(value: Fraction) -> str:
    with arithmetic(str(value.numerator), str(value.denominator)):
        return decimal_text(Decimal(value.numerator) / Decimal(value.denominator))


def _allocation(
    state: PortfolioState, values: dict[str, Fraction], nav: Fraction, cost: str
) -> ForecastAllocation:
    return ForecastAllocation(
        weights=tuple(
            ForecastWeight(asset_id=identity, weight=_fraction_text(value / nav))
            for identity, value in sorted(values.items())
            if value > 0
        ),
        cash_weight=_fraction_text(Fraction(state.cash_usd) / nav),
        upfront_cost_usd=cost,
    )


def render_recommendation(
    payload: RecommendationPayload, prepared: RecommendationPrepared
) -> RecommendationV1:
    """Explain recorded numbers; never recompute ranking or mutate a portfolio."""
    evaluation, plan, config = prepared.evaluation, prepared.plan, payload.config
    repro = evaluation.reproducibility
    if (
        repro.strategy_version_id != payload.strategy_version_id
        or repro.snapshot_id != payload.snapshot_id
        or repro.config_sha256 != payload.config_sha256
        or repro.snapshot_sha256 != payload.snapshot_sha256
        or repro.calendar_sha256 != payload.calendar_sha256
        or repro.engine_version != payload.engine_version
        or evaluation.as_of_session != payload.inputs.as_of_session
        or evaluation.decision_cutoff_utc != payload.decision_cutoff_utc
        or evaluation.mode != payload.source_mode
        or plan.context != planning_context(payload)
        or plan.status != "ready"
        or assess_targets(
            evaluation.target_weights, evaluation.cash_target_weight, config.portfolio
        )
        != evaluation.constraint_evidence
    ):
        raise ValueError("INPUT_FINGERPRINT_MISMATCH")
    notionals = {}
    for quote in plan.preview:
        if quote.effect is not None:
            with arithmetic(quote.effect.raw_price, quote.effect.quantity):
                notionals[quote.order.asset_id] = money(
                    Decimal(quote.effect.raw_price) * Decimal(quote.effect.quantity)
                )
    actions = tuple(
        RecommendedAction(
            asset_id=row.asset_id,
            side=row.side,
            label="INCREASE" if row.side == "BUY" else "REDUCE" if row.side == "SELL" else "HOLD",
            current_weight=row.current_weight,
            target_weight=row.target_weight,
            estimated_notional_usd=notionals[row.asset_id] if row.side != "HOLD" else "0.00",
            estimated_quantity=row.preview_executable_quantity
            if row.side != "HOLD"
            else "0.000000",
            reason_codes=(row.reason,),
            evidence=ActionEvidence(
                position_cap=config.portfolio.max_position_weight, current_weight=row.current_weight
            ),
            explanation=(
                f"{row.side.title()} {row.asset_id}: current weight {row.current_weight}, "
                f"target {row.target_weight}; "
                f"{row.reason.lower().replace('_', ' ')}. "
                f"Estimated quantity "
                f"{row.preview_executable_quantity if row.side != 'HOLD' else '0.000000'}; "
                "paper preview only."
            ),
        )
        for row in plan.actions
    )
    candidates = []
    for row in evaluation.candidates:
        features = tuple(
            FeatureValue(name=name, value=value, unavailable_reason=None)
            for name, value in (row.features.model_dump().items() if row.features else ())
            if isinstance(value, (float, int)) and not isinstance(value, bool)
        )
        contributions = tuple(
            FeatureValue(name=name, value=value, unavailable_reason=None)
            for name, value in (row.scoring.model_dump().items() if row.scoring else ())
            if name != "score" and isinstance(value, (float, int)) and not isinstance(value, bool)
        )
        candidates.append(
            CandidateEvidence(
                asset_id=row.asset_id,
                features=features,
                score=row.scoring.score if row.scoring else None,
                exclusion_reasons=row.reasons or (() if row.scoring else ("FEATURES_UNAVAILABLE",)),
                contributions=contributions,
            )
        )
    with arithmetic(
        *(row.estimated_slippage_usd for row in plan.actions),
        *(row.estimated_commission_usd for row in plan.actions),
    ):
        cost = money(
            sum(
                (
                    Decimal(row.estimated_slippage_usd) + Decimal(row.estimated_commission_usd)
                    for row in plan.actions
                ),
                Decimal(0),
            )
        )
    sides = {row.side for row in actions if row.side != "HOLD"}
    summary: Literal["BUY", "SELL", "HOLD", "REBALANCE", "ALLOCATE_TO_CASH"] = (
        "ALLOCATE_TO_CASH"
        if not evaluation.target_weights
        else "REBALANCE"
        if len(sides) > 1
        else "BUY"
        if sides == {"BUY"}
        else "SELL"
        if sides == {"SELL"}
        else "HOLD"
    )
    created = max(payload.requested_at, payload.decision_cutoff_utc)
    recommendation = RecommendationV1(
        id=payload.recommendation_id,
        portfolio_id=payload.portfolio_id,
        portfolio_revision=payload.portfolio_revision,
        strategy_version_id=payload.strategy_version_id,
        snapshot_id=payload.snapshot_id,
        snapshot_sha256=payload.snapshot_sha256,
        as_of_session=payload.inputs.as_of_session,
        decision_cutoff_utc=payload.decision_cutoff_utc,
        data_status=payload.source_mode,
        summary_action=summary,
        target_weights=tuple(
            TargetWeight(
                asset_id=row.asset_id, weight=row.weight, reason_codes=("RISK_CONSTRAINED_TARGET",)
            )
            for row in evaluation.target_weights
        ),
        cash_target_weight=evaluation.cash_target_weight,
        actions=actions,
        candidates=tuple(candidates),
        estimated_total_trade_cost_usd=cost,
        forecast_id=payload.forecast_id,
        engine_version=payload.engine_version,
        created_at=created,
        status="ready",
    )
    return recommendation


def compose_recommendation(
    payload: RecommendationPayload, prepared: RecommendationPrepared, pinned: PinnedSnapshot
) -> tuple[RecommendationV1, ForecastInputs]:
    recommendation = render_recommendation(payload, prepared)
    plan = prepared.plan
    cost = recommendation.estimated_total_trade_cost_usd
    with MarketRepository(pinned) as repository:
        view = repository.accounting_as_of(
            payload.decision_cutoff_utc, payload.inputs.as_of_session
        )
        calendar = repository.calendar
    marks = MarketEvidence(
        snapshot_id=payload.snapshot_id,
        snapshot_sha256=payload.snapshot_sha256,
        mode=payload.source_mode,
        freshness="fixture" if payload.source_mode == "synthetic_fixture" else "fresh",
        bars=view.bars,
    )
    current = value_close(payload.state, planning_context(payload), calendar, marks)
    projected_state = plan.preview[-1].state_after if plan.preview else payload.state
    proposed = value_close(projected_state, planning_context(payload), calendar, marks)
    if current.nav is None or current.nav <= 0 or proposed.nav is None or proposed.nav <= 0:
        raise ValueError("VALUATION_UNAVAILABLE")
    forecast = ForecastInputs(
        portfolio_id=payload.portfolio_id,
        portfolio_revision=payload.portfolio_revision,
        strategy_version_id=payload.strategy_version_id,
        config_sha256=payload.config_sha256,
        snapshot_id=payload.snapshot_id,
        snapshot_sha256=payload.snapshot_sha256,
        calendar_sha256=payload.calendar_sha256,
        source_mode=payload.source_mode,
        as_of_session=payload.inputs.as_of_session,
        decision_cutoff_utc=payload.decision_cutoff_utc,
        valuation_as_of_session=payload.inputs.as_of_session,
        initial_value_usd=current.money_value(),
        current_allocation=_allocation(payload.state, current.values, current.nav, "0.00"),
        proposed_allocation=_allocation(projected_state, proposed.values, proposed.nav, cost),
        seed=payload.inputs.seed,
    )
    return recommendation, forecast
