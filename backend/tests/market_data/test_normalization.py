"""Authored SYNTHETIC_DATA_ONLY provider-shaped input, never live provider evidence."""

from datetime import UTC, datetime

import pytest

from backend.market_data.models import Calendar
from backend.market_data.providers.normalization import normalize_observation
from backend.market_data.providers.yahoo import ProviderFailure
from backend.tests.market_data.test_repository import ROOT

ROW: dict[str, object] = {
    "session_date": "2027-01-04",
    "Open": "100",
    "High": "101",
    "Low": "99",
    "Close": "100",
    "Adj Close": "50",
    "Volume": 1000,
    "Dividends": "1.25",
    "Stock Splits": "2",
}


def test_observed_chronology_unverified_bases_and_unresolved_payable() -> None:
    calendar = Calendar.model_validate_json((ROOT / "calendar.json").read_bytes())
    observed = datetime(2031, 1, 1, tzinfo=UTC)
    result = normalize_observation("TEST:AAA", ROW, observed, calendar)
    assert result.bar.available_at == result.bar.ingested_at == observed
    assert result.bar.published_at is None and result.bar.availability_basis == "observed"
    assert result.bar.price_basis == "provider_unverified"
    assert result.actions[0].ratio_numerator == "2"
    assert result.actions[1].per_share == "1.25"
    assert result.actions[1].payable_session is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("Close", float("nan")),
        ("Volume", -1),
        ("Volume", "0.5"),
        ("Dividends", None),
        ("Stock Splits", -2),
        ("session_date", "2027-01-03"),
    ],
)
def test_invalid_or_partial_observation_fails(field: str, value: object) -> None:
    calendar = Calendar.model_validate_json((ROOT / "calendar.json").read_bytes())
    with pytest.raises(ProviderFailure):
        normalize_observation(
            "TEST:AAA", {**ROW, field: value}, datetime(2031, 1, 1, tzinfo=UTC), calendar
        )
