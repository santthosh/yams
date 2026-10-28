"""Closed, hash-pinned operator evidence for optional research acquisition."""

from datetime import date
from typing import Annotated, Literal, Self

from pydantic import Field, StrictBool, model_validator

from backend.domain.market import AssetV1
from backend.domain.types import Contract, SessionDate
from backend.market_data.models import AssetContext, Calendar, Text
from backend.market_data.providers.yahoo import ResearchPermission


class ResearchConfig(Contract):
    schema_version: Literal[1]
    rights_verified_local_use: StrictBool
    rights_reference: Text
    directory_reference: Text
    directory_kind: Literal["nasdaqlisted", "otherlisted"]
    adapter_version: Literal["yfinance_1.7.0_normalization_1"]
    first_session: SessionDate
    last_session: SessionDate
    calendar: Calendar
    assets: Annotated[tuple[AssetV1, ...], Field(min_length=1, max_length=1000)]
    context: AssetContext
    # This is a broad venue rule, not a user-supplied ticker shortlist.
    exchange_codes: Annotated[tuple[Text, ...], Field(min_length=1)]
    selection_rule_reference: Text

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.first_session > self.last_session:
            raise ValueError("Research coverage bounds are reversed")
        days: set[date] = {row.session_date for row in self.calendar.sessions}
        if self.first_session not in days or self.last_session not in days:
            raise ValueError("Research endpoints must be pinned sessions")
        ids = [asset.asset_id for asset in self.assets]
        keys = [(asset.venue, asset.symbol) for asset in self.assets]
        if len(set(ids)) != len(ids) or len(set(keys)) != len(keys):
            raise ValueError("Research mappings must have unique identities")
        if any(asset.provider != "yahoo_yfinance" for asset in self.assets):
            raise ValueError("Research mappings must identify the configured provider")
        if any(row.asset_id not in ids for row in (*self.context.aliases, *self.context.sectors)):
            raise ValueError("Context references an unmapped asset")
        for asset in self.assets:
            if not any(
                alias.asset_id == asset.asset_id
                and alias.venue == asset.venue
                and alias.symbol == asset.symbol
                and alias.provider == asset.provider
                and alias.provider_id == asset.provider_id
                and alias.covers(self.last_session)
                for alias in self.context.aliases
            ):
                raise ValueError("Research identity requires matching effective alias evidence")
            if not any(
                row.asset_id == asset.asset_id and row.covers(self.last_session)
                for row in self.context.sectors
            ):
                raise ValueError("Research identity requires effective sector evidence")
        return self

    def permission(self) -> ResearchPermission:
        return ResearchPermission(
            self.rights_reference,
            self.directory_reference,
            self.adapter_version,
            self.rights_verified_local_use,
        )
