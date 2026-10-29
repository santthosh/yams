"""Paper account transport; posted holdings remain distinct from recommendations."""

import unicodedata
from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    AfterValidator,
    Field,
    StrictBool,
    StrictStr,
    StringConstraints,
    model_validator,
)

from backend.domain.common import Page
from backend.domain.strategy import PortfolioConfig
from backend.domain.types import (
    AssetId,
    Contract,
    FractionString,
    Hash256,
    Money,
    Price,
    Quantity,
    Reason,
    SessionDate,
    SignedMoney,
    SourceMode,
    UTCTimestamp,
)


def portfolio_name(value: str) -> str:
    value = value.strip()
    if not 1 <= len(value) <= 120 or any(
        unicodedata.category(char) in {"Cc", "Cs"} for char in value
    ):
        raise ValueError("Portfolio name must contain 1–120 characters without controls")
    return value


def positive_capital(value: str) -> str:
    if Decimal(value) <= 0:
        raise ValueError("Opening paper capital must be positive")
    return value


PortfolioName = Annotated[StrictStr, AfterValidator(portfolio_name)]
SignedQuantity = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^-?(0|[1-9][0-9]{0,23})(\.[0-9]{1,6})?$"),
]


class PortfolioCreateRequest(Contract):
    name: PortfolioName
    strategy_version_id: UUID
    opening_cash_usd: Annotated[Money, AfterValidator(positive_capital)] = "1000.00"
    mode: SourceMode = "synthetic_fixture"
    snapshot_id: UUID | None = None


class PortfolioHoldingV1(Contract):
    asset_id: AssetId
    sector: StrictStr
    quantity: Quantity
    total_basis_usd: Money
    mark_price_usd: Price | None
    price_as_of_session: SessionDate | None
    market_value_usd: Money | None
    weight: FractionString | None
    reason: Reason | None

    @model_validator(mode="after")
    def truthful_missing_mark(self) -> Self:
        if Decimal(self.quantity) <= 0:
            raise ValueError("Holdings include positive posted shares only")
        if self.mark_price_usd is None and (
            self.market_value_usd is not None or self.weight is not None
        ):
            raise ValueError("Missing prices cannot produce a holding value or weight")
        if (
            self.mark_price_usd is None or self.market_value_usd is None or self.weight is None
        ) and self.reason is None:
            raise ValueError("Unavailable holding values require a reason")
        return self


class PortfolioValuationV1(Contract):
    status: Literal["available", "stale", "unavailable"]
    total_value_usd: Money | None
    cash_weight: FractionString | None
    snapshot_id: UUID | None
    snapshot_sha256: Hash256 | None
    as_of_session: SessionDate | None
    checked_at: UTCTimestamp
    reason: Reason | None
    missing_assets: tuple[AssetId, ...]
    warnings: tuple[Reason, ...]

    @model_validator(mode="after")
    def availability(self) -> Self:
        if (self.snapshot_id is None) != (self.snapshot_sha256 is None):
            raise ValueError("Snapshot identity and hash are paired")
        if self.status == "available" and self.total_value_usd is None:
            raise ValueError("Available valuation requires a value")
        if self.cash_weight is None and self.reason is None:
            raise ValueError("Unavailable cash weight requires a reason")
        if self.status != "available" and self.reason is None:
            raise ValueError("Stale/unavailable valuation requires a reason")
        if self.status == "unavailable" and (
            self.total_value_usd is not None or self.cash_weight is not None
        ):
            raise ValueError("Unavailable total must not substitute a value or weight")
        if self.status == "available" and self.missing_assets:
            raise ValueError("Available total cannot omit held assets")
        if (self.snapshot_id is None or self.as_of_session is None) and self.reason is None:
            raise ValueError("Absent market context requires an explicit reason")
        return self


class PaperPortfolioV1(Contract):
    id: UUID
    name: PortfolioName
    currency: Literal["USD"] = "USD"
    paper_only: Literal[True] = True
    valuation_mode: SourceMode
    total_value_usd: Money | None
    valuation_as_of_session: SessionDate | None
    strategy_version_id: UUID
    opening_cash_usd: Money
    opening_snapshot_id: UUID | None
    cash_usd: Money
    revision: Annotated[int, Field(strict=True, ge=1)]
    last_sequence: Annotated[int, Field(strict=True, ge=1)]
    state: Literal["active", "paused", "closed"]
    reconciliation_failed: StrictBool
    benchmark_symbol: Literal["SPY"] = "SPY"
    execution_policy_id: Literal["us_eod_next_open_v1"] = "us_eod_next_open_v1"
    risk_policy: PortfolioConfig
    created_at: UTCTimestamp
    holdings: tuple[PortfolioHoldingV1, ...]
    valuation: PortfolioValuationV1

    @model_validator(mode="after")
    def matching_valuation(self) -> Self:
        if (
            self.total_value_usd != self.valuation.total_value_usd
            or self.valuation_as_of_session != self.valuation.as_of_session
        ):
            raise ValueError("Portfolio summary and valuation evidence must agree")
        for holding in self.holdings:
            if (
                holding.mark_price_usd is not None
                and holding.price_as_of_session != self.valuation_as_of_session
            ):
                raise ValueError("Holding marks must share the portfolio valuation session")
        return self


class PortfolioPositionChangeV1(Contract):
    asset_id: AssetId
    quantity_delta: SignedQuantity
    total_basis_delta_usd: SignedMoney


class PortfolioFillV1(Contract):
    id: UUID
    order_id: UUID
    execution_session: SessionDate
    raw_price_usd: Price
    executed_price_usd: Price
    quantity: Quantity
    gross_usd: Money
    commission_usd: Money
    slippage_usd: Money
    removed_basis_usd: Money
    realized_pnl_usd: SignedMoney


class PortfolioTransactionV1(Contract):
    id: UUID
    sequence: Annotated[int, Field(strict=True, ge=1)]
    portfolio_revision: Annotated[int, Field(strict=True, ge=1)]
    kind: Literal[
        "opening_funding",
        "fill",
        "order_closed",
        "split",
        "dividend",
        "entitlement",
        "correction",
        "strategy_binding",
        "batch_approval",
        "batch_cancel",
    ]
    event_key: StrictStr
    recorded_at: UTCTimestamp
    effective_at: UTCTimestamp
    strategy_version_id: UUID
    snapshot_id: UUID | None
    cash_delta_usd: SignedMoney
    position_changes: tuple[PortfolioPositionChangeV1, ...]
    correction_target_id: UUID | None
    fill: PortfolioFillV1 | None

    @model_validator(mode="after")
    def event_shape(self) -> Self:
        if (self.kind == "fill") != (self.fill is not None):
            raise ValueError("Only fill events contain a posted fill")
        if (self.kind == "correction") != (self.correction_target_id is not None):
            raise ValueError("Correction events require target lineage")
        return self


class PortfolioTransactionPageV1(Page[PortfolioTransactionV1]):
    warnings: tuple[Reason, ...] = ()
    portfolio_id: UUID
    mode: SourceMode
    paper_only: Literal[True] = True
