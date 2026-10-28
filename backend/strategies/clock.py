"""Pinned end-of-day policy; arrival order never determines the decision time."""

from datetime import date, datetime, timedelta

from backend.market_data.models import Calendar


def decision_cutoff(calendar: Calendar, session_date: date) -> datetime:
    for session in calendar.sessions:
        if session.session_date == session_date:
            return session.close_at + timedelta(minutes=15)
    raise ValueError("Decision session is absent from the pinned calendar")
