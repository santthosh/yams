"""Authored SYNTHETIC_DATA_ONLY month-boundary and observation proofs (FIX-06/09)."""

from datetime import UTC, date, datetime

from backend.jobs.review_clock import monthly_anchors, next_review_anchor
from backend.market_data.models import Calendar, Session


def calendar() -> Calendar:
    # Explicit sessions are test evidence, not a generated real exchange calendar.
    days = (
        "2028-07-28",
        "2028-07-31",
        "2028-08-01",
        "2028-08-02",
        "2028-08-31",
        "2028-09-01",
        "2028-09-05",
    )
    return Calendar(
        schema_version=1,
        label="SYNTHETIC_DATA_ONLY",
        id="TEST",
        timezone="America/New_York",
        generator_version="authored-1",
        timezone_rules_version="authored-1",
        limitations=("SYNTHETIC_DATA_ONLY",),
        sessions=tuple(
            Session(
                session_date=date.fromisoformat(day),
                open_at=datetime.fromisoformat(day + "T13:30:00+00:00"),
                close_at=datetime.fromisoformat(day + "T20:00:00+00:00"),
            )
            for day in days
        ),
    )


def test_monthly_due_cutoff_and_daily_fresh_opportunity_are_pinned() -> None:
    values = monthly_anchors(calendar())
    assert [
        (
            r.session.isoformat(),
            r.due_at.isoformat(),
            r.window_end_at.isoformat() if r.window_end_at is not None else None,
        )
        for r in values
    ] == [
        ("2028-07-31", "2028-08-01T12:30:00+00:00", "2028-08-02T12:30:00+00:00"),
        ("2028-08-31", "2028-09-01T12:30:00+00:00", "2028-09-05T12:30:00+00:00"),
    ]
    july = values[0]
    assert july.state(datetime(2028, 8, 1, 12, 29, tzinfo=UTC)) == "future"
    assert july.state(datetime(2028, 8, 1, 12, 30, tzinfo=UTC)) == "current"
    assert july.state(datetime(2028, 8, 1, 20, tzinfo=UTC)) == "current"
    assert july.state(datetime(2028, 8, 2, 12, 30, tzinfo=UTC)) == "missed"
    assert july.state(datetime(2028, 9, 6, tzinfo=UTC)) == "missed"


def test_truncated_calendar_cannot_invent_month_end_or_opportunity_end() -> None:
    source = calendar()
    truncated = source.model_copy(update={"sessions": source.sessions[:2]})
    assert monthly_anchors(truncated) == ()
    missing_window = source.model_copy(update={"sessions": source.sessions[:3]})
    values = monthly_anchors(missing_window)
    assert len(values) == 1 and values[0].window_end_at is None
    assert values[0].state(datetime(2028, 8, 3, tzinfo=UTC)) == "unavailable"


def test_minimum_and_durable_checkpoint_never_replay_old_months() -> None:
    values = monthly_anchors(calendar())
    assert next_review_anchor(values, date(2028, 7, 1), None) == values[0]
    assert next_review_anchor(values, date(2028, 8, 7), None) == values[1]
    assert next_review_anchor(values, date(2028, 7, 1), date(2028, 7, 31)) == values[1]
    assert next_review_anchor(values, date(2028, 7, 1), date(2028, 8, 31)) is None
