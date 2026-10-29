"""Shared exact close valuation for planning and historical reporting."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from fractions import Fraction

from pydantic import TypeAdapter

from backend.domain.market import MarketBarV1
from backend.domain.types import SessionDate, UTCTimestamp
from backend.market_data.models import Calendar
from backend.portfolio.execution import (
    ExecutionContext,
    MarketEvidence,
    PortfolioState,
    arithmetic,
    money,
    usable_evidence_bar,
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
    return value_close_at(
        state,
        calendar,
        marks,
        session_date=context.decision_session,
        cutoff=context.decision_cutoff,
        live=context.execution_mode == "current_paper",
        required_assets=required_assets,
    )


def value_close_at(
    state: PortfolioState,
    calendar: Calendar,
    marks: MarketEvidence,
    *,
    session_date: date,
    cutoff: datetime,
    live: bool,
    required_assets: tuple[str, ...] = (),
) -> CloseValuation:
    """Read-only valuation needs a completed close, not a future execution open.

    Callers bind the market/calendar to their verified snapshot. This function
    shares exact mark arithmetic and evidence guards with the trading consumer.
    """
    cutoff = TypeAdapter(UTCTimestamp).validate_python(cutoff)
    session_date = TypeAdapter(SessionDate).validate_python(session_date)
    scheduled = next((s for s in calendar.sessions if s.session_date == session_date), None)
    if scheduled is None or scheduled.close_at > cutoff:
        raise ValueError("Valuation requires a completed pinned calendar session")
    positions = {row.asset_id: row for row in state.positions if Decimal(row.quantity) > 0}
    close = scheduled.close_at
    valid = {
        bar.asset_id: bar
        for bar in marks.bars
        if bar.session_date == session_date
        and usable_evidence_bar(bar, cutoff, live=live)
        and bar.available_at >= close
    }
    missing = tuple(sorted((positions.keys() | set(required_assets)) - valid.keys()))
    if missing or marks.freshness == "blocked" or (live and marks.freshness == "stale"):
        return CloseValuation(valid, {}, None, missing)
    values = {
        identity: Fraction(row.quantity) * Fraction(valid[identity].close)
        for identity, row in positions.items()
    }
    return CloseValuation(
        valid, values, Fraction(state.cash_usd) + sum(values.values(), Fraction(0)), ()
    )
