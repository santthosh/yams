from datetime import UTC, datetime

import pytest
from pydantic import TypeAdapter, ValidationError

from backend.domain.types import FiniteNumber, Money, Quantity, SessionDate, UTCTimestamp, Weight


@pytest.mark.parametrize("value", [0.1, 1, True, "NaN", "1e2", "01", "1.001", "-1", " 1"])
def test_money_does_not_coerce_or_round(value: object) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(Money).validate_python(value)


def test_money_roundtrip_exceeds_ieee754_safe_integer() -> None:
    adapter = TypeAdapter(Money)
    value = "9007199254740993.01"
    assert (
        adapter.dump_json(adapter.validate_json('"' + value + '"')) == ('"' + value + '"').encode()
    )


def test_quantity_scale_and_weight_bounds() -> None:
    assert TypeAdapter(Quantity).validate_python("0.999000") == "0.999000"
    for value in ("0.0000001", "-0.1", 1.25):
        with pytest.raises(ValidationError):
            TypeAdapter(Quantity).validate_python(value)
    with pytest.raises(ValidationError):
        TypeAdapter(Weight).validate_python("1.000001")


@pytest.mark.parametrize("value", ["0.1", True, float("nan"), float("inf"), float("-inf")])
def test_statistics_are_finite_json_numbers(value: object) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(FiniteNumber).validate_python(value)


def test_utc_timestamp_and_session_date_are_distinct() -> None:
    adapter = TypeAdapter(UTCTimestamp)
    value = adapter.validate_python("2026-10-27T12:34:56Z")
    assert value == datetime(2026, 10, 27, 12, 34, 56, tzinfo=UTC)
    assert adapter.dump_json(value) == b'"2026-10-27T12:34:56Z"'
    for invalid in ("2026-10-27T12:34:56", "2026-10-27T12:34:56+00:00", 1234):
        with pytest.raises(ValidationError):
            adapter.validate_python(invalid)
    with pytest.raises(ValidationError):
        TypeAdapter(SessionDate).validate_python(value)
