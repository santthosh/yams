"""Independent cross-publication contract cases; all evidence is synthetic."""

from datetime import timedelta
from pathlib import Path

import pytest

from backend.domain.market import SnapshotManifestV1
from backend.market_data.models import Calendar
from backend.portfolio.execution import calendar_digest
from backend.portfolio.execution_sources import verify_execution_sources

ROOT = Path(__file__).resolve().parents[3] / "data/fixtures/snapshot"


def source() -> tuple[SnapshotManifestV1, Calendar]:
    manifest = SnapshotManifestV1.model_validate_json((ROOT / "manifest.json").read_bytes())
    calendar = Calendar.model_validate_json((ROOT / "calendar.json").read_bytes())
    return manifest, calendar


def test_calendar_extension_preserves_original_eligible_open() -> None:
    original, calendar = source()
    last = calendar.sessions[-1]
    extension = last.model_copy(
        update={
            "session_date": last.session_date + timedelta(days=7),
            "open_at": last.open_at + timedelta(days=7),
            "close_at": last.close_at + timedelta(days=7),
        }
    )
    later = calendar.model_copy(update={"sessions": (*calendar.sessions, extension)})
    reference = original.calendar.model_copy(update={"version": calendar_digest(later)})
    execution = original.model_copy(update={"calendar": reference})
    assert calendar_digest(later) != calendar_digest(calendar)
    verify_execution_sources(original, execution, calendar, later, calendar.sessions[1], "SYN:AAA")


@pytest.mark.parametrize(
    "change",
    [
        "provider",
        "normalization",
        "price_basis",
        "quality",
        "missing_asset",
        "calendar_open",
        "calendar_identity",
    ],
)
def test_incompatible_publication_cannot_execute(change: str) -> None:
    original, calendar = source()
    execution = original
    later = calendar
    eligible = calendar.sessions[1]
    if change == "provider":
        execution = original.model_copy(
            update={
                "source": original.source.model_copy(
                    update={"provider": "other_synthetic_provider"}
                )
            }
        )
    elif change == "normalization":
        execution = original.model_copy(
            update={"source": original.source.model_copy(update={"normalization_version": "2"})}
        )
    elif change == "price_basis":
        execution = original.model_copy(
            update={
                "price_basis": original.price_basis.model_copy(
                    update={"ohlc": "provider_unverified"}
                )
            }
        )
    elif change == "quality":
        execution = original.model_copy(update={"quality": "blocked"})
    elif change == "missing_asset":
        execution = original.model_copy(
            update={"coverage": original.coverage.model_copy(update={"asset_ids": ("SYN:BBB",)})}
        )
    elif change == "calendar_open":
        changed = eligible.model_copy(update={"open_at": eligible.open_at + timedelta(minutes=1)})
        later = calendar.model_copy(
            update={
                "sessions": tuple(changed if row == eligible else row for row in calendar.sessions)
            }
        )
        execution = original.model_copy(
            update={
                "calendar": original.calendar.model_copy(update={"version": calendar_digest(later)})
            }
        )
    elif change == "calendar_identity":
        later = calendar.model_copy(update={"id": "OTHER_SYNTHETIC_CALENDAR"})
        execution = original.model_copy(
            update={
                "calendar": original.calendar.model_copy(
                    update={"id": later.id, "version": calendar_digest(later)}
                )
            }
        )
    with pytest.raises(ValueError, match="incompatible"):
        verify_execution_sources(original, execution, calendar, later, eligible, "SYN:AAA")
