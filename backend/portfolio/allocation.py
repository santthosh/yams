"""ADR-003 simultaneous capped inverse-volatility water-fill, without ledger writes."""

from collections.abc import Iterable
from fractions import Fraction
from typing import Annotated

from pydantic import Field, StrictBool

from backend.domain.strategy import PortfolioConfig, StrategyConfigV1
from backend.domain.types import AssetId, Contract, FiniteNumber, FractionString, Reason
from backend.portfolio.risk import AllocationTarget, RiskReport, assess_targets, finite_decimal
from backend.strategies.momentum import MomentumEvaluation

# Minimum numerical transport precision, NOT currency/share sizing. The grid
# expands for tiny positive weights; internal water-fill is exact rational.
SERIALIZATION_SCALE = 10**36


class AllocationCandidate(Contract):
    asset_id: AssetId
    sector: Annotated[str, Field(strict=True, min_length=1)]
    score: FiniteNumber
    volatility: Annotated[FiniteNumber, Field(ge=0)]
    eligible: StrictBool = True


class AllocationExclusion(Contract):
    asset_id: AssetId
    reason: Reason


class AllocationResult(Contract):
    selected_ids: tuple[AssetId, ...]
    targets: tuple[AllocationTarget, ...]
    cash_weight: FractionString
    exclusions: tuple[AllocationExclusion, ...]
    reasons: tuple[Reason, ...]
    risk: RiskReport


class AllocatedMomentum(Contract):
    momentum: MomentumEvaluation
    allocation: AllocationResult


def _joint_decimal_weights(
    weights: dict[str, Fraction], sectors: dict[str, str], policy: PortfolioConfig
) -> dict[str, Fraction]:
    """Largest remainders with cap constraints, conserving the exact invested total.

    All binding totals (budget, sector, position) have <=6 decimal places. Thus
    final total investment is representable on this finer grid. The grid expands
    until even the smallest positive weight has at least 36 significant digits.
    Per-asset error is strictly <1e-36; no residue is silently added to cash.
    """
    scale = SERIALIZATION_SCALE
    smallest = min((weight for weight in weights.values() if weight > 0), default=Fraction(1))
    while smallest * scale < 10**35:
        scale *= 10
    scaled = {identity: weight * scale for identity, weight in weights.items()}
    units = {identity: value.numerator // value.denominator for identity, value in scaled.items()}
    total = sum(scaled.values(), Fraction(0))
    if total.denominator != 1:
        raise ArithmeticError("Binding allocation total must have a finite decimal representation")
    remaining = int(total) - sum(units.values())
    position_cap = int(Fraction(policy.max_position_weight) * scale)
    sector_cap = int(Fraction(policy.max_sector_weight) * scale)
    sector_units = dict.fromkeys(sectors.values(), 0)
    for identity, amount in units.items():
        sector_units[sectors[identity]] += amount
    order = sorted(units, key=lambda identity: (-(scaled[identity] - units[identity]), identity))
    for identity in order:
        if not remaining:
            break
        sector = sectors[identity]
        if (
            scaled[identity] > units[identity]
            and units[identity] < position_cap
            and sector_units[sector] < sector_cap
        ):
            units[identity] += 1
            sector_units[sector] += 1
            remaining -= 1
    if remaining:
        raise ArithmeticError("Unable to serialize allocation while preserving constraints")
    return {identity: Fraction(value, scale) for identity, value in units.items()}


def allocate(
    candidates: Iterable[AllocationCandidate], policy: PortfolioConfig
) -> AllocationResult:
    policy = PortfolioConfig.model_validate(policy)
    rows = [AllocationCandidate.model_validate(row) for row in candidates]
    if len({row.asset_id for row in rows}) != len(rows):
        raise ValueError("Duplicate candidate asset_id")
    ranked = sorted(rows, key=lambda row: (-row.score, row.asset_id))
    exclusions = []
    selected: list[AllocationCandidate] = []
    for row in ranked:
        reason = (
            "INELIGIBLE"
            if not row.eligible
            else "ZERO_VOLATILITY"
            if row.volatility == 0
            else "OUTSIDE_TOP_N"
            if len(selected) >= policy.max_positions
            else None
        )
        if reason:
            exclusions.append(AllocationExclusion(asset_id=row.asset_id, reason=reason))
        else:
            selected.append(row)
    by_id = {row.asset_id: row for row in selected}
    identities = sorted(by_id)
    sectors = {identity: by_id[identity].sector for identity in identities}
    volatilities = {identity: Fraction(str(by_id[identity].volatility)) for identity in identities}
    smallest = min(volatilities.values(), default=Fraction(1))
    rates = {identity: smallest / volatility for identity, volatility in volatilities.items()}
    weights = dict.fromkeys(identities, Fraction(0))
    active = identities.copy()
    budget = 1 - Fraction(policy.min_cash_weight)
    position_cap = Fraction(policy.max_position_weight)
    sector_cap = Fraction(policy.max_sector_weight)
    while active and budget:
        sector_rates: dict[str, Fraction] = {}
        sector_totals = dict.fromkeys(sectors.values(), Fraction(0))
        for identity in identities:
            sector_totals[sectors[identity]] += weights[identity]
        for identity in active:
            sector = sectors[identity]
            sector_rates[sector] = sector_rates.get(sector, Fraction(0)) + rates[identity]
        step = min(
            [budget / sum((rates[identity] for identity in active), Fraction(0))]
            + [(position_cap - weights[identity]) / rates[identity] for identity in active]
            + [
                (sector_cap - sector_totals[sector]) / rate
                for sector, rate in sorted(sector_rates.items())
            ]
        )
        for identity in active:
            delta = step * rates[identity]
            weights[identity] += delta
            sector_totals[sectors[identity]] += delta
            budget -= delta
        active = [
            identity
            for identity in active
            if weights[identity] < position_cap and sector_totals[sectors[identity]] < sector_cap
        ]
    weights = _joint_decimal_weights(weights, sectors, policy)
    cash = 1 - sum(weights.values(), Fraction(0))
    targets = tuple(
        AllocationTarget(asset_id=identity, sector=sectors[identity], weight=finite_decimal(weight))
        for identity, weight in weights.items()
        if weight > 0
    )
    cash_text = finite_decimal(cash)
    risk = assess_targets(targets, cash_text, policy)
    if not risk.compliant:
        raise ArithmeticError("Allocation failed its independent risk policy check")
    reasons = []
    if not selected:
        reasons.append("EMPTY_ELIGIBLE_UNIVERSE")
    if Fraction(policy.min_cash_weight) == 1:
        reasons.append("CASH_FLOOR_FULL_CAPITAL")
    if budget > 0:
        reasons.append("UNALLOCATABLE_CAPACITY")
    return AllocationResult(
        selected_ids=tuple(row.asset_id for row in selected),
        targets=targets,
        cash_weight=cash_text,
        exclusions=tuple(sorted(exclusions, key=lambda row: row.asset_id)),
        reasons=tuple(reasons),
        risk=risk,
    )


def allocate_momentum(
    evaluation: MomentumEvaluation, config: StrategyConfigV1
) -> AllocatedMomentum:
    """Retain reproducibility and rejection evidence from the same pinned evaluation."""
    if evaluation.config_sha256 != config.config_hash():
        raise ValueError("Allocation config does not match momentum evaluation")
    candidates = tuple(
        AllocationCandidate(
            asset_id=row.asset_id,
            sector=row.sector,
            score=row.scoring.score,
            volatility=row.features.volatility,
            eligible=row.eligible and row.allocation_eligible,
        )
        for row in evaluation.candidates
        if row.features is not None and row.scoring is not None and row.sector is not None
    )
    result = allocate(candidates, config.portfolio)
    if result.selected_ids != evaluation.selected_ids:
        raise ValueError("Allocation selection disagrees with momentum evidence")
    return AllocatedMomentum(momentum=evaluation, allocation=result)
