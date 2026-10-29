"""Financial wire boundaries: strict decimal strings and honest unavailable values."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.domain.portfolio import (
    PortfolioCreateRequest,
    PortfolioHoldingV1,
    PortfolioValuationV1,
)


def test_creation_defaults_are_cash_only_fixture_mode_and_closed_input() -> None:
    request = PortfolioCreateRequest(
        name="  Independent paper account  ", strategy_version_id=uuid4()
    )
    assert request.name == "Independent paper account"
    assert request.opening_cash_usd == "1000.00"
    assert request.mode == "synthetic_fixture" and request.snapshot_id is None
    with pytest.raises(ValidationError):
        PortfolioCreateRequest.model_validate(request.model_dump() | {"asset_id": "invented"})


@pytest.mark.parametrize(
    "capital",
    [0, 1000.0, True, "0.00", "-1.00", "1.001", "NaN", "Infinity", "10000000000000000000000"],
)
def test_creation_rejects_non_decimal_or_invalid_capital(capital: object) -> None:
    with pytest.raises(ValidationError):
        PortfolioCreateRequest.model_validate(
            {"name": "paper", "strategy_version_id": uuid4(), "opening_cash_usd": capital}
        )


def test_missing_prices_require_reason_and_cannot_be_zero_substitutes() -> None:
    values = dict(
        asset_id="SYN:AAA",
        sector="Unknown",
        quantity="2.000000",
        total_basis_usd="200.20",
        mark_price_usd=None,
        price_as_of_session=None,
        market_value_usd=None,
        weight=None,
        reason=None,
    )
    with pytest.raises(ValidationError):
        PortfolioHoldingV1.model_validate(values)
    holding = PortfolioHoldingV1.model_validate(values | {"reason": "PRICE_UNAVAILABLE"})
    assert holding.market_value_usd is None and holding.weight is None
    with pytest.raises(ValidationError):
        PortfolioHoldingV1.model_validate(
            values | {"quantity": "0.000000", "reason": "PRICE_UNAVAILABLE"}
        )


def test_unavailable_nav_is_explicit_and_snapshot_hashes_are_paired() -> None:
    values = dict(
        status="unavailable",
        total_value_usd=None,
        cash_weight=None,
        snapshot_id=None,
        snapshot_sha256=None,
        as_of_session=None,
        checked_at=datetime.now(UTC),
        reason="PRICE_UNAVAILABLE",
        missing_assets=("SYN:AAA",),
        warnings=(),
    )
    assert PortfolioValuationV1.model_validate(values).total_value_usd is None
    with pytest.raises(ValidationError):
        PortfolioValuationV1.model_validate(values | {"total_value_usd": "0.00"})
    with pytest.raises(ValidationError):
        PortfolioValuationV1.model_validate(values | {"reason": None})
    with pytest.raises(ValidationError):
        PortfolioValuationV1.model_validate(values | {"snapshot_id": uuid4()})
