"""Bounded immutable scenario evidence; only the lease owner registers its digest."""

import hashlib
import os
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import Field, TypeAdapter, model_validator

from backend.domain.forecast import ForecastV1
from backend.domain.types import Contract, Hash256, canonical_json, load_json
from backend.forecasting.bootstrap import (
    BLOCK,
    LOOKBACK,
    NUMPY_VERSION,
    PATHS,
    array_bytes,
    draw_starts,
    outcome,
)
from backend.forecasting.contracts import ForecastInputs, ForecastPayload
from backend.forecasting.scenarios import ScenarioBundle, normalized_inputs
from backend.market_data.files import SnapshotIntegrityError, read_contained_file
from backend.market_data.publication import rename_no_replace

FileName = Literal[
    "forecast.json",
    "reproducibility.json",
    "returns.f64",
    "indices.i64",
    "rng-state.json",
    "paths.f64",
]
BOUNDS = {
    "forecast.json": 512 * 1024,
    "reproducibility.json": 1024 * 1024,
    "returns.f64": 252 * 16 * 8,
    "indices.i64": 5000 * 18 * 8,
    "rng-state.json": 4096,
    "paths.f64": 2 * 5000 * 91 * 8,
}


class ForecastFile(Contract):
    name: FileName
    sha256: Hash256
    size_bytes: int = Field(strict=True, ge=1)

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if self.size_bytes > BOUNDS[self.name]:
            raise ValueError("Oversized forecast artifact")
        return self


class ForecastManifest(Contract):
    schema_version: Literal[1] = 1
    forecast_id: UUID
    inputs_sha256: Hash256
    engine_version: Hash256
    files: tuple[ForecastFile, ...] = Field(min_length=2, max_length=6)

    @model_validator(mode="after")
    def closed_files(self) -> Self:
        names = tuple(row.name for row in self.files)
        if names != tuple(sorted(set(names))) or not {
            "forecast.json",
            "reproducibility.json",
        } <= set(names):
            raise ValueError("Forecast files must be complete, unique and sorted")
        return self


@dataclass(frozen=True)
class StoredForecast:
    manifest: ForecastManifest
    inputs: ForecastInputs
    forecast: ForecastV1
    metadata: dict[str, Any]
    files: Mapping[str, bytes]


def _sync(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def stage_forecast(stage: Path, payload: ForecastPayload, bundle: ScenarioBundle) -> str:
    files = {
        **bundle.artifacts,
        "forecast.json": canonical_json(load_json(bundle.forecast.model_dump_json())),
        "reproducibility.json": canonical_json(
            {
                "inputs_canonical_json": payload.inputs_canonical_json,
                "fingerprint_inputs": bundle.reproducibility,
            }
        ),
    }
    manifest = ForecastManifest(
        forecast_id=payload.forecast_id,
        inputs_sha256=hashlib.sha256(payload.inputs_canonical_json.encode()).hexdigest(),
        engine_version=payload.engine_version,
        files=tuple(
            ForecastFile.model_validate(
                {
                    "name": name,
                    "sha256": hashlib.sha256(value).hexdigest(),
                    "size_bytes": len(value),
                }
            )
            for name, value in sorted(files.items())
        ),
    )
    encoded = canonical_json(load_json(manifest.model_dump_json()))
    stage.mkdir(mode=0o700, exist_ok=False)
    for name, value in [*files.items(), ("manifest.json", encoded)]:
        descriptor = os.open(
            stage / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
    _sync(stage)
    digest = hashlib.sha256(encoded).hexdigest()
    read_forecast_artifacts(stage, digest, verify_numerics=True)
    return digest


def read_forecast_artifacts(
    root: Path, digest: str, *, verify_numerics: bool = False
) -> StoredForecast:
    digest = TypeAdapter(Hash256).validate_python(digest)
    header = read_contained_file(root, "manifest.json", 65536)
    if hashlib.sha256(header).hexdigest() != digest:
        raise SnapshotIntegrityError("Forecast manifest identity mismatch")
    manifest = ForecastManifest.model_validate_json(header)
    files: dict[str, bytes] = {}
    for row in manifest.files:
        value = read_contained_file(root, row.name, BOUNDS[row.name])
        if len(value) != row.size_bytes or hashlib.sha256(value).hexdigest() != row.sha256:
            raise SnapshotIntegrityError("Forecast artifact identity mismatch")
        files[row.name] = value
    forecast = ForecastV1.model_validate_json(files["forecast.json"])
    repro = load_json(files["reproducibility.json"])
    if not isinstance(repro, dict) or set(repro) != {"inputs_canonical_json", "fingerprint_inputs"}:
        raise ValueError("Invalid forecast reproducibility envelope")
    payload = ForecastPayload(
        forecast_id=manifest.forecast_id,
        engine_version=manifest.engine_version,
        inputs_canonical_json=repro["inputs_canonical_json"],
    )
    inputs, metadata = payload.inputs, repro["fingerprint_inputs"]
    if not isinstance(metadata, dict):
        raise ValueError("Invalid forecast fingerprint inputs")
    if (
        manifest.inputs_sha256 != hashlib.sha256(payload.inputs_canonical_json.encode()).hexdigest()
        or forecast.id != payload.forecast_id
        or forecast.engine_version != payload.engine_version
        or forecast.snapshot_id != inputs.snapshot_id
        or forecast.snapshot_sha256 != inputs.snapshot_sha256
        or forecast.calendar_version != inputs.calendar_sha256
        or forecast.data_status != inputs.source_mode
        or forecast.as_of_session != inputs.as_of_session
        or forecast.decision_cutoff_utc != inputs.decision_cutoff_utc
        or forecast.initial_value_usd != inputs.initial_value_usd
        or forecast.current_allocation != inputs.current_allocation
        or forecast.proposed_allocation != inputs.proposed_allocation
        or forecast.seed != inputs.seed
        or metadata.get("inputs") != normalized_inputs(inputs)
        or metadata.get("engine_version") != payload.engine_version
        or metadata.get("numpy_version") != NUMPY_VERSION
    ):
        raise ValueError("Forecast lineage differs from pinned inputs")
    if forecast.status == "available" and (
        hashlib.sha256(canonical_json(metadata)).hexdigest() != forecast.fingerprint
    ):
        raise ValueError("Forecast fingerprint mismatch")
    expected_metadata = {
        "fingerprint_schema_version": 1,
        "method": "multivariate_block_bootstrap_v1",
        "simulation_count": PATHS,
        "lookback_sessions": LOOKBACK,
        "block_length_sessions": BLOCK,
        "horizon_calendar_days": 90,
        "decision_start_at": inputs.decision_cutoff_utc.isoformat(),
        "generator": "PCG64",
        "sampling_version": "noncircular_c_order_v1",
        "cash_return_fraction": 0,
    }
    if any(metadata.get(key) != value for key, value in expected_metadata.items()):
        raise ValueError("Forecast method metadata differs from the supported model")
    stored = StoredForecast(manifest, inputs, forecast, metadata, files)
    _validate_arrays(stored, verify_numerics=verify_numerics)
    return stored


def _validate_arrays(stored: StoredForecast, *, verify_numerics: bool) -> None:
    import numpy as np

    forecast, files, metadata = stored.forecast, stored.files, stored.metadata
    union = metadata.get("asset_order")
    expected_union = sorted(
        {
            row.asset_id
            for allocation in (stored.inputs.current_allocation, stored.inputs.proposed_allocation)
            for row in allocation.weights
            if Decimal(row.weight) > 0
        }
    )
    if union != expected_union:
        raise ValueError("Invalid canonical forecast asset order")
    for name, digest in (
        ("returns.f64", forecast.input_array_sha256),
        ("indices.i64", forecast.sampled_indices.sha256 if forecast.sampled_indices else None),
        (
            "rng-state.json",
            forecast.rng.initial_state.sha256 if forecast.rng.initial_state else None,
        ),
    ):
        if (name in files) != (digest is not None) or (
            name in files and hashlib.sha256(files[name]).hexdigest() != digest
        ):
            raise ValueError("Forecast evidence reference mismatch")
    if "returns.f64" in files:
        if not 1 <= len(union) <= 16 or len(files["returns.f64"]) != LOOKBACK * len(union) * 8:
            raise ValueError("Invalid return-array shape")
        if (
            metadata.get("input_shape") != [LOOKBACK, len(union)]
            or metadata.get("input_encoding") != "little_endian_float64_c_order_v1"
        ):
            raise ValueError("Return-array metadata differs from its encoding")
        values = np.frombuffer(files["returns.f64"], dtype="<f8")
        if not np.isfinite(values).all() or np.any(values < -1):
            raise ValueError("Invalid return-array values")
    count = forecast.horizon_trading_sessions
    if "indices.i64" in files:
        if not count or len(files["indices.i64"]) != PATHS * ((count + BLOCK - 1) // BLOCK) * 8:
            raise ValueError("Invalid sampled-index shape")
        indices = np.frombuffer(files["indices.i64"], dtype="<i8")
        if np.any(indices < 0) or np.any(indices >= 248):
            raise ValueError("Invalid noncircular sampled indices")
        if verify_numerics:
            expected = draw_starts(count, stored.inputs.seed)
            if array_bytes(expected.starts, integer=True) != files["indices.i64"] or canonical_json(
                expected.initial_state
            ) != files.get("rng-state.json"):
                raise ValueError("Sampled indices differ from the pinned RNG stream")
    if forecast.status == "unavailable":
        if "paths.f64" in files:
            raise ValueError("Unavailable forecast cannot publish numerical paths")
        return
    if (
        "paths.f64" not in files
        or not count
        or len(files["paths.f64"]) != 2 * PATHS * (count + 1) * 8
    ):
        raise ValueError("Incomplete scenario paths")
    paths = np.frombuffer(files["paths.f64"], dtype="<f8").reshape(2, PATHS, count + 1)
    if not np.isfinite(paths).all() or np.any(paths < 0):
        raise ValueError("Invalid scenario paths")
    assert forecast.initial_value_usd is not None
    assert stored.inputs.proposed_allocation.upfront_cost_usd is not None
    if (
        not np.all(paths[:, :, 0] == 1)
        or metadata.get("path_shape") != [2, PATHS, count + 1]
        or metadata.get("path_unit") != "gross_growth_factor"
        or metadata.get("capital_cost_policy") != "exact_upfront_capital_v1"
    ):
        raise ValueError("Scenario growth paths differ from the pinned method")
    nav = forecast.initial_value_usd
    if verify_numerics:
        if (
            outcome(paths[0, :, -1], nav) != forecast.hold_unchanged
            or outcome(paths[1, :, -1], nav, stored.inputs.proposed_allocation.upfront_cost_usd)
            != forecast.proposed
        ):
            raise ValueError("Scenario outcomes differ from preserved paths")


def publish_forecast(stage: Path, store: Path, digest: str) -> Path:
    read_forecast_artifacts(stage, digest, verify_numerics=True)
    destination = store / digest
    _sync(stage)
    try:
        rename_no_replace(stage, destination)
    except FileExistsError:
        read_forecast_artifacts(destination, digest, verify_numerics=True)
    _sync(store)
    return destination
