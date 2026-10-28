"""Worker-side reporting over actual persisted, hash-verified core outputs."""

import json
from pathlib import Path

import pytest
from sqlalchemy import Engine

from backend.backtesting.benchmark import BacktestMetricsReport, build_report, calculate_report
from backend.backtesting.service import admit_core, read_core_run
from backend.jobs.queue import Queue
from backend.jobs.worker import Worker
from backend.market_data.files import PinnedSnapshot
from backend.market_data.repository import MarketRepository
from backend.tests.integration.test_backtest_core import prepare
from backend.tests.integration.test_bootstrap import database as database

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[3] / "data/fixtures"
EXPECTED = json.loads((ROOT / "metrics_extensions/case.json").read_text())["core_report"][
    "expected"
]


def test_report_requires_complete_persisted_core_and_preserves_its_artifacts(
    database: Engine, tmp_path: Path
) -> None:
    request = prepare(database, tmp_path)
    accepted = admit_core(database, tmp_path, request)
    queued = read_core_run(database, tmp_path, accepted.experiment_id)
    assert queued is not None
    snapshot = PinnedSnapshot.open(
        tmp_path / "snapshots" / queued.payload.snapshot_sha256, queued.payload.snapshot_sha256
    )
    with (
        MarketRepository(snapshot) as repository,
        pytest.raises(ValueError, match="complete sealed core"),
    ):
        build_report(queued, repository)
    assert Worker(Queue(database), artifact_root=tmp_path).run_once()
    saved = read_core_run(database, tmp_path, accepted.experiment_id)
    assert saved is not None and saved.result is not None
    prior = saved.result.model_dump_json()
    with MarketRepository(snapshot) as repository:
        first = build_report(saved, repository)
        assert saved.manifest_sha256 is not None
        assert (
            calculate_report(saved.payload, saved.result, saved.manifest_sha256, repository)
            == first
        )
        with pytest.raises(ValueError, match="complete input window"):
            calculate_report(
                saved.payload,
                saved.result.model_copy(update={"points": saved.result.points[:-1]}),
                saved.manifest_sha256,
                repository,
            )
        assert build_report(saved, repository) == first
    assert BacktestMetricsReport.model_validate_json(first.model_dump_json()) == first
    assert first.core_manifest_sha256 == saved.manifest_sha256
    assert first.comparison_sha256 == first.comparison.fingerprint()
    assert (
        first.portfolio.total.metrics.cumulative_return_fraction.value
        == EXPECTED["cumulative_return"]
    )
    assert first.portfolio.total.metrics.annualized_return_fraction.value == pytest.approx(
        EXPECTED["annualized_return"], abs=1e-12
    )
    assert first.portfolio.total.metrics.turnover_fraction.value == pytest.approx(
        EXPECTED["turnover"], abs=1e-12
    )
    assert first.portfolio.total.metrics.slippage_usd == "0.61"
    assert first.portfolio.holdout.return_observations == 1
    assert (
        first.portfolio.holdout.metrics.annualized_volatility_fraction.unavailable_reason
        == "INSUFFICIENT_RETURN_HISTORY"
    )
    assert first.benchmark.available and first.benchmark.nav_usd == (
        "1000.00",
        "1000.23",
        "1000.45",
        "1000.68",
    )
    assert first.cash_nav_usd == ("1000.00",) * 4
    assert (
        first.exposures[0].cash_weight.value == 1
        and first.exposures[0].max_position_weight.value == 0
    )
    assert (
        "SYNTHETIC_DATA_ONLY" in first.warnings
        and "HOLDOUT_REPEATED_SELECTION_CAVEAT" in first.warnings
    )
    again = read_core_run(database, tmp_path, accepted.experiment_id)
    assert (
        again is not None and again.result is not None and again.result.model_dump_json() == prior
    )
    assert again.manifest_sha256 == saved.manifest_sha256
