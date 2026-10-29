"""Pinned monthly review opportunities; no wall-clock or weekday calendar guesses."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from backend.market_data.models import Calendar
from backend.strategies.clock import decision_cutoff


@dataclass(frozen=True)
class ReviewAnchor:
    session: date
    due_at: datetime
    window_end_at: datetime | None
    calendar_rows: tuple[str, ...]

    def state(self, observed: datetime) -> Literal["future", "current", "missed", "unavailable"]:
        if observed < self.due_at:
            return "future"
        if self.window_end_at is None:
            return "unavailable"
        return "missed" if observed >= self.window_end_at else "current"


def monthly_anchors(calendar: Calendar) -> tuple[ReviewAnchor, ...]:
    anchors = []
    for index, (current, following) in enumerate(
        zip(calendar.sessions, calendar.sessions[1:], strict=False)
    ):
        if (current.session_date.year, current.session_date.month) == (
            following.session_date.year,
            following.session_date.month,
        ):
            continue
        try:
            window_end = decision_cutoff(calendar, following.session_date)
        except ValueError:
            window_end = None
        anchors.append(
            ReviewAnchor(
                session=current.session_date,
                due_at=decision_cutoff(calendar, current.session_date),
                window_end_at=window_end,
                calendar_rows=tuple(
                    row.model_dump_json() for row in calendar.sessions[index : index + 3]
                ),
            )
        )
    return tuple(anchors)


def next_review_anchor(
    anchors: tuple[ReviewAnchor, ...], minimum: date, after: date | None
) -> ReviewAnchor | None:
    return next(
        (
            row
            for row in anchors
            if row.session >= minimum and (after is None or row.session > after)
        ),
        None,
    )
