import hashlib
import json
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.domain.types import canonical_json
from backend.forecasting.artifacts import (
    ForecastFile,
    ForecastManifest,
    publish_forecast,
    read_forecast_artifacts,
    stage_forecast,
)
from backend.forecasting.contracts import ForecastInputs, ForecastPayload
from backend.forecasting.scenarios import ScenarioBundle, compare_scenarios
from backend.market_data.files import PinnedSnapshot, SnapshotIntegrityError
from backend.market_data.repository import MarketRepository


def prepared(pinned: PinnedSnapshot, inputs: ForecastInputs) -> ScenarioBundle:
    with MarketRepository(pinned) as repository:
        return compare_scenarios(
            repository, inputs, forecast_id=UUID(int=3), engine_version="e" * 64
        )


def payload(inputs: ForecastInputs) -> ForecastPayload:
    return ForecastPayload(
        forecast_id=UUID(int=3),
        inputs_canonical_json=inputs.canonical_bytes().decode(),
        engine_version="e" * 64,
    )


def test_sealed_roundtrip_atomic_publication_and_identical_orphan_recovery(
    pinned: PinnedSnapshot,
    inputs: ForecastInputs,
    tmp_path: Path,
) -> None:
    bundle = prepared(pinned, inputs)
    stage, store = tmp_path / "stage", tmp_path / "store"
    store.mkdir()
    digest = stage_forecast(stage, payload(inputs), bundle)
    stored = read_forecast_artifacts(stage, digest)
    assert stored.forecast == bundle.forecast and stored.inputs == inputs
    destination = publish_forecast(stage, store, digest)
    assert destination == store / digest and not stage.exists()
    retry = tmp_path / "retry"
    assert stage_forecast(retry, payload(inputs), bundle) == digest
    assert publish_forecast(retry, store, digest) == destination
    assert read_forecast_artifacts(destination, digest).forecast == bundle.forecast


def test_hash_and_containment_guards_reject_tampering_and_symlinks(
    pinned: PinnedSnapshot,
    inputs: ForecastInputs,
    tmp_path: Path,
) -> None:
    stage = tmp_path / "stage"
    digest = stage_forecast(stage, payload(inputs), prepared(pinned, inputs))
    original = (stage / "returns.f64").read_bytes()
    (stage / "returns.f64").write_bytes(bytes([original[0] ^ 1]) + original[1:])
    with pytest.raises(SnapshotIntegrityError):
        read_forecast_artifacts(stage, digest)
    (stage / "returns.f64").unlink()
    outside = tmp_path / "outside.f64"
    outside.write_bytes(original)
    (stage / "returns.f64").symlink_to(outside)
    with pytest.raises(SnapshotIntegrityError):
        read_forecast_artifacts(stage, digest)


def test_closed_file_manifest_and_full_path_shape_are_required(
    pinned: PinnedSnapshot,
    inputs: ForecastInputs,
    tmp_path: Path,
) -> None:
    with pytest.raises(ValidationError):
        ForecastFile.model_validate({"name": "../outside", "sha256": "a" * 64, "size_bytes": 1})
    with pytest.raises(ValidationError):
        ForecastFile(name="returns.f64", sha256="a" * 64, size_bytes=252 * 16 * 8 + 1)
    bundle = prepared(pinned, inputs)
    broken = ScenarioBundle(
        bundle.forecast,
        bundle.reproducibility,
        {**bundle.artifacts, "paths.f64": bundle.artifacts["paths.f64"][:-8]},
    )
    with pytest.raises(ValueError, match="paths"):
        stage_forecast(tmp_path / "broken", payload(inputs), broken)
    stage = tmp_path / "valid"
    stage_forecast(stage, payload(inputs), bundle)
    header = json.loads((stage / "manifest.json").read_text())
    header["files"].append(header["files"][0])
    with pytest.raises(ValidationError):
        ForecastManifest.model_validate(header)


def test_valid_range_indices_from_another_seed_cannot_be_published_as_original_seed(
    pinned: PinnedSnapshot,
    inputs: ForecastInputs,
    tmp_path: Path,
) -> None:
    other = prepared(pinned, inputs.model_copy(update={"seed": 43}))
    metadata = {**other.reproducibility, "inputs": {**other.reproducibility["inputs"], "seed": 42}}
    forecast = other.forecast.model_copy(
        update={"seed": 42, "fingerprint": hashlib.sha256(canonical_json(metadata)).hexdigest()}
    )
    with pytest.raises(ValueError, match="pinned RNG stream"):
        stage_forecast(
            tmp_path / "bad-stream",
            payload(inputs),
            ScenarioBundle(forecast, metadata, other.artifacts),
        )


def test_unavailable_result_has_no_numeric_path_artifact(
    pinned: PinnedSnapshot,
    inputs: ForecastInputs,
    tmp_path: Path,
) -> None:
    unknown = inputs.model_copy(update={"initial_value_usd": None})
    digest = stage_forecast(tmp_path / "unavailable", payload(unknown), prepared(pinned, unknown))
    stored = read_forecast_artifacts(tmp_path / "unavailable", digest)
    assert stored.forecast.status == "unavailable" and stored.forecast.proposed is None
    assert set(stored.files) == {"forecast.json", "reproducibility.json"}


def test_archived_results_keep_original_statistics_and_timezone_endpoint(
    pinned: PinnedSnapshot,
    inputs: ForecastInputs,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.forecasting import artifacts as artifact_module
    from backend.forecasting import service

    stage = tmp_path / "archived"
    original = prepared(pinned, inputs)
    digest = stage_forecast(stage, payload(inputs), original)

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Must not reinterpret an already sealed original")

    monkeypatch.setattr(artifact_module, "draw_starts", forbidden)
    monkeypatch.setattr(artifact_module, "outcome", forbidden)
    monkeypatch.setattr(service, "map_horizon", forbidden)
    stored = read_forecast_artifacts(stage, digest)
    service.validate_result(payload(inputs), stored, pinned, archived=True)
    assert stored.forecast == original.forecast
    with pytest.raises(AssertionError, match="already sealed"):
        read_forecast_artifacts(stage, digest, verify_numerics=True)
    with pytest.raises(AssertionError, match="already sealed"):
        service.validate_result(payload(inputs), stored, pinned)
