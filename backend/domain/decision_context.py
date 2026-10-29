"""Readonly UI composition; suggestions and indicative sessions authorize nothing."""

from typing import Literal
from uuid import UUID

from backend.domain.types import Contract, Reason, SessionDate, SourceMode, UTCTimestamp


class DecisionInputsV1(Contract):
    portfolio_id: UUID
    data_status: SourceMode
    snapshot_id: UUID | None
    clock_at: UTCTimestamp
    suggested_session: SessionDate | None
    suggested_cutoff_utc: UTCTimestamp | None
    unavailable_reason: Reason | None
    selection_policy: Literal["EARLIEST_PINNED_HISTORY_AND_HORIZON"] = (
        "EARLIEST_PINNED_HISTORY_AND_HORIZON"
    )
    limitation: Literal["CALENDAR_SUPPORT_NOT_PRICE_COMPLETENESS"] = (
        "CALENDAR_SUPPORT_NOT_PRICE_COMPLETENESS"
    )


class ApprovalPreviewV1(Contract):
    recommendation_id: UUID
    portfolio_id: UUID
    expected_revision: int
    indicative_eligible_open_at: UTCTimestamp | None
    unavailable_reason: Reason | None
    limitation: Literal["READONLY_NOT_RESERVED_REVALIDATE_ON_APPLY"] = (
        "READONLY_NOT_RESERVED_REVALIDATE_ON_APPLY"
    )
