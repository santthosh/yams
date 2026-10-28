"""Exact target-policy diagnostics, independent of prices and order sizing."""

from fractions import Fraction
from typing import Annotated

from pydantic import Field, TypeAdapter

from backend.domain.strategy import PortfolioConfig
from backend.domain.types import AssetId, Contract, FractionString, Reason


class AllocationTarget(Contract):
    asset_id: AssetId
    sector: Annotated[str, Field(strict=True, min_length=1)]
    weight: FractionString


class SectorRisk(Contract):
    sector: str
    weight: FractionString
    at_cap: bool


class RiskReport(Contract):
    compliant: bool
    violations: tuple[Reason, ...]
    position_count: int
    max_position_weight: FractionString
    max_sector_weight: FractionString
    invested_weight: FractionString
    cash_weight: FractionString
    unmet_investable_weight: FractionString
    position_limit: FractionString
    sector_limit: FractionString
    cash_floor: FractionString
    capped_positions: tuple[AssetId, ...]
    sectors: tuple[SectorRisk, ...]


def finite_decimal(value: Fraction) -> str:
    """Exact plain text for terminating base-ten fractions; no ambient Decimal context."""
    denominator = value.denominator
    twos = fives = 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    if denominator != 1 or value < 0:
        raise ValueError("Expected a nonnegative terminating decimal")
    places = max(twos, fives)
    units = value.numerator * 2 ** (places - twos) * 5 ** (places - fives)
    if not places:
        return str(units)
    digits = str(units).zfill(places + 1)
    return (digits[:-places] + "." + digits[-places:]).rstrip("0").rstrip(".")


def assess_targets(
    targets: tuple[AllocationTarget, ...], cash_weight: FractionString, policy: PortfolioConfig
) -> RiskReport:
    """Report exact concentration/cap violations; never repair an invalid target."""
    # Validate even direct Python calls; type annotations alone do not enforce scalars.
    targets = tuple(AllocationTarget.model_validate(row) for row in targets)
    cash = Fraction(TypeAdapter(FractionString).validate_python(cash_weight))
    policy = PortfolioConfig.model_validate(policy)
    position_cap = Fraction(policy.max_position_weight)
    sector_cap = Fraction(policy.max_sector_weight)
    floor = Fraction(policy.min_cash_weight)
    sectors: dict[str, Fraction] = {}
    weights = [Fraction(row.weight) for row in targets]
    for row, weight in zip(targets, weights, strict=True):
        sectors[row.sector] = sectors.get(row.sector, Fraction(0)) + weight
    invested = sum(weights, Fraction(0))
    violations = []
    if len({row.asset_id for row in targets}) != len(targets):
        violations.append("DUPLICATE_ASSET")
    if sum(weight > 0 for weight in weights) > policy.max_positions:
        violations.append("POSITION_COUNT_LIMIT")
    if any(weight > position_cap for weight in weights):
        violations.append("POSITION_CAP")
    if any(weight > sector_cap for weight in sectors.values()):
        violations.append("SECTOR_CAP")
    if cash < floor:
        violations.append("CASH_FLOOR")
    if invested + cash != 1:
        violations.append("INCOMPLETE_ALLOCATION")
    # Aggregates may exceed one for invalid external targets. Reject such transport
    # rather than constructing an invalid bounded report or hiding the violation.
    if invested > 1 or any(weight > 1 for weight in sectors.values()):
        raise ValueError("Target allocation exceeds full capital")
    return RiskReport(
        compliant=not violations,
        violations=tuple(violations),
        position_count=sum(weight > 0 for weight in weights),
        max_position_weight=finite_decimal(max(weights, default=Fraction(0))),
        max_sector_weight=finite_decimal(max(sectors.values(), default=Fraction(0))),
        invested_weight=finite_decimal(invested),
        cash_weight=finite_decimal(cash),
        unmet_investable_weight=finite_decimal(max(Fraction(0), cash - floor)),
        position_limit=policy.max_position_weight,
        sector_limit=policy.max_sector_weight,
        cash_floor=policy.min_cash_weight,
        capped_positions=tuple(
            sorted(row.asset_id for row in targets if Fraction(row.weight) == position_cap)
        ),
        sectors=tuple(
            SectorRisk(sector=sector, weight=finite_decimal(weight), at_cap=weight == sector_cap)
            for sector, weight in sorted(sectors.items())
        ),
    )
