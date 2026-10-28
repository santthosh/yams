"""Observed Tiingo diagnostics; raw share liquidity never uses adjusted volume."""

import hashlib
from collections.abc import Mapping
from datetime import datetime, timedelta
from decimal import Decimal
from fractions import Fraction

from pydantic import TypeAdapter, ValidationError

from backend.domain.market import MarketBarV1
from backend.domain.types import UTCTimestamp, canonical_json, decimal_text
from backend.market_data.models import Calendar, CorporateAction
from backend.market_data.providers.normalization import NormalizedObservation
from backend.market_data.providers.normalization import decimal_text as source_number
from backend.market_data.providers.yahoo import ProviderFailure


def normalize_tiingo(
    asset_id: str, row: Mapping[str, object], observed_at: datetime, calendar: Calendar
) -> NormalizedObservation:
    observed_at = TypeAdapter(UTCTimestamp).validate_python(observed_at)
    try:
        represented = row.get("date")
        if not isinstance(represented, str):
            raise ValueError("Missing source session")
        stamp = datetime.fromisoformat(represented)
        if (
            stamp.tzinfo is None
            or stamp.utcoffset() != timedelta(0)
            or (stamp.hour, stamp.minute, stamp.second, stamp.microsecond) != (0, 0, 0, 0)
        ):
            raise ValueError("Unsupported represented session label")
        day = stamp.date()
        scheduled = next(item for item in calendar.sessions if item.session_date == day)
        if scheduled.close_at > observed_at:
            raise ProviderFailure("PROVIDER_SESSION_INCOMPLETE")
        volume = Decimal(source_number(row.get("volume")))
        dividend = Decimal(source_number(row.get("divCash")))
        split = Decimal(source_number(row.get("splitFactor")))
        if volume < 0 or volume != volume.to_integral_value():
            raise ProviderFailure("PROVIDER_VOLUME_INVALID")
        if dividend < 0 or split <= 0:
            raise ProviderFailure("PROVIDER_ACTION_INVALID")
        bar = MarketBarV1.model_validate(
            {
                "schema_version": 1,
                "asset_id": asset_id,
                "session_date": day,
                "open": source_number(row.get("open")),
                "high": source_number(row.get("high")),
                "low": source_number(row.get("low")),
                "close": source_number(row.get("close")),
                "adjusted_close": source_number(row.get("adjClose")),
                "volume": int(volume),
                "currency": "USD",
                "provider": "tiingo_eod",
                "published_at": None,
                "available_at": observed_at,
                "ingested_at": observed_at,
                "availability_basis": "observed",
                "price_basis": "raw_as_traded",
                "volume_basis": "raw_shares_v1",
                "quality_flags": ["ACTION_ACCOUNTING_UNSUPPORTED"],
            }
        )
        actions = []
        for kind, amount in (("split", split), ("dividend", dividend)):
            if (kind == "split" and amount == 1) or (kind == "dividend" and amount == 0):
                continue
            identity = hashlib.sha256(
                canonical_json(
                    {
                        "asset_id": asset_id,
                        "session": day.isoformat(),
                        "kind": kind,
                        "amount": amount,
                        "provider": "tiingo_eod",
                    }
                )
            ).hexdigest()
            ratio = Fraction(amount)
            actions.append(
                CorporateAction.model_validate(
                    {
                        "asset_id": asset_id,
                        "event_id": identity,
                        "kind": kind,
                        "effective_session": day,
                        "provider": "tiingo_eod",
                        "currency": "USD",
                        "ratio_numerator": str(ratio.numerator) if kind == "split" else None,
                        "ratio_denominator": str(ratio.denominator) if kind == "split" else None,
                        "per_share": decimal_text(amount) if kind == "dividend" else None,
                        "payable_session": None,
                        "available_at": observed_at,
                        "ingested_at": observed_at,
                    }
                )
            )
        return NormalizedObservation(bar, tuple(actions))
    except ProviderFailure:
        raise
    except (ValueError, StopIteration, ValidationError):
        raise ProviderFailure("PROVIDER_ROW_INVALID") from None
