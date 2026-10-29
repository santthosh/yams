"""Independent posted quantity × coherent raw close + cash valuation checks."""

from decimal import Decimal
from fractions import Fraction

import pytest

from backend.portfolio.valuation import value_close_at
from backend.tests.portfolio.test_execution import at, bar, calendar, market, state


def test_last_pinned_close_does_not_need_a_future_trade_session() -> None:
    result = value_close_at(
        state("799.80", "2.000000", "200.20"),
        calendar(),
        market(bar(day=15, price="110.25")),
        session_date=at(15).date(),
        cutoff=at(15),
        live=True,
    )
    assert result.values == {"A": Fraction(Decimal("220.50"))}
    assert result.nav == Fraction(Decimal("1020.30"))
    assert result.money_value() == "1020.30" and result.missing_assets == ()


def test_missing_future_or_uningested_mark_cannot_be_substituted() -> None:
    held = state("799.80", "2.000000", "200.20")
    original = bar(day=15)
    for evidence in (
        market(),
        market(original.model_copy(update={"available_at": at(15, 22)})),
        market(original.model_copy(update={"ingested_at": at(15, 22)})),
    ):
        result = value_close_at(
            held, calendar(), evidence, session_date=at(15).date(), cutoff=at(15), live=True
        )
        assert result.nav is None and result.money_value() is None
        assert result.missing_assets == ("A",)
    stale = value_close_at(
        held,
        calendar(),
        market(original, freshness="stale"),
        session_date=at(15).date(),
        cutoff=at(15),
        live=True,
    )
    assert stale.nav is None
    historical = value_close_at(
        held,
        calendar(),
        market(original.model_copy(update={"ingested_at": at(15, 22)})),
        session_date=at(15).date(),
        cutoff=at(15),
        live=False,
    )
    assert historical.money_value() == "999.80"
    with pytest.raises(ValueError, match="completed"):
        value_close_at(
            held,
            calendar(),
            market(original),
            session_date=at(15).date(),
            cutoff=at(15, 20),
            live=True,
        )
