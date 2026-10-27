"""Strict wire scalars. Financial decimals stay strings until domain arithmetic."""

import json
import math
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    StringConstraints,
    WithJsonSchema,
    field_validator,
)


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    @field_validator("schema_version", mode="before", check_fields=False)
    @classmethod
    def strict_schema_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("schema_version must be an integer")
        return value


def _decimal(value: str) -> str:
    if not Decimal(value).is_finite():
        raise ValueError("Decimal must be finite")
    return value


def _weight(value: str) -> str:
    if not Decimal(0) <= Decimal(value) <= Decimal(1):
        raise ValueError("Weight must be between zero and one")
    return value


def _positive(value: str) -> str:
    if Decimal(value) <= 0:
        raise ValueError("Value must be positive")
    return value


DecimalString = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^(0|[1-9][0-9]*)(\.[0-9]+)?$"),
    AfterValidator(_decimal),
]
Money = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^(0|[1-9][0-9]{0,21})(\.[0-9]{1,2})?$"),
]
SignedMoney = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^-?(0|[1-9][0-9]{0,21})(\.[0-9]{1,2})?$"),
]
Price = Annotated[DecimalString, AfterValidator(_positive)]
Quantity = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^(0|[1-9][0-9]{0,23})(\.[0-9]{1,6})?$"),
]
Weight = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^(0|1)(\.[0-9]{1,6})?$"),
    AfterValidator(_weight),
]
PositiveWeight = Annotated[Weight, AfterValidator(_positive)]
FractionString = Annotated[DecimalString, AfterValidator(_weight)]
Hash256 = Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$")]
AssetId = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=160)]
Reason = Annotated[str, StringConstraints(strict=True, pattern=r"^[A-Z][A-Z0-9_]*$")]
NonnegativeInt = Annotated[int, Field(strict=True, ge=0)]
SourceMode = Literal["synthetic_fixture", "research_market_data"]


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float | Decimal):
        raise ValueError("Expected a JSON number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Expected a finite number")
    return result


FiniteNumber = Annotated[float, BeforeValidator(_number), Field(allow_inf_nan=False)]


def _utc_input(value: object) -> object:
    if isinstance(value, str) and not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?Z", value
    ):
        raise ValueError("Timestamp must be RFC3339 UTC Z")
    if not isinstance(value, str | datetime):
        raise ValueError("Timestamp must be a UTC timestamp")
    return value


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("Timestamp must be timezone-aware UTC")
    return value


UTCTimestamp = Annotated[
    datetime,
    BeforeValidator(_utc_input),
    AfterValidator(_utc),
    PlainSerializer(lambda value: value.isoformat().replace("+00:00", "Z"), return_type=str),
    WithJsonSchema({"type": "string", "format": "date-time", "pattern": "Z$"}),
]


def _date_input(value: object) -> object:
    if isinstance(value, datetime):
        raise ValueError("Session date cannot be a timestamp")
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("Expected YYYY-MM-DD")
    return value


SessionDate = Annotated[date, BeforeValidator(_date_input)]


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> object:
    raise ValueError(f"Nonfinite JSON token: {value}")


def load_json(data: str | bytes) -> object:
    """Transport entrypoint: preserve numeric precision and reject duplicate keys."""
    return json.loads(
        data,
        object_pairs_hook=_unique_object,
        parse_float=Decimal,
        parse_constant=_invalid_constant,
    )


def decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError("Cannot canonicalize nonfinite Decimal")
    if value == 0:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _quote(value: str) -> str:
    pieces = ['"']
    for char in value:
        code = ord(char)
        if 0xD800 <= code <= 0xDFFF:
            raise ValueError("Invalid Unicode scalar")
        if char in ('"', "\\"):
            pieces.append("\\" + char)
        elif code < 32:
            pieces.append(f"\\u{code:04x}")
        else:
            pieces.append(char)
    return "".join(pieces) + '"'


def canonical_json(value: object) -> bytes:
    """ADR-003 bytes; arrays preserve order (ADR-006/007 extension)."""
    if value is None:
        text = "null"
    elif isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, str):
        text = _quote(value)
    elif isinstance(value, int):
        text = str(value)
    elif isinstance(value, Decimal):
        text = decimal_text(value)
    elif isinstance(value, float):
        raise ValueError("Canonical numbers must be exact Decimal or integer, not binary float")
    elif isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("Canonical object keys must be strings")
        text = (
            "{"
            + ",".join(
                _quote(key) + ":" + canonical_json(value[key]).decode("utf-8")
                for key in sorted(value)
            )
            + "}"
        )
    elif isinstance(value, list | tuple):
        text = "[" + ",".join(canonical_json(item).decode("utf-8") for item in value) + "]"
    else:
        raise ValueError(f"Unsupported canonical value: {type(value).__name__}")
    return text.encode("utf-8")
