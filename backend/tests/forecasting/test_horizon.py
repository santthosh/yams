from datetime import UTC, datetime

from backend.forecasting.horizon import map_horizon
from backend.market_data.models import Calendar


def schedule(days: list[tuple[str, int]], *, rules: str = "synthetic_us_post2007_v1") -> Calendar:
    return Calendar.model_validate(
        {
            "schema_version": 1,
            "label": "SYNTHETIC_DATA_ONLY abbreviated arithmetic probe",
            "id": "SYNTHETIC_DST_PROBE",
            "timezone": "America/New_York",
            "generator_version": "authored_probe_v1",
            "timezone_rules_version": rules,
            "limitations": ["Abbreviated fixture, not a validated exchange schedule"],
            "sessions": [
                {
                    "session_date": day,
                    "open_at": f"{day}T{hour - 6:02d}:30:00Z",
                    "close_at": f"{day}T{hour:02d}:00:00Z",
                }
                for day, hour in days
            ],
        }
    )


def test_adr006_ninety_local_days_cross_spring_dst_and_count_pinned_closes() -> None:
    calendar = schedule(
        [
            ("2030-01-01", 21),
            ("2030-01-02", 21),
            ("2030-01-03", 21),
            ("2030-04-01", 20),
            ("2030-04-02", 20),
        ]
    )
    horizon = map_horizon(calendar, datetime(2030, 1, 1, 21, tzinfo=UTC))
    assert horizon.end_at == datetime(2030, 4, 1, 20, tzinfo=UTC)
    assert horizon.sessions is not None
    assert [str(day) for day in horizon.sessions] == ["2030-01-02", "2030-01-03", "2030-04-01"]
    assert horizon.unavailable_reason is None


def test_fall_dst_adds_utc_hour_without_inventing_weekend_sessions() -> None:
    calendar = schedule(
        [("2030-08-05", 20), ("2030-08-06", 20), ("2030-11-01", 20), ("2030-11-04", 21)]
    )
    horizon = map_horizon(calendar, datetime(2030, 8, 5, 20, tzinfo=UTC))
    assert horizon.end_at == datetime(2030, 11, 3, 21, tzinfo=UTC)
    assert horizon.sessions is not None and len(horizon.sessions) == 2
    assert horizon.unavailable_reason is None


def test_missing_coverage_empty_sessions_and_unknown_timezone_are_distinct() -> None:
    cutoff = datetime(2030, 1, 1, 21, tzinfo=UTC)
    partial = map_horizon(schedule([("2030-01-01", 21), ("2030-01-02", 21)]), cutoff)
    assert partial.unavailable_reason == "CALENDAR_UNAVAILABLE"
    assert partial.end_at == datetime(2030, 4, 1, 20, tzinfo=UTC) and partial.sessions is None
    empty = map_horizon(schedule([("2030-01-01", 21)]), cutoff)
    assert empty.unavailable_reason == "ZERO_SESSION_HORIZON" and empty.sessions == ()
    unknown = map_horizon(schedule([("2030-01-01", 21)], rules="unverified"), cutoff)
    assert unknown.unavailable_reason == "CALENDAR_UNAVAILABLE" and unknown.end_at is None
