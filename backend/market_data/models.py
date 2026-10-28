"""Internal temporal evidence contracts; transport AssetV1 stays unchanged."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, StringConstraints, model_validator

from backend.domain.types import AssetId, Contract, DecimalString, Price, SessionDate, UTCTimestamp

Text = Annotated[str, StringConstraints(strict=True, min_length=1)]


def finite_decimal(value: str) -> str:
    if not Decimal(value).is_finite():
        raise ValueError("Expected a finite decimal")
    return value


SignedDecimal = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^-?(0|[1-9][0-9]*)(\.[0-9]+)?$"),
    AfterValidator(finite_decimal),
]


class Evidence(Contract):
    asset_id: AssetId
    available_at: UTCTimestamp
    ingested_at: UTCTimestamp

    def visible(self, cutoff: datetime, live: bool) -> bool:
        return self.available_at <= cutoff and (not live or self.ingested_at <= cutoff)


class Interval(Evidence):
    effective_from: SessionDate
    effective_to_exclusive: SessionDate | None

    @model_validator(mode="after")
    def nonempty(self) -> Self:
        if (
            self.effective_to_exclusive is not None
            and self.effective_to_exclusive <= self.effective_from
        ):
            raise ValueError("Effective interval must be nonempty and half-open")
        return self

    def covers(self, session: date) -> bool:
        return self.effective_from <= session and (
            self.effective_to_exclusive is None or session < self.effective_to_exclusive
        )


class Membership(Interval):
    timing_status: Literal["synthetic_known", "point_in_time", "current_only", "unknown"]


class Universe(Contract):
    schema_version: Literal[1]
    label: Text
    rule: Text
    source_sha256: Text
    memberships: tuple[Membership, ...]


class Alias(Interval):
    venue: Annotated[str, StringConstraints(strict=True, pattern=r"^[A-Z0-9]{4}$")]
    symbol: Text
    provider: Text
    provider_id: Text


class Sector(Interval):
    sector: Text
    provider: Text


class Fundamental(Evidence):
    metric: Text
    period_end: SessionDate
    value: SignedDecimal
    provider: Text


class AssetContext(Contract):
    schema_version: Literal[2]
    aliases: tuple[Alias, ...]
    sectors: tuple[Sector, ...]
    fundamentals: tuple[Fundamental, ...]


class Session(Contract):
    session_date: SessionDate
    open_at: UTCTimestamp
    close_at: UTCTimestamp

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.open_at >= self.close_at:
            raise ValueError("Session open must precede close")
        return self


class Calendar(Contract):
    schema_version: Literal[1]
    label: Text
    id: Text
    timezone: Literal["America/New_York"]
    generator_version: Text
    timezone_rules_version: Text
    limitations: tuple[Text, ...]
    sessions: tuple[Session, ...]

    @model_validator(mode="after")
    def ordered(self) -> Self:
        days = tuple(row.session_date for row in self.sessions)
        if days != tuple(sorted(set(days))):
            raise ValueError("Calendar sessions must be unique and sorted")
        return self


class CorporateAction(Evidence):
    event_id: Text
    kind: Literal["split", "dividend"]
    effective_session: SessionDate
    provider: Text
    currency: Literal["USD"]
    ratio_numerator: Price | None
    ratio_denominator: Price | None
    per_share: DecimalString | None
    payable_session: SessionDate | None

    @model_validator(mode="after")
    def action_fields(self) -> Self:
        if self.kind == "split":
            if self.ratio_numerator is None or self.ratio_denominator is None:
                raise ValueError("Split requires an evidenced positive ratio")
            if self.per_share is not None or self.payable_session is not None:
                raise ValueError("Split cannot contain dividend fields")
        else:
            if self.per_share is None:
                raise ValueError("Dividend requires a declared amount")
            if self.ratio_numerator is not None or self.ratio_denominator is not None:
                raise ValueError("Dividend cannot contain split fields")
            if self.payable_session is not None and self.payable_session < self.effective_session:
                raise ValueError("Payable session cannot precede ex-session")
        return self
