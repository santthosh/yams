"""Shared exact close valuation for planning and historical reporting."""

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction

from backend.domain.market import MarketBarV1
from backend.market_data.models import Calendar
from backend.portfolio.execution import (
    ExecutionContext,
    MarketEvidence,
    PortfolioState,
    arithmetic,
    money,
    usable_bar,
    verify_context,
)


@dataclass(frozen=True)
class CloseValuation:
    marks: dict[str, MarketBarV1]
    values: dict[str, Fraction]
    nav: Fraction | None
    missing_assets: tuple[str, ...]

    def money_value(self) -> str | None:
        if self.nav is None:
            return None
        with arithmetic(str(self.nav.numerator), str(self.nav.denominator)):
            return money(Decimal(self.nav.numerator) / Decimal(self.nav.denominator))


def value_close(
    state: PortfolioState,
    context: ExecutionContext,
    calendar: Calendar,
    marks: MarketEvidence,
    *,
    required_assets: tuple[str, ...] = (),
) -> CloseValuation:
    verify_context(context, calendar, marks)
    positions = {row.asset_id: row for row in state.positions if Decimal(row.quantity) > 0}
    close = next(
        s.close_at for s in calendar.sessions if s.session_date == context.decision_session
    )
    valid = {
        bar.asset_id: bar
        for bar in marks.bars
        if bar.session_date == context.decision_session
        and usable_bar(bar, context.decision_cutoff, context)
        and bar.available_at >= close
    }
    missing = tuple(sorted((positions.keys() | set(required_assets)) - valid.keys()))
    if (
        missing
        or marks.freshness == "blocked"
        or (context.execution_mode == "current_paper" and marks.freshness == "stale")
    ):
        return CloseValuation(valid, {}, None, missing)
    values = {
        identity: Fraction(row.quantity) * Fraction(valid[identity].close)
        for identity, row in positions.items()
    }
    return CloseValuation(
        valid, values, Fraction(state.cash_usd) + sum(values.values(), Fraction(0)), ()
    )
