"""Authorized intent and partial-result representation; posting is a later service."""

from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, StrictBool, model_validator

from backend.domain.types import (
    AssetId,
    Contract,
    Hash256,
    Quantity,
    Reason,
    SessionDate,
    UTCTimestamp,
)


class PaperOrderV1(Contract):
    id: UUID
    asset_id: AssetId
    side: Literal["BUY", "SELL"]
    requested_quantity: Quantity
    filled_quantity: Quantity
    pending_quantity: Quantity
    cancelled_or_skipped_quantity: Quantity
    earliest_fill_session: SessionDate
    status: Literal["pending", "partially_filled", "filled", "cancelled", "rejected"]
    terminal: StrictBool
    reason: Reason | None

    @model_validator(mode="after")
    def quantity_lifecycle(self) -> Self:
        requested = Decimal(self.requested_quantity)
        filled, pending, closed = map(
            Decimal,
            (self.filled_quantity, self.pending_quantity, self.cancelled_or_skipped_quantity),
        )
        if requested <= 0 or requested != filled + pending + closed:
            raise ValueError("Requested quantity must equal filled, pending and closed quantities")
        if self.terminal != (pending == 0):
            raise ValueError("Terminal order must have no pending quantity")
        if self.status == "filled" and (filled != requested or not self.terminal):
            raise ValueError("Filled order must be completely filled")
        if self.status == "partially_filled" and not 0 < filled < requested:
            raise ValueError("Partial fill must be positive and below requested quantity")
        if self.status in {"cancelled", "rejected"} and (filled != 0 or not self.terminal):
            raise ValueError("Unfilled terminal state cannot erase fills")
        if self.status == "pending" and (filled != 0 or self.terminal):
            raise ValueError("Pending order has no fills and remains active")
        if (closed > 0 or self.status == "pending") and self.reason is None:
            raise ValueError("Pending or closed remainder requires a reason")
        return self


class PaperOrderBatchV1(Contract):
    id: UUID
    portfolio_id: UUID
    recommendation_id: UUID
    approval_idempotency_key: UUID
    approved_revision: Annotated[int, Field(strict=True, ge=0)]
    approved_at: UTCTimestamp
    decision_cutoff_utc: UTCTimestamp
    snapshot_id: UUID
    calendar_version: Hash256
    execution_policy_id: Literal["us_eod_next_open_v1"]
    eligible_open_at: UTCTimestamp
    status: Literal["pending", "partially_filled", "filled", "cancelled", "rejected"]
    terminal: StrictBool
    orders: Annotated[tuple[PaperOrderV1, ...], Field(min_length=1)]
    reason: Reason | None

    @model_validator(mode="after")
    def batch_lifecycle(self) -> Self:
        if self.eligible_open_at <= max(self.approved_at, self.decision_cutoff_utc):
            raise ValueError("Eligible open must be strictly after approval and cutoff")
        if len({order.id for order in self.orders}) != len(self.orders):
            raise ValueError("Duplicate order ID")
        if self.terminal != all(order.terminal for order in self.orders):
            raise ValueError("Batch terminal state must match its orders")
        any_filled = any(Decimal(order.filled_quantity) > 0 for order in self.orders)
        all_filled = all(order.status == "filled" for order in self.orders)
        if self.status == "filled" and not all_filled:
            raise ValueError("Filled batch contains an incomplete order")
        if self.status == "partially_filled" and (not any_filled or all_filled):
            raise ValueError("Partial batch must contain some but not complete execution")
        if self.status in {"cancelled", "rejected", "pending"} and any_filled:
            raise ValueError("Batch state cannot hide posted fills")
        if self.status in {"cancelled", "rejected"} and (not self.terminal or self.reason is None):
            raise ValueError("Terminal unfilled batch requires a reason")
        if self.status == "pending" and self.terminal:
            raise ValueError("Pending batch cannot be terminal")
        return self
