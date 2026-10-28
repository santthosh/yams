"""Exchange-session experiment boundaries, without inferred weekdays."""

from dataclasses import dataclass
from datetime import date
from fractions import Fraction

from backend.domain.experiment import ExperimentRequest
from backend.market_data.models import Calendar, Session
from backend.strategies.clock import decision_cutoff


@dataclass(frozen=True)
class ExperimentSchedule:
    sessions: tuple[Session, ...]
    decision_sessions: tuple[date, ...]
    holdout_start_session: date | None
    development_sessions: int
    holdout_sessions: int


def build_schedule(request: ExperimentRequest, calendar: Calendar) -> ExperimentSchedule:
    """Initial close then true calendar month ends, with in-window next-open fills."""
    sessions = tuple(
        row
        for row in calendar.sessions
        if request.start_session <= row.session_date < request.end_session_exclusive
    )
    if not sessions:
        raise ValueError("Experiment interval contains no pinned sessions")
    # Every close is observed at its approved overnight cutoff, including the last.
    for row in sessions:
        decision_cutoff(calendar, row.session_date)
    following = {
        left.session_date: right
        for left, right in zip(calendar.sessions, calendar.sessions[1:], strict=False)
    }
    decisions = tuple(
        row.session_date
        for row in sessions
        if following[row.session_date].session_date < request.end_session_exclusive
        and (
            row == sessions[0]
            or (row.session_date.year, row.session_date.month)
            != (
                following[row.session_date].session_date.year,
                following[row.session_date].session_date.month,
            )
        )
    )
    desired = Fraction(str(request.evaluation_split.holdout_fraction)) * len(sessions)
    holdout_count = min(len(sessions) - 1, -(-desired.numerator // desired.denominator))
    development_count = len(sessions) - holdout_count
    return ExperimentSchedule(
        sessions,
        decisions,
        sessions[development_count].session_date if holdout_count else None,
        development_count,
        holdout_count,
    )
