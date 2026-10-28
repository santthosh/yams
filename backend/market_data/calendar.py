"""Versioned real XNYS sessions, independent of the received price rows."""

import hashlib
import importlib
from datetime import UTC, date, datetime, timedelta
from importlib import resources
from importlib.metadata import version
from pathlib import Path
from zoneinfo import TZPATH

from backend.market_data.models import Calendar


def timezone_identity() -> str:
    for directory in TZPATH:
        path = Path(directory) / "America/New_York"
        if path.is_file():
            return "zoneinfo_sha256_" + hashlib.sha256(path.read_bytes()).hexdigest()
    data = resources.files("tzdata.zoneinfo.America").joinpath("New_York").read_bytes()
    return "tzdata_" + version("tzdata") + "_sha256_" + hashlib.sha256(data).hexdigest()


def real_calendar(
    history_sessions: int, as_of_session: date | None = None, *, now: datetime | None = None
) -> tuple[Calendar, date]:
    if type(history_sessions) is not int or not 252 <= history_sessions <= 2000:
        raise ValueError("Unsupported history budget")
    observed = now or datetime.now(UTC)
    if observed.tzinfo is None or observed.utcoffset() != timedelta(0):
        raise ValueError("Calendar observation must be aware UTC")
    if as_of_session is not None and as_of_session > observed.date():
        raise ValueError("Future market session")
    if version("exchange-calendars") != "4.13.2":
        raise ValueError("Unsupported calendar generator version")
    # Import lazily inside the supervised resource-limited acquisition process.
    xcals = importlib.import_module("exchange_calendars")
    anchor = as_of_session or observed.date()
    generated = xcals.get_calendar(
        "XNYS",
        start=(anchor - timedelta(days=history_sessions * 2 + 40)).isoformat(),
        end=(anchor + timedelta(days=14)).isoformat(),
    )
    rows = [
        {
            "session_date": index.date().isoformat(),
            "open_at": row["open"].isoformat().replace("+00:00", "Z"),
            "close_at": row["close"].isoformat().replace("+00:00", "Z"),
        }
        for index, row in generated.schedule.iterrows()
    ]
    completed = [
        index
        for index, row in enumerate(rows)
        if datetime.fromisoformat(row["close_at"]) <= observed
        and (as_of_session is None or row["session_date"] <= as_of_session.isoformat())
    ]
    if not completed:
        raise ValueError("No completed market session")
    last = completed[-1]
    day = date.fromisoformat(rows[last]["session_date"])
    if as_of_session is not None and day != as_of_session:
        raise ValueError("As-of must be a completed real calendar session")
    if last + 1 >= len(rows) or last + 1 < history_sessions:
        raise ValueError("Insufficient calendar history or lookahead")
    calendar = Calendar.model_validate(
        {
            "schema_version": 1,
            "label": "XNYS regular equity sessions",
            "id": "XNYS",
            "timezone": "America/New_York",
            "generator_version": "exchange_calendars_4.13.2",
            "timezone_rules_version": timezone_identity(),
            "limitations": ["Regular sessions only; instrument-specific halts are not modeled."],
            "sessions": rows[last + 1 - history_sessions : last + 2],
        }
    )
    return calendar, day
