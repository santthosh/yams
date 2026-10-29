"""Real snapshot/Parquet mutations exercise the repository guard, not a mocked view."""

import hashlib
import json
from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import duckdb

from backend.forecasting.contracts import ForecastInputs
from backend.forecasting.scenarios import ScenarioBundle, compare_scenarios
from backend.market_data.files import PinnedSnapshot
from backend.market_data.repository import MarketRepository
from scripts.generate_fixtures import parquet_bars


def mutate(
    pinned: PinnedSnapshot,
    temporary: Path,
    change: Callable[[list[dict[str, Any]]], None],
) -> PinnedSnapshot:
    artifact = next(row for row in pinned.manifest.artifacts if row.role == "bars")
    original = temporary / "original.parquet"
    original.write_bytes(pinned.artifacts[artifact.path])
    with duckdb.connect(config={"threads": 1}) as connection:
        rows = [
            json.loads(row[0])
            for row in connection.execute(
                "SELECT payload FROM read_parquet(?) ORDER BY asset_id,session_date",
                [str(original)],
            ).fetchall()
        ]
    change(rows)
    content = parquet_bars(rows)
    replacement = artifact.model_copy(
        update={"sha256": hashlib.sha256(content).hexdigest(), "size_bytes": len(content)}
    )
    manifest = pinned.manifest.model_copy(
        update={
            "artifacts": tuple(
                replacement if row.path == artifact.path else row
                for row in pinned.manifest.artifacts
            ),
        }
    )
    return PinnedSnapshot(manifest, {**pinned.artifacts, artifact.path: content})


def run(pinned: PinnedSnapshot, inputs: ForecastInputs) -> ScenarioBundle:
    bound = inputs.model_copy(
        update={
            "snapshot_id": pinned.manifest.snapshot_id(),
            "snapshot_sha256": pinned.manifest.manifest_hash(),
        }
    )
    with MarketRepository(pinned) as repository:
        return compare_scenarios(
            repository, bound, forecast_id=UUID(int=3), engine_version="e" * 64
        )


def test_future_bar_changes_cannot_change_past_paths(
    pinned: PinnedSnapshot,
    inputs: ForecastInputs,
    tmp_path: Path,
) -> None:
    original = run(pinned, inputs)

    def change(rows: list[dict[str, Any]]) -> None:
        for row in rows:
            if row["asset_id"] == "SYN:AAA" and row["session_date"] > str(inputs.as_of_session):
                for key in ("open", "high", "low", "close", "adjusted_close"):
                    row[key] = str(Decimal(row[key]) * Decimal("1.1"))
                break
        else:
            raise AssertionError("Expected an actual future observation")

    changed = run(mutate(pinned, tmp_path, change), inputs)
    assert changed.forecast.status == "available"
    assert changed.forecast.proposed == original.forecast.proposed
    assert changed.forecast.hold_unchanged == original.forecast.hold_unchanged
    assert changed.artifacts == original.artifacts
    # Source lineage must change even though the as-of numerical evidence does not.
    assert changed.forecast.fingerprint != original.forecast.fingerprint
    assert changed.forecast.input_array_sha256 == original.forecast.input_array_sha256


def test_one_required_late_close_invalidates_both_cases_without_older_row_fallback(
    pinned: PinnedSnapshot,
    inputs: ForecastInputs,
    tmp_path: Path,
) -> None:
    def change(rows: list[dict[str, Any]]) -> None:
        row = next(
            r
            for r in rows
            if r["asset_id"] == "SYN:AAA" and r["session_date"] == str(inputs.as_of_session)
        )
        late = (
            (inputs.decision_cutoff_utc + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
        )
        row["available_at"], row["ingested_at"] = late, late

    result = run(mutate(pinned, tmp_path, change), inputs).forecast
    assert result.status == "unavailable"
    assert result.unavailable_reason == "INSUFFICIENT_ALIGNED_HISTORY"
    assert result.proposed is None and result.hold_unchanged is None
    assert result.input_array_sha256 is None
