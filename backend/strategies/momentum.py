"""Deterministic scoring evidence shared by every future strategy consumer."""

import hashlib
import math
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from backend.domain.strategy import StrategyConfigV1
from backend.domain.types import (
    Contract,
    FiniteNumber,
    Hash256,
    SessionDate,
    SourceMode,
    UTCTimestamp,
    canonical_json,
)
from backend.market_data.files import PinnedSnapshot
from backend.market_data.models import Calendar
from backend.market_data.repository import MarketRepository, MarketView
from backend.strategies.eligibility import eligible_universe
from backend.strategies.features import population_zscores, sample_log_volatility, window_momentum


class FeatureValues(Contract):
    momentum_long: FiniteNumber
    momentum_short: FiniteNumber
    volatility: Annotated[FiniteNumber, Field(ge=0)]


class ScoreEvidence(Contract):
    momentum_long_z: FiniteNumber
    momentum_short_z: FiniteNumber
    volatility_z: FiniteNumber
    momentum_long_contribution: FiniteNumber
    momentum_short_contribution: FiniteNumber
    volatility_contribution: FiniteNumber
    score: FiniteNumber


class CandidateEvidence(Contract):
    asset_id: str
    sector: str | None
    eligible: bool
    allocation_eligible: bool
    reasons: tuple[str, ...]
    raw_close: str | None
    median_dollar_volume: str | None
    trend_sma: str | None
    input_sha256: Hash256
    features: FeatureValues | None
    scoring: ScoreEvidence | None
    rank: int | None


class DataDiagnosticEvidence(Contract):
    reason: str
    asset_id: str | None
    session_date: SessionDate | None
    count: int


class MomentumEvaluation(Contract):
    schema_version: Literal[1] = 1
    engine_version: Annotated[str, Field(min_length=1)]
    snapshot_id: UUID
    manifest_sha256: Hash256
    config_sha256: Hash256
    calendar_sha256: Hash256
    mode: SourceMode
    cutoff: UTCTimestamp
    session_date: SessionDate
    candidates: tuple[CandidateEvidence, ...]
    selected_ids: tuple[str, ...]
    warnings: tuple[str, ...]
    data_diagnostics: tuple[DataDiagnosticEvidence, ...]


def evaluate_momentum(
    view: MarketView, calendar: Calendar, config: StrategyConfigV1, *, engine_version: str
) -> MomentumEvaluation:
    eligibility = eligible_universe(view, calendar, config)
    features: dict[str, FeatureValues] = {}
    failed = set()
    for item in eligibility:
        if not item.eligible:
            continue
        closes = [bar.adjusted_close for bar in item.window]
        try:
            features[item.asset_id] = FeatureValues(
                momentum_long=window_momentum(closes, config.signals.momentum_long_sessions),
                momentum_short=window_momentum(closes, config.signals.momentum_short_sessions),
                volatility=sample_log_volatility(closes, config.signals.volatility_sessions),
            )
        except (ValueError, ArithmeticError):
            failed.add(item.asset_id)
    ids = sorted(features)
    long_z = population_zscores([features[identity].momentum_long for identity in ids])
    short_z = population_zscores([features[identity].momentum_short for identity in ids])
    vol_z = population_zscores([features[identity].volatility for identity in ids])
    weights = config.signals.z_score_weights
    scoring = {}
    for identity, long, short, volatility in zip(ids, long_z, short_z, vol_z, strict=True):
        contributions = (
            long * float(weights.momentum_long),
            short * float(weights.momentum_short),
            volatility * float(weights.volatility_penalty),
        )
        scoring[identity] = ScoreEvidence(
            momentum_long_z=long,
            momentum_short_z=short,
            volatility_z=volatility,
            momentum_long_contribution=contributions[0],
            momentum_short_contribution=contributions[1],
            volatility_contribution=contributions[2],
            score=math.fsum(contributions),
        )
    ordered = sorted(ids, key=lambda identity: (-scoring[identity].score, identity))
    ranks = {identity: index + 1 for index, identity in enumerate(ordered)}
    selected = tuple(identity for identity in ordered if features[identity].volatility > 0)[
        : config.portfolio.max_positions
    ]
    candidates = []
    for item in eligibility:
        measured = features.get(item.asset_id)
        reasons = set(item.reasons)
        if item.asset_id in failed:
            reasons.add("NONFINITE_FEATURE")
        if measured is not None and measured.volatility == 0:
            reasons.add("ZERO_VOLATILITY")
        candidates.append(
            CandidateEvidence(
                asset_id=item.asset_id,
                sector=item.sector,
                eligible=item.eligible and measured is not None,
                allocation_eligible=measured is not None and measured.volatility > 0,
                reasons=tuple(sorted(reasons)),
                raw_close=item.raw_close,
                median_dollar_volume=item.median_dollar_volume,
                trend_sma=item.trend_sma,
                input_sha256=hashlib.sha256(
                    canonical_json([bar.model_dump(mode="json") for bar in item.window])
                ).hexdigest(),
                features=measured,
                scoring=scoring.get(item.asset_id),
                rank=ranks.get(item.asset_id),
            )
        )
    return MomentumEvaluation(
        engine_version=engine_version,
        snapshot_id=view.snapshot_id,
        manifest_sha256=view.manifest_hash,
        config_sha256=config.config_hash(),
        calendar_sha256=hashlib.sha256(
            canonical_json(calendar.model_dump(mode="json"))
        ).hexdigest(),
        mode=view.mode,
        cutoff=view.cutoff,
        session_date=view.session_date,
        candidates=tuple(candidates),
        selected_ids=selected,
        warnings=view.warnings,
        data_diagnostics=tuple(
            DataDiagnosticEvidence(
                reason=item.reason,
                asset_id=item.asset_id,
                session_date=item.session_date,
                count=item.count,
            )
            for item in view.diagnostics
        ),
    )


def evaluate_snapshot(
    snapshot: PinnedSnapshot,
    config: StrategyConfigV1,
    cutoff: datetime,
    session_date: date,
    *,
    engine_version: str,
    live: bool = False,
) -> MomentumEvaluation:
    """Preferred entry point: one verified snapshot owns both bars and calendar."""
    with MarketRepository(snapshot) as repository:
        view = repository.as_of(cutoff, session_date, live=live)
        return evaluate_momentum(view, repository.calendar, config, engine_version=engine_version)
