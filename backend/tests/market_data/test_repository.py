"""Consumer tests over authored rows, rehashed as independent candidate snapshots."""

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import MappingProxyType

import pytest

from backend.domain.market import SnapshotManifestV1
from backend.market_data.files import PinnedSnapshot
from backend.market_data.repository import MarketRepository
from scripts.generate_fixtures import parquet_bars

ROOT = Path(__file__).resolve().parents[3] / "data/fixtures/snapshot"
DAY = date(2027, 1, 5)
CUTOFF = datetime(2027, 1, 5, 21, 0, 1, tzinfo=UTC)


def candidate(
    *,
    prices: tuple[str, str] = ("100", "150"),
    duplicate: str = "",
    delay: bool = False,
    missing_sector: bool = False,
) -> PinnedSnapshot:
    manifest = json.loads((ROOT / "manifest.json").read_bytes())
    content = {item["path"]: (ROOT / item["path"]).read_bytes() for item in manifest["artifacts"]}
    source = json.loads((ROOT / "bars.json").read_bytes())
    rows = [
        row
        for row in source
        if row["asset_id"] == "SYN:AAA" and row["session_date"] in {"2027-01-04", "2027-01-05"}
    ]
    for row, price in zip(rows, prices, strict=True):
        for field in ("open", "high", "low", "close", "adjusted_close"):
            row[field] = price
    if delay:
        rows[1]["available_at"] = "2027-01-05T21:00:01.000001Z"
        rows[1]["ingested_at"] = "2027-01-06T00:00:00Z"
    if duplicate:
        copy = dict(rows[1])
        if duplicate == "conflict":
            copy["adjusted_close"] = "149"
        rows.append(copy)
    content["bars.parquet"] = parquet_bars(rows)
    if missing_sector:
        context = json.loads(content["asset_context.json"])
        context["sectors"] = [row for row in context["sectors"] if row["asset_id"] != "SYN:AAA"]
        content["asset_context.json"] = json.dumps(context).encode()
    for item in manifest["artifacts"]:
        data = content[item["path"]]
        item.update(sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data))
        if item["role"] == "bars":
            item["row_count"] = len(rows)
    return PinnedSnapshot(SnapshotManifestV1.model_validate(manifest), MappingProxyType(content))


@pytest.mark.parametrize(
    ("price", "count"), [("150", 1), ("150.0001", 0), ("50", 1), ("49.9999", 0)]
)
def test_quality_guard_cannot_be_bypassed_with_narrow_window(price: str, count: int) -> None:
    with MarketRepository(candidate(prices=("100", price))) as repository:
        view = repository.as_of(CUTOFF, DAY, start_session=DAY)
        assert len(view.bars) == count
        assert any(item.reason == "EXTREME_ADJUSTED_MOVE" for item in view.diagnostics) == (
            count == 0
        )


def test_exact_cutoff_and_live_ingestion_boundary() -> None:
    with MarketRepository(candidate(delay=True)) as repository:
        assert len(repository.as_of(CUTOFF, DAY, start_session=DAY).bars) == 0
        later = CUTOFF + timedelta(microseconds=1)
        assert len(repository.as_of(later, DAY, start_session=DAY).bars) == 1
        assert len(repository.as_of(later, DAY, start_session=DAY, live=True).bars) == 0


@pytest.mark.parametrize(
    ("duplicate", "reason", "count"),
    [("identical", "DUPLICATE_BAR", 1), ("conflict", "CONFLICTING_BAR", 0)],
)
def test_duplicates_are_audited_or_quarantined(duplicate: str, reason: str, count: int) -> None:
    with MarketRepository(candidate(duplicate=duplicate)) as repository:
        view = repository.as_of(CUTOFF, DAY, start_session=DAY)
        assert len(view.bars) == count
        assert any(
            item.reason == reason and item.asset_id == "SYN:AAA" for item in view.diagnostics
        )


def test_missing_sector_is_not_unknown() -> None:
    with MarketRepository(candidate(missing_sector=True)) as repository:
        assets = {asset.asset_id: asset for asset in repository.as_of(CUTOFF, DAY).assets}
        assert assets["SYN:AAA"].sector is None
        assert "AMBIGUOUS_OR_MISSING_SECTOR" in assets["SYN:AAA"].reasons
        sector = assets["SYN:CCC"].sector
        assert sector is not None and sector.sector == "Unknown"


def replace_json(snapshot: PinnedSnapshot, name: str, value: object) -> PinnedSnapshot:
    content = dict(snapshot.artifacts)
    content[name] = json.dumps(value).encode()
    manifest = snapshot.manifest.model_dump(mode="json")
    for item in manifest["artifacts"]:
        data = content[item["path"]]
        item.update(sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data))
    return PinnedSnapshot(SnapshotManifestV1.model_validate(manifest), MappingProxyType(content))


def test_future_price_and_fundamental_mutations_do_not_change_earlier_view() -> None:
    base = candidate(prices=("100", "120"))
    changed = candidate(prices=("100", "900"))
    context = json.loads(changed.artifacts["asset_context.json"])
    context["fundamentals"] = [
        {
            "asset_id": "SYN:AAA",
            "metric": "earnings",
            "period_end": "2026-12-31",
            "value": "999999",
            "provider": "yams_synthetic_v1",
            "available_at": "2027-01-05T00:00:00Z",
            "ingested_at": "2027-01-05T00:00:00Z",
        }
    ]
    changed = replace_json(changed, "asset_context.json", context)
    cutoff = datetime(2027, 1, 4, 21, 0, 1, tzinfo=UTC)
    with MarketRepository(base) as first, MarketRepository(changed) as second:
        original = first.as_of(cutoff, date(2027, 1, 4))
        mutated = second.as_of(cutoff, date(2027, 1, 4))
        assert original.bars == mutated.bars
        assert original.fundamentals == mutated.fundamentals == ()
        assert original.assets == mutated.assets


def test_cross_venue_same_ticker_and_effective_alias_transition() -> None:
    snapshot = candidate()
    context = json.loads(snapshot.artifacts["asset_context.json"])
    context["aliases"][0].update(symbol="SHARED", effective_to_exclusive="2027-01-05")
    successor = dict(context["aliases"][0])
    successor.update(symbol="RENAMED", effective_from="2027-01-05", effective_to_exclusive=None)
    context["aliases"].append(successor)
    context["aliases"][1].update(symbol="SHARED", venue="XNAS")
    with MarketRepository(replace_json(snapshot, "asset_context.json", context)) as repository:
        earlier = repository.as_of(CUTOFF, date(2027, 1, 4))
        later = repository.as_of(CUTOFF, DAY)
        before = {asset.asset_id: asset.alias for asset in earlier.assets}
        after = {asset.asset_id: asset.alias for asset in later.assets}
        assert before["SYN:AAA"] is not None and before["SYN:BBB"] is not None
        assert before["SYN:AAA"].symbol == before["SYN:BBB"].symbol == "SHARED"
        assert before["SYN:AAA"].venue != before["SYN:BBB"].venue
        assert after["SYN:AAA"] is not None and after["SYN:AAA"].symbol == "RENAMED"


def test_calendar_gaps_are_explicit_without_weekend_invention() -> None:
    with MarketRepository(candidate()) as repository:
        view = repository.as_of(CUTOFF, DAY)
        gaps = [item for item in view.diagnostics if item.reason == "MISSING_SESSION"]
        assert any(item.asset_id == "SYN:BBB" and item.session_date == DAY for item in gaps)
        assert all(item.session_date in {date(2027, 1, 4), DAY} for item in gaps)


@pytest.mark.parametrize("value", ["-1", "0", "NaN", "Infinity"])
def test_invalid_prices_never_enter_repository(value: str) -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        MarketRepository(candidate(prices=("100", value)))


def test_fixture_path_never_connects_and_duckdb_external_access_is_locked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import socket

    import duckdb

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Fixture reader attempted network access")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    with MarketRepository(candidate()) as repository:
        assert repository.as_of(CUTOFF, DAY).bars
        connection = repository._connection
        assert connection is not None
        with pytest.raises(duckdb.Error):
            connection.execute("SET enable_external_access = true")
        with pytest.raises(duckdb.Error):
            connection.execute("SELECT * FROM read_csv('/etc/passwd')").fetchall()
        with pytest.raises(duckdb.Error):
            connection.execute("INSTALL httpfs")


def test_fix05_actions_preserve_facts_and_flag_missing_payable() -> None:
    fixture = json.loads((ROOT.parent / "fix-05/case.json").read_bytes())["inputs"]
    common = {
        "asset_id": "SYN:AAA",
        "provider": "yams_synthetic_v1",
        "currency": "USD",
        "available_at": "2027-01-04T00:00:00Z",
        "ingested_at": "2027-01-04T00:00:00Z",
    }
    split = fixture["split"]
    dividend = fixture["dividend"]
    actions = [
        {
            **common,
            "event_id": split["event_key"],
            "kind": "split",
            "effective_session": split["effective_session"],
            "ratio_numerator": str(split["ratio_numerator"]),
            "ratio_denominator": str(split["ratio_denominator"]),
            "per_share": None,
            "payable_session": None,
        },
        {
            **common,
            "event_id": dividend["event_key"],
            "kind": "dividend",
            "effective_session": dividend["ex_session"],
            "ratio_numerator": None,
            "ratio_denominator": None,
            "per_share": dividend["per_share"],
            "payable_session": None,
        },
    ]
    with MarketRepository(replace_json(candidate(), "actions.json", actions)) as repository:
        view = repository.as_of(CUTOFF, DAY)
        assert view.actions[0].ratio_numerator == "2"
        assert view.actions[1].per_share == "1.25"
        assert view.actions[1].payable_session is None
        assert any(item.reason == "UNRESOLVED_DIVIDEND_PAYABLE" for item in view.diagnostics)
        # Action evidence never changes authored prices or posts synthetic cash.
        assert [bar.adjusted_close for bar in view.bars] == ["100", "150"]
