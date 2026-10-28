"""Conservative observed research rows; never backdate downloads or repair prices."""

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation

from pydantic import TypeAdapter, ValidationError

from backend.domain.market import MarketBarV1
from backend.domain.types import SessionDate, UTCTimestamp, canonical_json
from backend.market_data.models import Calendar, CorporateAction
from backend.market_data.providers.yahoo import ProviderFailure


def decimal_text(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ProviderFailure("PROVIDER_NUMERIC_VALUE_INVALID")
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        raise ProviderFailure("PROVIDER_NUMERIC_VALUE_INVALID") from None
    if not number.is_finite():
        raise ProviderFailure("PROVIDER_NUMERIC_VALUE_INVALID")
    return format(number, "f")


@dataclass(frozen=True)
class NormalizedObservation:
    bar: MarketBarV1
    actions: tuple[CorporateAction, ...]


def normalize_observation(
    asset_id: str, row: Mapping[str, object], observed_at: datetime, calendar: Calendar
) -> NormalizedObservation:
    """Require explicit action columns and a completed pinned calendar session.

    Yahoo observations remain provider_unverified: float inputs retain their exposed
    decimal representation, not a claim of original exchange tick precision. An
    ex-date is evidence of an announcement, never an invented dividend payable date.
    """
    observed_at = TypeAdapter(UTCTimestamp).validate_python(observed_at)
    try:
        day = TypeAdapter(SessionDate).validate_python(row.get("session_date"))
        session = next(item for item in calendar.sessions if item.session_date == day)
        if session.close_at > observed_at:
            raise ProviderFailure("PROVIDER_SESSION_INCOMPLETE")
        volume = Decimal(decimal_text(row.get("Volume")))
        if volume < 0 or volume != volume.to_integral_value():
            raise ProviderFailure("PROVIDER_VOLUME_INVALID")
        dividend = Decimal(decimal_text(row.get("Dividends")))
        split = Decimal(decimal_text(row.get("Stock Splits")))
        if dividend < 0 or split < 0:
            raise ProviderFailure("PROVIDER_ACTION_INVALID")
        bar = MarketBarV1.model_validate(
            {
                "schema_version": 1,
                "asset_id": asset_id,
                "session_date": day,
                "open": decimal_text(row.get("Open")),
                "high": decimal_text(row.get("High")),
                "low": decimal_text(row.get("Low")),
                "close": decimal_text(row.get("Close")),
                "adjusted_close": decimal_text(row.get("Adj Close")),
                "volume": int(volume),
                "currency": "USD",
                "provider": "yahoo_yfinance",
                "published_at": None,
                "available_at": observed_at,
                "ingested_at": observed_at,
                "availability_basis": "observed",
                "price_basis": "provider_unverified",
                "volume_basis": "provider_unverified",
                "quality_flags": ["RAW_PRICE_BASIS_UNVERIFIED", "ACTION_COVERAGE_UNVERIFIED"],
            }
        )
        actions = []
        for kind, amount in (("split", split), ("dividend", dividend)):
            if amount == 0:
                continue
            identity = hashlib.sha256(
                canonical_json(
                    {
                        "asset_id": asset_id,
                        "session": day.isoformat(),
                        "kind": kind,
                        "amount": format(amount, "f"),
                        "provider": "yahoo_yfinance",
                    }
                )
            ).hexdigest()
            actions.append(
                CorporateAction.model_validate(
                    {
                        "asset_id": asset_id,
                        "event_id": identity,
                        "kind": kind,
                        "effective_session": day,
                        "provider": "yahoo_yfinance",
                        "currency": "USD",
                        "available_at": observed_at,
                        "ingested_at": observed_at,
                        "ratio_numerator": format(amount, "f") if kind == "split" else None,
                        "ratio_denominator": "1" if kind == "split" else None,
                        "per_share": format(amount, "f") if kind == "dividend" else None,
                        "payable_session": None,
                    }
                )
            )
        return NormalizedObservation(bar, tuple(actions))
    except (StopIteration, ValidationError):
        raise ProviderFailure("PROVIDER_ROW_INVALID") from None
