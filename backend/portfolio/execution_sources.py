"""Cross-publication provenance rules shared by loader and fenced publisher."""

from backend.domain.market import SnapshotManifestV1
from backend.market_data.models import Calendar, Session
from backend.portfolio.execution import calendar_digest


def verify_execution_sources(
    decision: SnapshotManifestV1,
    execution: SnapshotManifestV1,
    calendar: Calendar,
    execution_calendar: Calendar,
    eligible: Session,
    asset_id: str,
) -> None:
    actual = next(
        (row for row in execution_calendar.sessions if row.session_date == eligible.session_date),
        None,
    )
    if (
        decision.quality == "blocked"
        or execution.quality == "blocked"
        or decision.mode != execution.mode
        or decision.source.provider != execution.source.provider
        or decision.source.normalization_version != execution.source.normalization_version
        or decision.price_basis != execution.price_basis
        or decision.price_basis.ohlc != "raw_as_traded"
        or decision.calendar.version != calendar_digest(calendar)
        or execution.calendar.version != calendar_digest(execution_calendar)
        or (calendar.id, calendar.timezone) != (execution_calendar.id, execution_calendar.timezone)
        or (decision.calendar.id, decision.calendar.timezone) != (calendar.id, calendar.timezone)
        or (execution.calendar.id, execution.calendar.timezone)
        != (execution_calendar.id, execution_calendar.timezone)
        or actual != eligible
        or asset_id not in decision.coverage.asset_ids
        or asset_id not in execution.coverage.asset_ids
    ):
        raise ValueError("Execution publication is incompatible with approved decision")
    # No delivered real provider has the verified historical/action capabilities.
    if decision.mode != "synthetic_fixture":
        raise ValueError("Unsupported accounting source")
