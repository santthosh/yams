"""Independent synthetic event and cent-level oracles; no financial engine oracle generation."""

import hashlib
import json
import shutil
from datetime import date
from pathlib import Path
from types import MappingProxyType
from typing import Any
from uuid import UUID

import pytest

from backend.backtesting.runner import BacktestCoreResult, BacktestFailure, run_backtest
from backend.backtesting.schedule import build_schedule
from backend.domain.experiment import ExperimentRequest
from backend.domain.market import SnapshotManifestV1
from backend.market_data.files import PinnedSnapshot
from backend.market_data.models import Calendar
from backend.market_data.repository import MarketRepository
from backend.strategies.clock import decision_cutoff
from backend.strategies.registry import template_config
from scripts.generate_fixtures import parquet_bars

ROOT = Path(__file__).resolve().parents[3] / "data/fixtures"
ORACLE = json.loads((ROOT / "backtesting/core-case.json").read_text())
VERSION = UUID("11111111-1111-4111-8111-111111111111")


def pinned(tmp_path: Path) -> PinnedSnapshot:
    shutil.copytree(ROOT / "snapshot", tmp_path / "snapshot")
    digest = json.loads((ROOT / "manifest.json").read_text())["snapshot_sha256"]
    return PinnedSnapshot.open(tmp_path / "snapshot", digest)


def request(snapshot: PinnedSnapshot, **updates: Any) -> ExperimentRequest:
    return ExperimentRequest.model_validate(
        dict(
            strategy_version_id=VERSION,
            snapshot_id=snapshot.manifest.snapshot_id(),
            start_session=ORACLE["start_session"],
            end_session_exclusive=ORACLE["end_session_exclusive"],
            initial_capital_usd="1000.00",
            benchmark_asset_id="SYN:SPY",
            execution_policy_id="us_eod_next_open_v1",
            random_seed=42,
            evaluation_split={"kind": "chronological", "holdout_fraction": 0.25},
        )
        | updates
    )


def altered(
    snapshot: PinnedSnapshot, *, bars: list[dict[str, Any]] | None = None, **json_artifacts: Any
) -> PinnedSnapshot:
    content = dict(snapshot.artifacts)
    if bars is not None:
        content["bars.parquet"] = parquet_bars(bars)
    for path, value in json_artifacts.items():
        content[path] = json.dumps(value).encode()
    manifest = snapshot.manifest.model_dump(mode="json")
    for item in manifest["artifacts"]:
        data = content[item["path"]]
        item.update(sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data))
        if item["role"] == "bars" and bars is not None:
            item["row_count"] = len(bars)
    # Authored provenance remains unchanged. Other artifact mutations obtain new identities.
    return PinnedSnapshot(SnapshotManifestV1.model_validate(manifest), MappingProxyType(content))


def run(snapshot: PinnedSnapshot, **updates: Any) -> BacktestCoreResult:
    with MarketRepository(snapshot) as repository:
        return run_backtest(
            repository,
            request(snapshot, **updates),
            template_config("mean_reversion"),
            engine_version="test-core-1",
        )


def test_independent_next_open_cent_oracle_and_reproducible_split(tmp_path: Path) -> None:
    snapshot = pinned(tmp_path)
    result = run(snapshot)
    assert result == run(snapshot)
    assert BacktestCoreResult.model_validate_json(result.model_dump_json()) == result
    assert [row.nav_usd for row in result.points] == ORACLE["daily_nav_usd"]
    assert [row.phase for row in result.points] == ["development"] * 3 + ["holdout"]
    assert str(result.holdout_start_session) == ORACLE["holdout_start_session"]
    assert len(result.decisions) == 1 and len(result.executions) == 3
    assert result.points[0].state.positions == ()  # no recommendation-time mutation
    assert result.points[1].state.cash_usd == ORACLE["cash_after_fills_usd"]
    assert {row.asset_id: row.quantity for row in result.points[1].state.positions} == ORACLE[
        "shares_floor_6dp"
    ]
    for row in result.executions:
        assert row.fill is not None
        assert str(row.fill.execution_session) == "2028-07-19"
        assert row.fill.execution_at > row.context.approved_at == row.context.decision_cutoff
        assert row.fill.gross_usd == ORACLE["debits_half_even_cents"][row.order.asset_id]
        assert row.fill.proposed_at >= row.fill.evidence_available_at > row.fill.execution_at
    assert {
        "SYNTHETIC_DATA_ONLY",
        "INSUFFICIENT_HOLDOUT",
        "HOLDOUT_REPEATED_SELECTION_CAVEAT",
    } <= set(result.warnings)
    # Internal series are not a public completed ExperimentRunV1 or invented metrics.
    assert "metrics" not in result.model_dump()


def test_calendar_month_end_initial_anchor_and_no_end_boundary_fill(tmp_path: Path) -> None:
    snapshot = pinned(tmp_path)
    calendar = Calendar.model_validate_json(snapshot.artifacts["calendar.json"])
    schedule = build_schedule(request(snapshot, end_session_exclusive="2028-08-03"), calendar)
    assert schedule.decision_sessions == (date(2028, 7, 18), date(2028, 7, 31))
    assert decision_cutoff(calendar, date(2028, 7, 31)).isoformat() == "2028-08-01T12:30:00+00:00"
    narrow = build_schedule(request(snapshot, end_session_exclusive="2028-08-01"), calendar)
    assert narrow.decision_sessions == (date(2028, 7, 18),)
    one = run(snapshot, end_session_exclusive="2028-07-19")
    assert len(one.points) == 1 and not one.decisions and not one.executions
    assert one.holdout_start_session is None
    with pytest.raises(ValueError, match="no pinned sessions"):
        build_schedule(
            request(snapshot, start_session="2028-07-22", end_session_exclusive="2028-07-23"),
            calendar,
        )
    with pytest.raises(ValueError, match="next pinned"):
        build_schedule(
            request(
                snapshot,
                start_session=calendar.sessions[-1].session_date,
                end_session_exclusive="2040-01-01",
            ),
            calendar,
        )


def test_future_bar_and_action_injection_cannot_change_prior_decision(tmp_path: Path) -> None:
    snapshot = pinned(tmp_path)
    baseline = run(snapshot)
    rows = json.loads((ROOT / "snapshot/bars.json").read_bytes())
    for row in rows:
        if row["session_date"] > "2028-07-21":
            row["adjusted_close"] = "1234"
    future_action = action("dividend", "2028-07-20", payable="2028-07-21")
    future_action["available_at"] = future_action["ingested_at"] = "2028-08-01T14:30:00Z"
    result = run(altered(snapshot, bars=rows, **{"actions.json": [future_action]}))
    assert result.points == baseline.points
    assert (
        result.decisions[0].measured.momentum.candidates
        == baseline.decisions[0].measured.momentum.candidates
    )
    assert result.decisions[0].plan.orders == baseline.decisions[0].plan.orders
    assert result.decisions[0].measured.allocation == baseline.decisions[0].measured.allocation
    assert result.snapshot_sha256 != baseline.snapshot_sha256


@pytest.mark.parametrize(
    ("day", "reason"),
    [("2028-07-19", "MISSING_ELIGIBLE_OPEN"), ("2028-07-20", "MISSING_HELD_CLOSE")],
)
def test_missing_evidence_fails_without_substituting_another_day(
    tmp_path: Path, day: str, reason: str
) -> None:
    snapshot = pinned(tmp_path)
    rows = [
        row
        for row in json.loads((ROOT / "snapshot/bars.json").read_bytes())
        if not (row["asset_id"] == "SYN:AAA" and row["session_date"] == day)
    ]
    with pytest.raises(BacktestFailure, match=reason):
        run(altered(snapshot, bars=rows))


def test_accounting_retains_exit_prices_without_enlarging_decision_universe(tmp_path: Path) -> None:
    snapshot = pinned(tmp_path)
    universe = json.loads(snapshot.artifacts["universe.json"])
    for row in universe["memberships"]:
        if row["asset_id"] == "SYN:AAA":
            row["effective_to_exclusive"] = "2028-07-20"
    changed = altered(snapshot, **{"universe.json": universe})
    assert run(changed).points == run(snapshot).points
    with MarketRepository(changed) as repository:
        day = date(2028, 7, 20)
        cutoff = decision_cutoff(repository.calendar, day)
        eligible = repository.as_of(cutoff, day)
        accounting = repository.accounting_as_of(cutoff, day)
        assert "SYN:AAA" not in {row.asset_id for row in eligible.assets}
        assert "SYN:AAA" not in {row.asset_id for row in eligible.bars}
        assert "SYN:AAA" in {row.asset_id for row in accounting.bars}


def action(kind: str, day: str, *, payable: str | None = None) -> dict[str, Any]:
    return dict(
        asset_id="SYN:AAA",
        available_at=day + "T14:30:00Z",
        ingested_at=day + "T14:30:00Z",
        event_id="authored-1",
        kind=kind,
        effective_session=day,
        provider="SYNTHETIC",
        currency="USD",
        ratio_numerator="2" if kind == "split" else None,
        ratio_denominator="1" if kind == "split" else None,
        per_share="1.25" if kind == "dividend" else None,
        payable_session=payable,
    )


def test_dividend_entitlement_and_payable_credit_once(tmp_path: Path) -> None:
    snapshot = pinned(tmp_path)
    result = run(
        altered(
            snapshot, **{"actions.json": [action("dividend", "2028-07-20", payable="2028-07-21")]}
        )
    )
    assert result.points[2].state.cash_usd == "392.84"
    assert result.points[3].state.cash_usd == "396.41"
    assert [row.cash_delta_usd for row in result.actions] == ["0.00", "3.57"]
    assert result.points[3].state.entitlements[0].quantity == "2.855103"


def test_split_before_session_valuation_preserves_basis(tmp_path: Path) -> None:
    snapshot = pinned(tmp_path)
    rows = json.loads((ROOT / "snapshot/bars.json").read_bytes())
    from decimal import Decimal

    for row in rows:
        if row["asset_id"] == "SYN:AAA" and row["session_date"] >= "2028-07-20":
            for field in ["open", "high", "low", "close"]:
                row[field] = str(Decimal(row[field]) / 2)
    result = run(altered(snapshot, bars=rows, **{"actions.json": [action("split", "2028-07-20")]}))
    assert [row.nav_usd for row in result.points] == ORACLE["daily_nav_usd"]
    position = next(row for row in result.points[2].state.positions if row.asset_id == "SYN:AAA")
    assert position.quantity == ORACLE["split_probe"]["quantity_after"]
    assert position.total_basis_usd == "200.34"
    assert result.points[2].state.cash_usd == "392.84"


@pytest.mark.parametrize(
    ("kind", "day", "reason"),
    [
        ("dividend", "2028-07-20", "PAYABLE_DATE_UNAVAILABLE"),
        ("split", "2028-07-19", "ORDER_ACTION_CONFLICT"),
    ],
)
def test_unsupported_actions_fail_safely(tmp_path: Path, kind: str, day: str, reason: str) -> None:
    snapshot = pinned(tmp_path)
    with pytest.raises(BacktestFailure, match=reason):
        run(altered(snapshot, **{"actions.json": [action(kind, day)]}))


def test_cooperative_cancel_and_short_warmup(tmp_path: Path) -> None:
    snapshot = pinned(tmp_path)
    with MarketRepository(snapshot) as repository:
        calls = 0

        def cancelled() -> bool:
            nonlocal calls
            calls += 1
            return calls > 2

        with pytest.raises(BacktestFailure, match="CANCELLED"):
            run_backtest(
                repository,
                request(snapshot),
                template_config("mean_reversion"),
                engine_version="test",
                cancelled=cancelled,
            )
    result = run(snapshot, start_session="2027-01-04", end_session_exclusive="2027-01-08")
    assert "LIMITED_WARMUP" in result.warnings
    assert all(row.nav_usd == "1000.00" and not row.state.positions for row in result.points)


def test_daily_bar_arriving_after_its_overnight_cutoff_cannot_backfill_nav(tmp_path: Path) -> None:
    snapshot = pinned(tmp_path)
    rows = json.loads((ROOT / "snapshot/bars.json").read_bytes())
    for row in rows:
        if row["asset_id"] == "SYN:AAA" and row["session_date"] == "2028-07-19":
            row["available_at"] = row["ingested_at"] = "2028-07-20T14:30:00Z"
    with pytest.raises(BacktestFailure, match="MISSING_ELIGIBLE_OPEN"):
        run(altered(snapshot, bars=rows))


def test_two_point_holdout_carries_post_fill_state(tmp_path: Path) -> None:
    snapshot = pinned(tmp_path)
    result = run(snapshot, end_session_exclusive="2028-07-20")
    assert [row.phase for row in result.points] == ["development", "holdout"]
    assert [row.nav_usd for row in result.points] == ["1000.00", "999.40"]
    assert len(result.points[1].state.positions) == 3
    assert result.points[1].state.cash_usd == "392.84"


def test_diagnostic_capability_cannot_authorize_historical_accounting(tmp_path: Path) -> None:
    from dataclasses import replace

    from backend.backtesting.runner import validate_source

    snapshot = pinned(tmp_path)
    metadata = snapshot.manifest.model_dump(mode="json")
    metadata["mode"] = "research_market_data"
    metadata["source"]["rights_status"] = "verified_local_use"
    metadata["source"]["rights_reference"] = "test-only-explicit-rights"
    # Isolate source admission: a diagnostics capability does not establish any
    # of the four historical accounting capabilities, even with raw OHLC metadata.
    provenance_path = next(
        row["path"]
        for row in metadata["artifacts"]
        if row["sha256"] == metadata["source"]["capabilities_sha256"]
    )
    content = dict(snapshot.artifacts)
    content[provenance_path] = json.dumps(
        {
            "supports_diagnostics": True,
            "raw_execution_prices": False,
            "complete_action_accounting": False,
        }
    ).encode()
    new_hash = hashlib.sha256(content[provenance_path]).hexdigest()
    for row in metadata["artifacts"]:
        if row["path"] == provenance_path:
            row.update(sha256=new_hash, size_bytes=len(content[provenance_path]))
    metadata["source"]["capabilities_sha256"] = new_hash
    candidate = replace(
        snapshot,
        manifest=SnapshotManifestV1.model_validate(metadata),
        artifacts=MappingProxyType(content),
    )
    with MarketRepository(snapshot) as repository:
        repository.snapshot = candidate  # source guard unit test; no research reader claim
        with pytest.raises(BacktestFailure, match="UNSUPPORTED_ACCOUNTING_SOURCE"):
            validate_source(repository)


def test_mismatched_snapshot_and_uncovered_interval_fail(tmp_path: Path) -> None:
    snapshot = pinned(tmp_path)
    with MarketRepository(snapshot) as repository:
        with pytest.raises(BacktestFailure, match="SNAPSHOT_IDENTITY_MISMATCH"):
            run_backtest(
                repository,
                request(snapshot, snapshot_id=VERSION),
                template_config("mean_reversion"),
                engine_version="test",
            )
    with pytest.raises(BacktestFailure, match="UNCOVERED_EXPERIMENT_INTERVAL"):
        run(snapshot, start_session="2026-12-01")


def test_weekend_cutoff_and_actual_month_end_decision_trace(tmp_path: Path) -> None:
    snapshot = pinned(tmp_path)
    calendar = Calendar.model_validate_json(snapshot.artifacts["calendar.json"])
    assert decision_cutoff(calendar, date(2028, 7, 28)).isoformat() == "2028-07-31T12:30:00+00:00"
    result = run(snapshot, end_session_exclusive="2028-08-03")
    assert [row.plan.context.decision_session for row in result.decisions] == [
        date(2028, 7, 18),
        date(2028, 7, 31),
    ]
    assert all(
        row.plan.context.approved_at == row.plan.context.decision_cutoff for row in result.decisions
    )
    assert [row.session_date for row in result.points] == [
        row.session_date
        for row in calendar.sessions
        if date(2028, 7, 18) <= row.session_date < date(2028, 8, 3)
    ]
