"""Ninety New York calendar days with explicitly pinned timezone/schedule evidence."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from backend.market_data.calendar import timezone_identity
from backend.market_data.models import Calendar


@dataclass(frozen=True)
class Horizon:
    end_at: datetime | None
    sessions: tuple[date, ...] | None
    unavailable_reason: str | None


def _transitions(year: int) -> tuple[date, date]:
    march, november = date(year, 3, 1), date(year, 11, 1)
    return (
        march + timedelta(days=(6 - march.weekday()) % 7 + 7),
        november + timedelta(days=(6 - november.weekday()) % 7),
    )


def _synthetic_endpoint(cutoff: datetime) -> datetime:
    """Exactly the fixture generator's declared US post-2007 rule, independent of host TZ."""
    spring, fall = _transitions(cutoff.year)
    start = datetime.combine(spring, datetime.min.time(), UTC) + timedelta(hours=7)
    end = datetime.combine(fall, datetime.min.time(), UTC) + timedelta(hours=6)
    offset = -4 if start <= cutoff < end else -5
    local = cutoff.astimezone(timezone(timedelta(hours=offset)))
    target = local.replace(tzinfo=None) + timedelta(days=90)
    spring, fall = _transitions(target.year)
    spring_at = datetime.combine(spring, datetime.min.time()) + timedelta(hours=2)
    fall_at = datetime.combine(fall, datetime.min.time()) + timedelta(hours=2)
    # Canonical market cutoffs are morning times, outside these ambiguous/gap hours.
    if spring_at <= target < spring_at + timedelta(hours=1) or (
        fall_at - timedelta(hours=1) <= target < fall_at
    ):
        raise ValueError("Ambiguous or nonexistent synthetic local endpoint")
    target_offset = -4 if spring_at <= target < fall_at else -5
    return target.replace(tzinfo=timezone(timedelta(hours=target_offset))).astimezone(UTC)


def map_horizon(calendar: Calendar, cutoff: datetime) -> Horizon:
    if cutoff.tzinfo is None or cutoff.utcoffset() != timedelta(0):
        raise ValueError("Forecast cutoff must be aware UTC")
    try:
        if calendar.timezone_rules_version == "synthetic_us_post2007_v1":
            endpoint = _synthetic_endpoint(cutoff)
        elif calendar.timezone_rules_version == timezone_identity():
            local = cutoff.astimezone(ZoneInfo("America/New_York"))
            endpoint = (local + timedelta(days=90)).astimezone(UTC)
        else:
            return Horizon(None, None, "CALENDAR_UNAVAILABLE")
    except (ValueError, OSError):
        return Horizon(None, None, "CALENDAR_UNAVAILABLE")
    sessions = tuple(
        row.session_date for row in calendar.sessions if cutoff < row.close_at <= endpoint
    )
    if not sessions:
        return Horizon(endpoint, (), "ZERO_SESSION_HORIZON")
    if calendar.sessions[0].close_at > cutoff or calendar.sessions[-1].close_at < endpoint:
        return Horizon(endpoint, None, "CALENDAR_UNAVAILABLE")
    if len(sessions) > 90:
        return Horizon(endpoint, None, "WORKLOAD_LIMIT")
    return Horizon(endpoint, sessions, None)
