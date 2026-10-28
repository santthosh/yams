"""Approved cutoff boundaries, pinned handler lineage and financial rerun proof."""

import hashlib
import json
import multiprocessing as mp
import shutil
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import MappingProxyType
from uuid import uuid4

import pytest

from backend.domain.evaluation import StrategyEvaluationResultV1
from backend.domain.market import SnapshotManifestV1
from backend.domain.strategy import StrategyConfigV1
from backend.jobs.handlers.evaluate_strategy import EvaluationFailure, evaluate_strategy
from backend.market_data.files import PinnedSnapshot
from backend.market_data.models import Calendar
from backend.market_data.repository import MarketRepository
from backend.portfolio.allocation import allocate_momentum
from backend.strategies.clock import decision_cutoff
from backend.strategies.momentum import evaluate_snapshot
from backend.tests.market_data.test_repository import candidate
from backend.tests.strategies.test_evaluation_contracts import ROOT, explicit_fixture_result
from scripts.generate_fixtures import parquet_bars


@pytest.mark.parametrize(
    ("day", "close", "next_day", "next_open", "expected"),
    [
        (
            "2026-03-06",
            "2026-03-06T21:00:00Z",
            "2026-03-09",
            "2026-03-09T13:30:00Z",
            "2026-03-09T12:30:00Z",
        ),
        (
            "2026-03-09",
            "2026-03-09T20:00:00Z",
            "2026-03-10",
            "2026-03-10T13:30:00Z",
            "2026-03-10T12:30:00Z",
        ),
        (
            "2026-11-27",
            "2026-11-27T18:00:00Z",
            "2026-11-30",
            "2026-11-30T14:30:00Z",
            "2026-11-30T13:30:00Z",
        ),
        (
            "2026-05-22",
            "2026-05-22T20:00:00Z",
            "2026-05-26",
            "2026-05-26T13:30:00Z",
            "2026-05-26T12:30:00Z",
        ),
    ],
)
def test_pinned_next_open_controls_cutoff_across_dst_early_close_and_holiday(
    day: str, close: str, next_day: str, next_open: str, expected: str
) -> None:
    data = json.loads((ROOT / "snapshot/calendar.json").read_text())
    data["sessions"] = [
        {"session_date": day, "open_at": day + "T14:30:00Z", "close_at": close},
        {"session_date": next_day, "open_at": next_open, "close_at": next_day + "T21:00:00Z"},
    ]
    calendar = Calendar.model_validate(data)
    assert decision_cutoff(calendar, date.fromisoformat(day)) == datetime.fromisoformat(expected)
    with pytest.raises(ValueError, match="absent"):
        decision_cutoff(calendar, date(2026, 1, 1))
    with pytest.raises(ValueError, match="next pinned"):
        decision_cutoff(calendar, date.fromisoformat(next_day))
    # A malformed adjacent session must not be silently skipped or repaired.
    data["sessions"][1]["open_at"] = (
        (datetime.fromisoformat(close) + timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
    )
    with pytest.raises(ValueError, match="overnight"):
        decision_cutoff(Calendar.model_validate(data), date.fromisoformat(day))


@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_available_at_boundary_and_late_ingestion_are_distinct(offset: int) -> None:
    snapshot = candidate(prices=("100", "120"))
    content = dict(snapshot.artifacts)
    source = json.loads((ROOT / "snapshot/bars.json").read_text())
    rows = [
        row
        for row in source
        if row["asset_id"] == "SYN:AAA" and row["session_date"] in {"2027-01-04", "2027-01-05"}
    ]
    cutoff = datetime(2027, 1, 6, 13, 30, tzinfo=UTC)
    rows[1]["available_at"] = (
        (cutoff + timedelta(microseconds=offset)).isoformat().replace("+00:00", "Z")
    )
    rows[1]["ingested_at"] = (cutoff + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
    content["bars.parquet"] = parquet_bars(rows)
    manifest = snapshot.manifest.model_dump(mode="json")
    for item in manifest["artifacts"]:
        value = content[item["path"]]
        item.update(sha256=hashlib.sha256(value).hexdigest(), size_bytes=len(value))
    pinned = PinnedSnapshot(SnapshotManifestV1.model_validate(manifest), MappingProxyType(content))
    with MarketRepository(pinned) as repository:
        assert decision_cutoff(repository.calendar, date(2027, 1, 5)) == cutoff
        view = repository.as_of(cutoff, date(2027, 1, 5), start_session=date(2027, 1, 5))
        assert len(view.bars) == (1 if offset <= 0 else 0)
        assert not repository.as_of(
            cutoff, date(2027, 1, 5), start_session=date(2027, 1, 5), live=True
        ).bars
        if offset > 0:
            assert any(item.reason == "MISSING_SESSION" for item in view.diagnostics)


def test_handler_pins_policy_build_and_reruns_independent_fixture(tmp_path: Path) -> None:
    payload, expected = explicit_fixture_result(tmp_path / "explicit")
    shutil.copytree(ROOT / "snapshot", tmp_path / "snapshots" / payload.snapshot_sha256)
    cancel = mp.get_context("spawn").Event()
    first = StrategyEvaluationResultV1.model_validate_json(
        evaluate_strategy(payload.model_dump(mode="json"), cancel, root=tmp_path)
    )
    second_payload = payload.model_copy(update={"evaluation_id": uuid4()})
    second = StrategyEvaluationResultV1.model_validate_json(
        evaluate_strategy(second_payload.model_dump(mode="json"), cancel, root=tmp_path)
    )
    assert first == second == expected
    assert first.decision_cutoff_utc == datetime(2028, 7, 18, 12, 30, tzinfo=UTC)
    assert first.selected_ids == ("SYN:AAA", "SYN:BBB", "SYN:CCC")
    assert first.cash_target_weight == "0.4"
    for field, value in (
        ("engine_version", "0" * 64),
        ("calendar_sha256", "0" * 64),
        ("config_sha256", "0" * 64),
        ("decision_cutoff_utc", first.decision_cutoff_utc + timedelta(microseconds=1)),
    ):
        changed = payload.model_copy(update={field: value})
        with pytest.raises(EvaluationFailure) as caught:
            evaluate_strategy(changed.model_dump(mode="json"), cancel, root=tmp_path)
        assert caught.value.code == "VALIDATION_ERROR"
    cancel.set()
    with pytest.raises(EvaluationFailure):
        evaluate_strategy(payload.model_dump(mode="json"), cancel, root=tmp_path)


def test_late_price_mutation_cannot_change_past_candidate_or_target() -> None:
    rules = StrategyConfigV1.from_json((ROOT / "fix-01/strategy.canonical.json").read_bytes())
    results = []
    for price in ("100", "900"):
        manifest = json.loads((ROOT / "snapshot/manifest.json").read_text())
        content = {
            item["path"]: (ROOT / "snapshot" / item["path"]).read_bytes()
            for item in manifest["artifacts"]
        }
        rows = json.loads((ROOT / "snapshot/bars.json").read_text())
        late = next(
            row
            for row in rows
            if row["asset_id"] == "SYN:AAA" and row["session_date"] == "2028-07-17"
        )
        late.update(
            available_at="2028-07-18T12:30:00.000001Z", ingested_at="2028-07-18T12:30:00.000001Z"
        )
        for field in ("open", "high", "low", "close", "adjusted_close"):
            late[field] = price
        content["bars.parquet"] = parquet_bars(rows)
        for item in manifest["artifacts"]:
            value = content[item["path"]]
            item.update(sha256=hashlib.sha256(value).hexdigest(), size_bytes=len(value))
        pinned = PinnedSnapshot(
            SnapshotManifestV1.model_validate(manifest), MappingProxyType(content)
        )
        calendar = Calendar.model_validate_json(content["calendar.json"])
        result = allocate_momentum(
            evaluate_snapshot(
                pinned,
                rules,
                decision_cutoff(calendar, date(2028, 7, 17)),
                date(2028, 7, 17),
                engine_version="test-build",
            ),
            rules,
        )
        aaa = next(row for row in result.momentum.candidates if row.asset_id == "SYN:AAA")
        assert not aaa.eligible and "SYN:AAA" not in result.allocation.selected_ids
        results.append(result)
    # Snapshot lineage must differ; financial evidence must be unchanged.
    assert results[0].momentum.manifest_sha256 != results[1].momentum.manifest_sha256
    assert results[0].momentum.candidates == results[1].momentum.candidates
    assert results[0].momentum.data_diagnostics == results[1].momentum.data_diagnostics
    assert results[0].allocation == results[1].allocation
