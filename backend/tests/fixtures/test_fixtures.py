"""Fixture integrity/oracle checks; these do not claim an implemented trading engine."""

import ast
import hashlib
import json
import math
import statistics
import struct
import subprocess
import sys
from collections import Counter
from datetime import datetime
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, Decimal
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import pytest

from backend.domain.market import AssetV1, MarketBarV1, SnapshotManifestV1
from backend.domain.strategy import StrategyConfigV1

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "data/fixtures"


def read(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


def case(number: int) -> dict[str, Any]:
    value: dict[str, Any] = read(f"fix-{number:02d}/case.json")
    return value


def test_generated_bytes_are_stable_in_two_independent_directories(tmp_path: Path) -> None:
    roots = [tmp_path / "first", tmp_path / "relocated"]
    for root in roots:
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/generate_fixtures.py"),
                "--output-root",
                str(root),
            ],
            check=True,
        )
    first = {
        str(path.relative_to(roots[0])): path.read_bytes()
        for path in roots[0].rglob("*")
        if path.is_file()
    }
    second = {
        str(path.relative_to(roots[1])): path.read_bytes()
        for path in roots[1].rglob("*")
        if path.is_file()
    }
    assert first == second
    assert first == {name: (FIXTURES / name).read_bytes() for name in first}
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/generate_fixtures.py"), "--check"], check=True
    )
    changed = roots[0] / "fix-03/case.json"
    changed.write_bytes(changed.read_bytes() + b" ")
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/generate_fixtures.py"),
            "--check",
            "--output-root",
            str(roots[0]),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0 and "Fixture drift" in result.stderr


def test_generator_cannot_import_the_production_calculations() -> None:
    tree = ast.parse((ROOT / "scripts/generate_fixtures.py").read_text())
    imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    imports += [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    ]
    assert not any(name and name.startswith("backend") for name in imports)


def test_complete_snapshot_and_suite_checksums_and_schemas() -> None:
    suite = read("manifest.json")
    assert suite["label"] == "SYNTHETIC_DATA_ONLY"
    for name, metadata in suite["files"].items():
        content = (FIXTURES / name).read_bytes()
        assert len(content) == metadata["size_bytes"]
        assert hashlib.sha256(content).hexdigest() == metadata["sha256"]
    raw = (FIXTURES / "snapshot/manifest.json").read_bytes()
    manifest = SnapshotManifestV1.model_validate_json(raw)
    assert manifest.canonical_bytes() == raw
    assert manifest.manifest_hash() == suite["snapshot_sha256"]
    assert str(manifest.snapshot_id()) == suite["snapshot_id"]
    assert (
        str(uuid5(NAMESPACE_URL, "urn:yams:dataset:sha256:" + hashlib.sha256(raw).hexdigest()))
        == suite["snapshot_id"]
    )
    for artifact in manifest.artifacts:
        content = (FIXTURES / "snapshot" / artifact.path).read_bytes()
        assert hashlib.sha256(content).hexdigest() == artifact.sha256
        assert len(content) == artifact.size_bytes
    for asset in read("snapshot/assets.json"):
        AssetV1.model_validate(asset)
    bars = read("snapshot/bars.json")
    for bar in bars:
        MarketBarV1.model_validate(bar)
    calendar = read("snapshot/calendar.json")
    sessions = [row["session_date"] for row in calendar["sessions"]]
    assert len(sessions) > 4 * 252
    assert sessions == sorted(set(sessions))
    counts = Counter(bar["asset_id"] for bar in bars)
    assert set(counts) == set(manifest.coverage.asset_ids)
    for asset in counts:
        assert [bar["session_date"] for bar in bars if bar["asset_id"] == asset] == sessions
    assert calendar["label"] == "SYNTHETIC_DATA_ONLY"


def test_authored_canonical_config_matches_production_hash() -> None:
    raw = (FIXTURES / "fix-01/strategy.canonical.json").read_bytes()
    parsed = StrategyConfigV1.from_json(raw)
    assert parsed.canonical_bytes() == raw
    assert parsed.config_hash() == case(1)["expected"]["config_sha256"]
    assert parsed.config_hash() == (FIXTURES / "fix-01/strategy.sha256").read_text().strip()


def test_all_ten_cases_have_inputs_oracles_derivations_and_failure_cases() -> None:
    for number in range(1, 11):
        value = case(number)
        assert value["id"] == f"FIX-{number:02d}"
        assert value["label"] == "SYNTHETIC_DATA_ONLY"
        assert value["inputs"] and value["expected"] and value["derivation"]
        assert value["tolerances"] and value["negative_cases"] and value["owner_issues"]


def test_independent_feature_oracles_and_full_window() -> None:
    expected = case(1)["expected"]
    assert [-math.sqrt(1.5), 0, math.sqrt(1.5)] == pytest.approx(
        expected["z_scores"], abs=1e-12, rel=0
    )
    probe = expected["full_snapshot_probe"]
    prices = [
        float(bar["adjusted_close"])
        for bar in read("snapshot/bars.json")
        if bar["asset_id"] == probe["asset_id"] and bar["session_date"] <= probe["as_of_session"]
    ]
    assert len(prices) == 401
    assert prices[-1] / prices[-127] - 1 == pytest.approx(probe["momentum126"], abs=1e-12, rel=0)
    assert prices[-1] / prices[-64] - 1 == pytest.approx(probe["momentum63"], abs=1e-12, rel=0)
    log_returns = [math.log(b / a) for a, b in zip(prices[-61:-1], prices[-60:], strict=True)]
    assert statistics.stdev(log_returns) * math.sqrt(252) == pytest.approx(
        probe["volatility60"], abs=1e-12, rel=0
    )
    assert statistics.mean(prices[-200:]) == float(probe["sma200"])
    assert statistics.median(prices[-20:]) * 1000000 == float(probe["median_dollar_volume20"])


def test_future_only_mutation_preserves_original_cutoff_oracle() -> None:
    value = case(2)
    inputs, expected = value["inputs"], value["expected"]
    rows = inputs["history"] + [inputs["future"]]

    def at_cutoff() -> list[str]:
        return [
            row["adjusted_close"]
            for row in rows
            if datetime.fromisoformat(row["available_at"])
            <= datetime.fromisoformat(inputs["cutoff"])
        ]

    assert at_cutoff() == expected["as_of_closes"]
    rows[-1]["adjusted_close"] = inputs["mutation"]["future_adjusted_close"]
    assert at_cutoff() == expected["as_of_closes"]
    assert Decimal(at_cutoff()[-1]) / Decimal(at_cutoff()[0]) - 1 == Decimal("0.2")
    # Mutation control: a leaky calculation disagrees with the committed oracle.
    assert Decimal(rows[-1]["adjusted_close"]) / Decimal(rows[0]["adjusted_close"]) - 1 != Decimal(
        "0.2"
    )


def test_decimal_accounting_and_duplicate_posting_oracles() -> None:
    inputs, expected = case(3)["inputs"], case(3)["expected"]
    price, quantity = Decimal(inputs["raw_price"]), Decimal(inputs["quantity"])
    buy = price * (1 + Decimal(inputs["slippage_fraction"]))
    sell = price * (1 - Decimal(inputs["slippage_fraction"]))
    debit = (buy * quantity).quantize(Decimal(".01"), rounding=ROUND_HALF_EVEN)
    credit = (sell * quantity).quantize(Decimal(".01"), rounding=ROUND_HALF_EVEN)
    assert str(Decimal(inputs["cash"]) - debit) == expected["cash_after_buy"]
    assert str(Decimal(inputs["cash"]) - debit + credit) == expected["cash_after_sell"]
    affordable = (Decimal("100") / buy).quantize(Decimal(".000001"), rounding=ROUND_DOWN)
    assert str(affordable) == expected["affordable_quantity"]
    assert [
        str(Decimal(amount).quantize(Decimal(".01"), rounding=ROUND_HALF_EVEN))
        for amount in inputs["rounding"]["cash_amounts"]
    ] == expected["half_even_cash"]
    duplicate = case(4)
    unique = {event["event_key"]: event for event in duplicate["inputs"]["deliveries"]}
    assert len(unique) == duplicate["expected"]["posting_count"]
    once = Decimal("1000") + sum(Decimal(event["cash_delta"]) for event in unique.values())
    twice = Decimal("1000") + sum(
        Decimal(event["cash_delta"]) for event in duplicate["inputs"]["deliveries"]
    )
    assert once == Decimal(duplicate["expected"]["cash"])
    assert twice != once  # Deliberately wrong duplicate accounting must fail the oracle.


def test_strict_open_mutation_and_missing_price_oracle() -> None:
    value = case(6)
    schedule = value["inputs"]["schedule"]
    eligible = [
        next(row["session_date"] for row in schedule if row["open_at"] > approval)
        for approval in value["inputs"]["approvals"]
    ]
    assert eligible == value["expected"]["eligible_sessions"]
    wrong = next(
        row["session_date"] for row in schedule if row["open_at"] >= value["inputs"]["approvals"][1]
    )
    assert wrong != eligible[1]
    assert value["expected"]["fill_count"] == 0


def test_corporate_action_and_isolated_portfolio_arithmetic() -> None:
    value = case(5)
    inputs, expected = value["inputs"], value["expected"]
    ratio = Decimal(inputs["split"]["ratio_numerator"]) / inputs["split"]["ratio_denominator"]
    shares = Decimal(inputs["initial_quantity"]) * ratio
    basis = Decimal(inputs["unit_basis"]) / ratio
    assert shares == Decimal(expected["quantity_after_split"])
    assert basis == Decimal(expected["unit_basis_after_split"])
    assert shares * basis == Decimal(expected["total_basis_after_split"])
    dividend = Decimal(inputs["dividend"]["entitled_quantity"]) * Decimal(
        inputs["dividend"]["per_share"]
    )
    assert dividend == Decimal(expected["cash_dividend_on_payable"])
    assert dividend * inputs["dividend"]["delivery_count"] != dividend
    isolated = case(10)
    balances = {
        entrant["id"]: Decimal(entrant["cash_usd"]) for entrant in isolated["inputs"]["entrants"]
    }
    balances["A"] -= Decimal(isolated["inputs"]["a_only_fill"]["cash_debit"])
    assert balances["A"] == Decimal(isolated["expected"]["a_cash_usd"])
    assert balances["B"] == Decimal(isolated["expected"]["b_cash_usd"])


def test_drawdown_and_annualization_independent_arithmetic() -> None:
    value = case(7)
    nav = [Decimal(amount) for amount in value["inputs"]["nav_usd"]]
    expected = value["expected"]
    assert float(nav[-1] / nav[0] - 1) == expected["cumulative_return"]
    assert float(1 - nav[2] / nav[1]) == expected["max_drawdown"]
    returns = expected["period_returns"]
    assert float((nav[-1] / nav[0]) ** 84 - 1) == pytest.approx(expected["annualized_return"])
    assert statistics.stdev(returns) * math.sqrt(252) == pytest.approx(
        expected["annualized_volatility"], abs=1e-12, rel=0
    )
    assert 100 / statistics.mean(map(float, nav)) == pytest.approx(
        expected["turnover"], abs=1e-12, rel=0
    )


def test_seeded_sampling_artifacts_and_independent_forecast_oracles() -> None:
    value = case(8)
    expected = value["expected"]
    raw = (FIXTURES / "fix-08/starts.i64le").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == expected["indices_sha256"]
    assert len(raw) == 5000 * 13 * 8
    assert list(struct.unpack("<13q", raw[:104])) == expected["first_path_starts"]
    starts = [item[0] for item in struct.iter_unpack("<q", raw)]
    assert min(starts) == 0 and max(starts) == 247
    vectors = (FIXTURES / "fix-08/constant-vectors.f64le").read_bytes()
    assert hashlib.sha256(vectors).hexdigest() == expected["array_sha256"]
    probe = value["inputs"]["small_operator_probe"]
    rows = [index for start in probe["starts"] for index in range(start, start + 2)][:3]
    assert rows == expected["small_sampled_rows"]
    sampled = [probe["vectors"][index] for index in rows]
    assert sampled == expected["small_sampled_vectors"]
    assert all(sum(vector) == 0 for vector in sampled)
    assert float(Decimal("1.005") ** 63 - 1) == pytest.approx(
        expected["constant_proposed_return"], abs=1e-12, rel=0
    )
    assert (
        str((Decimal("1.005") ** 63 * 1000).quantize(Decimal(".01")))
        == expected["constant_proposed_ending_usd"]
    )


def test_changed_artifact_cannot_reuse_snapshot_identity() -> None:
    original = read("snapshot/manifest.json")
    first = SnapshotManifestV1.model_validate(original)
    for role in ("bars", "universe", "calendar"):
        changed = json.loads(json.dumps(original))
        artifact = next(item for item in changed["artifacts"] if item["role"] == role)
        content = (FIXTURES / "snapshot" / artifact["path"]).read_bytes() + b" "
        artifact.update(sha256=hashlib.sha256(content).hexdigest(), size_bytes=len(content))
        if role == "calendar":
            changed["calendar"]["version"] = artifact["sha256"]
        assert SnapshotManifestV1.model_validate(changed).snapshot_id() != first.snapshot_id()
