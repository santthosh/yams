"""ADR-011/FIX-01/02 independent oracles, shared policy and honest family evidence."""

import hashlib
import json
import shutil
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, localcontext
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.domain.strategy import MeanReversionSignalConfig, StrategyConfigV1
from backend.market_data.files import PinnedSnapshot
from backend.market_data.repository import MarketRepository
from backend.portfolio.allocation import allocate_momentum
from backend.strategies.features import sample_log_volatility
from backend.strategies.low_volatility import LowVolatilityFeatures
from backend.strategies.mean_reversion import MeanReversionFeatures, measure
from backend.strategies.momentum import MomentumEvaluation, evaluate_momentum, evaluate_strategy
from backend.strategies.registry import ALTERNATIVE_CONFIG_HASHES, template_config

ROOT = Path(__file__).resolve().parents[3] / "data/fixtures"
ORACLE = json.loads((ROOT / "template_extensions/case.json").read_text())


@pytest.mark.parametrize("kind", ["mean_reversion", "low_volatility"])
def test_config_canonical_vectors_and_validation(kind: str) -> None:
    raw = (ROOT / f"template_extensions/{kind}.canonical.json").read_bytes()
    config = StrategyConfigV1.from_json(raw)
    assert config.canonical_bytes() == raw
    assert hashlib.sha256(raw).hexdigest() == ORACLE["families"][kind]["config_sha256"]
    assert config.config_hash() == ALTERNATIVE_CONFIG_HASHES[kind]
    assert template_config(kind) == config
    for mutation in ["unknown_kind", "cross_family", "missing", "bad_window", "history"]:
        data = config.model_dump(mode="json")
        if mutation == "unknown_kind":
            data["signals"]["kind"] = "passive_spy"
        elif mutation == "cross_family":
            data["signals"]["momentum_long_sessions"] = 126
        elif mutation == "missing":
            del data["signals"]["require_positive_trend"]
        elif mutation == "bad_window":
            data["signals"]["volatility_sessions"] = True
        else:
            data["signals"]["volatility_sessions"] = 252
        with pytest.raises(ValidationError):
            StrategyConfigV1.model_validate(data)


@pytest.mark.parametrize("kind", ["mean_reversion", "low_volatility"])
def test_full_asof_snapshot_golden_features_ranks_and_targets(kind: str, tmp_path: Path) -> None:
    identity = json.loads((ROOT / "manifest.json").read_text())["snapshot_sha256"]
    config = template_config(kind)
    shutil.copytree(ROOT / "snapshot", tmp_path / "snapshot")
    with MarketRepository(PinnedSnapshot.open(tmp_path / "snapshot", identity)) as repository:
        view = repository.as_of(datetime(2028, 7, 19, 12, 30, tzinfo=UTC), date(2028, 7, 18))
        assert view.session_date.isoformat() == ORACLE["as_of_session"]
        evaluated = evaluate_strategy(
            view, repository.calendar, config, engine_version="fixture-v1"
        )
        expected = ORACLE["families"][kind]
        assert list(evaluated.selected_ids) == expected["ranks"]
        for row in evaluated.candidates:
            if row.asset_id not in ORACLE["measurements"]:
                assert row.features is None and row.scoring is None and row.reasons
                continue
            assert row.features is not None and row.scoring is not None
            assert isinstance(
                row.features,
                MeanReversionFeatures if kind == "mean_reversion" else LowVolatilityFeatures,
            )
            values = ORACLE["measurements"][row.asset_id]
            assert row.features.volatility == pytest.approx(float(values["volatility"]), abs=1e-12)
            assert row.scoring.score == pytest.approx(
                float(expected["scores"][row.asset_id]), abs=1e-12
            )
            if isinstance(row.features, MeanReversionFeatures):
                assert row.features.mean_reversion_sma == values["mean_reversion_sma"]
                assert row.features.mean_reversion_distance == pytest.approx(
                    float(values["mean_reversion_distance"]), abs=1e-12
                )
            assert "momentum_long" not in row.features.model_dump()
        allocated = allocate_momentum(evaluated, config)
        assert {row.asset_id: row.weight for row in allocated.allocation.targets} == expected[
            "default_targets"
        ]
        assert allocated.allocation.cash_weight == expected["default_cash"]
        assert MomentumEvaluation.model_validate_json(evaluated.model_dump_json()) == evaluated
        assert (
            evaluate_strategy(
                replace(view, assets=tuple(reversed(view.assets)), bars=tuple(reversed(view.bars))),
                repository.calendar,
                config,
                engine_version="fixture-v1",
            )
            == evaluated
        )
        data = config.model_dump(mode="json")
        data["portfolio"]["max_positions"] = 2
        limited = StrategyConfigV1.model_validate(data)
        measured = evaluate_strategy(
            view, repository.calendar, limited, engine_version="fixture-v1"
        )
        target = allocate_momentum(measured, limited).allocation
        assert list(target.selected_ids) == expected["top_two_selected"]
        assert {row.asset_id: row.weight for row in target.targets} == expected["top_two_targets"]
        assert target.cash_weight == expected["top_two_cash"]
        with pytest.raises(ValueError, match="requires a momentum"):
            evaluate_momentum(view, repository.calendar, config, engine_version="fixture-v1")
        # Future-only bars have no place in the required completed as-of window.
        future = tuple(
            bar.model_copy(
                update={
                    "session_date": view.session_date + timedelta(days=10),
                    "adjusted_close": "999999",
                }
            )
            for bar in view.bars[-5:]
        )
        assert (
            evaluate_strategy(
                replace(view, bars=view.bars + future),
                repository.calendar,
                config,
                engine_version="fixture-v1",
            )
            == evaluated
        )
        empty = evaluate_strategy(
            replace(view, bars=()), repository.calendar, config, engine_version="fixture-v1"
        )
        assert not empty.selected_ids and all(
            "MISSING_HISTORY" in row.reasons for row in empty.candidates
        )
        assert allocate_momentum(empty, config).allocation.cash_weight == "1"
        gap = replace(
            view, bars=tuple(bar for bar in view.bars if bar.session_date != view.session_date)
        )
        assert not evaluate_strategy(
            gap, repository.calendar, config, engine_version="fixture-v1"
        ).selected_ids


@pytest.mark.parametrize("kind", ["mean_reversion", "low_volatility"])
def test_ties_and_zero_volatility_keep_shared_selection_policy(kind: str, tmp_path: Path) -> None:
    identity = json.loads((ROOT / "manifest.json").read_text())["snapshot_sha256"]
    raw = template_config(kind).model_dump(mode="json")
    raw["signals"]["require_positive_trend"] = False
    raw["portfolio"]["max_positions"] = 1
    config = StrategyConfigV1.model_validate(raw)
    shutil.copytree(ROOT / "snapshot", tmp_path / "snapshot")
    with MarketRepository(PinnedSnapshot.open(tmp_path / "snapshot", identity)) as repository:
        view = repository.as_of(datetime(2028, 7, 19, 12, 30, tzinfo=UTC), date(2028, 7, 18))
        tied = replace(
            view, assets=tuple(row for row in view.assets if row.asset_id in {"SYN:AAA", "SYN:BBB"})
        )
        result = evaluate_strategy(tied, repository.calendar, config, engine_version="fixture-v1")
        assert result.selected_ids == ("SYN:AAA",)
        assert all(row.scoring is not None and row.scoring.score == 0 for row in result.candidates)
        zeros = replace(
            view, assets=tuple(row for row in view.assets if row.asset_id == "SYN:ZERO")
        )
        result = evaluate_strategy(zeros, repository.calendar, config, engine_version="fixture-v1")
        assert result.candidates[0].eligible and "ZERO_VOLATILITY" in result.candidates[0].reasons
        assert result.candidates[0].rank == 1 and not result.selected_ids
        assert allocate_momentum(result, config).allocation.cash_weight == "1"
        mixed = replace(
            view,
            assets=tuple(row for row in view.assets if row.asset_id in {"SYN:AAA", "SYN:ZERO"}),
        )
        result = evaluate_strategy(mixed, repository.calendar, config, engine_version="fixture-v1")
        assert result.candidates[-1].rank == 1  # Zero distance beats declining-distance AAA too.
        assert result.selected_ids == ("SYN:AAA",)


def test_independent_twenty_close_probe_and_annualization_expression() -> None:
    signals = template_config("mean_reversion").signals
    assert isinstance(signals, MeanReversionSignalConfig)
    for last, preceding, expected in [("90", "110", 0.1), ("100", "100", 0), ("110", "90", -0.1)]:
        values = ["100"] * 232 + ["100"] * 18 + [preceding, last]
        result = measure(values, signals)
        assert result.mean_reversion_sma == "100"
        assert result.mean_reversion_distance == pytest.approx(expected, abs=1e-12)
    with localcontext() as context:
        context.prec = 60
        expected_vol = (Decimal(101) / 100).ln() * (Decimal(60 * 252) / 59).sqrt()
    assert sample_log_volatility(
        ["100" if i % 2 == 0 else "101" for i in range(61)]
    ) == pytest.approx(float(expected_vol), abs=1e-12)
