"""Pinned end-of-day policy; arrival order never determines the decision time."""

from datetime import date, datetime, timedelta

from backend.market_data.models import Calendar


def decision_cutoff(calendar: Calendar, session_date: date) -> datetime:
    for index, session in enumerate(calendar.sessions):
        if session.session_date == session_date:
            if index + 1 == len(calendar.sessions):
                raise ValueError("Decision requires the next pinned calendar session")
            following = calendar.sessions[index + 1]
            cutoff = following.open_at - timedelta(hours=1)
            if cutoff < session.close_at:
                raise ValueError("Next pinned opening cannot support an overnight cutoff")
            return cutoff
    raise ValueError("Decision session is absent from the pinned calendar")
