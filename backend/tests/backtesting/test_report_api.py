"""Independent financial vectors survive public projection and immutable file paging."""

import hashlib
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.backtesting.artifacts import stage_core
from backend.backtesting.benchmark import calculate_report
from backend.backtesting.contracts import BacktestCorePayload
from backend.backtesting.metrics import calculate_metrics, drawdown_series
from backend.backtesting.queries import ExperimentQueryError, decode_cursor, encode_cursor
from backend.backtesting.report_artifacts import (
    ROLES,
    publish_report,
    read_artifact,
    read_manifest,
    stage_report,
    verify_report,
)
from backend.backtesting.reports import project_report
from backend.domain.experiment_api import (
    ExperimentCurvePointV1,
    ExperimentReportSummaryV1,
    ExperimentReproducibilityV1,
    ExperimentTradeV1,
)
from backend.domain.types import canonical_json, load_json
from backend.market_data.files import SnapshotIntegrityError
from backend.market_data.repository import MarketRepository
from backend.strategies.registry import template_config
from backend.tests.backtesting.test_core import pinned, request


def output(
    tmp_path: Path,
) -> tuple[
    ExperimentReportSummaryV1,
    tuple[ExperimentCurvePointV1, ...],
    tuple[ExperimentTradeV1, ...],
    ExperimentReproducibilityV1,
]:
    from uuid import uuid4

    from backend.backtesting.runner import run_backtest

    snapshot = pinned(tmp_path)
    inputs = request(snapshot)
    config = template_config("mean_reversion")
    with MarketRepository(snapshot) as repository:
        core = run_backtest(repository, inputs, config, engine_version="a" * 64)
        digest = stage_core(tmp_path / "core", core)
        payload = BacktestCorePayload(
            experiment_id=uuid4(),
            inputs_canonical_json=canonical_json(load_json(inputs.model_dump_json())).decode(),
            source_mode=core.source_mode,
            config_sha256=core.config_sha256,
            snapshot_sha256=core.snapshot_sha256,
            calendar_sha256=core.calendar_sha256,
            engine_version=core.engine_version,
            config_canonical_json=config.canonical_bytes().decode(),
        )
        report = calculate_report(payload, core, digest, repository)
    return project_report(payload, core, report, snapshot.manifest.source.provider)


def test_shared_drawdown_path_uses_independent_fix07_values() -> None:
    values = drawdown_series(("100.00", "120.00", "90.00", "108.00"))
    assert [value.value for value in values] == [0, 0, 0.25, 0.1]
    assert (
        calculate_metrics(("100.00", "120.00", "90.00", "108.00")).max_drawdown_fraction
        == values[2]
    )
    assert drawdown_series(()) == ()
    assert drawdown_series(("0.00", "1.00"))[1].unavailable_reason == "ZERO_START_NAV"
    assert (
        calculate_metrics(("100.00",)).max_drawdown_fraction.unavailable_reason
        == "INSUFFICIENT_RETURN_HISTORY"
    )


def test_public_projection_retains_money_dates_holdout_weights_and_disclosures(
    tmp_path: Path,
) -> None:
    summary, points, trades, repro = output(tmp_path)
    assert [point.portfolio_nav_usd for point in points] == [
        "1000.00",
        "999.40",
        "993.66",
        "1000.22",
    ]
    assert [point.drawdown_fraction.value for point in points] == [0, 0.0006, 0.00634, 0]
    assert [point.benchmark_nav_usd for point in points] == [
        "1000.00",
        "1000.23",
        "1000.45",
        "1000.68",
    ]
    assert points[0].cash_weight.value == "1"
    assert isinstance(points[-1].cash_weight.value, str)
    assert points[-1].phase == "holdout" and points[-2].phase == "development"
    assert summary.portfolio.total.metrics.trade_count == 3
    assert len(trades) == 3 and all(trade.currency == "USD" for trade in trades)
    assert repro.core_manifest_sha256 == summary.core_manifest_sha256
    assert "SYNTHETIC_DATA_ONLY" in repro.warnings
    assert "nav_usd" not in summary.model_dump_json()
    assert "BENCHMARK_FRICTION_FREE_FULLY_INVESTED" in summary.benchmark.warnings


def test_report_hashes_fixed_roles_and_restart_reads(tmp_path: Path) -> None:
    values = output(tmp_path)
    digest = stage_report(tmp_path / "stage", *values)
    manifest = verify_report(tmp_path / "stage", digest)
    assert tuple(item.role for item in manifest.artifacts) == ROLES
    store = tmp_path / "store"
    store.mkdir()
    publish_report(tmp_path / "stage", store, digest)
    root = store / digest
    assert read_manifest(root, digest) == manifest
    point = ExperimentCurvePointV1.model_validate_json(
        read_artifact(root, manifest, "series").splitlines()[0]
    )
    assert point.portfolio_nav_usd == "1000.00"
    # Fresh identical computation/staging can safely adopt an already verified orphan.
    assert stage_report(tmp_path / "retry", *values) == digest
    publish_report(tmp_path / "retry", store, digest)
    assert verify_report(root, digest) == manifest
    content = root / "series.jsonl"
    content.write_bytes(content.read_bytes().replace(b"1000.00", b"1001.00", 1))
    with pytest.raises(SnapshotIntegrityError):
        read_artifact(root, manifest, "series")


@pytest.mark.parametrize(
    "attack", ["symlink", "hardlink", "parent_symlink", "manifest", "oversized"]
)
def test_report_read_rejects_unsafe_or_unpinned_files(tmp_path: Path, attack: str) -> None:
    values = output(tmp_path)
    digest = stage_report(tmp_path / "stage", *values)
    root = tmp_path / "stage"
    if attack in {"symlink", "hardlink"}:
        target = root / "summary.json"
        data = target.read_bytes()
        target.unlink()
        (tmp_path / "outside.json").write_bytes(data)
        if attack == "symlink":
            target.symlink_to(tmp_path / "outside.json")
        else:
            os.link(tmp_path / "outside.json", target)
    elif attack == "parent_symlink":
        (tmp_path / "alias").symlink_to(root, target_is_directory=True)
        root = tmp_path / "alias"
    elif attack == "manifest":
        digest = hashlib.sha256(b"different").hexdigest()
    else:
        (root / "summary.json").write_bytes(b"x" * (1024 * 1024))
    with pytest.raises((SnapshotIntegrityError, ValidationError)):
        verify_report(root, digest)


def test_opaque_cursor_cannot_cross_query_or_parse_paths() -> None:
    cursor = encode_cursor("run-a:series:window", "25")
    assert decode_cursor(cursor, "run-a:series:window") == "25"
    for malformed in (cursor, "../../outside", "____", encode_cursor("other", "0")):
        with pytest.raises(ExperimentQueryError):
            decode_cursor(malformed, "run-b:trades:window")
