from typing import Any

import pytest
from pydantic import ValidationError

from backend.domain.market import AssetV1, MarketBarV1, SnapshotArtifact, SnapshotManifestV1


def bar() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "asset_id": "DEMO:AAA",
        "session_date": "2026-10-23",
        "open": "100.00",
        "high": "105.00",
        "low": "99.00",
        "close": "101.25",
        "adjusted_close": "101.25",
        "volume": 10000,
        "currency": "USD",
        "provider": "offline_fixture",
        "published_at": None,
        "available_at": "2026-10-23T21:05:00Z",
        "ingested_at": "2026-10-23T21:05:00Z",
        "availability_basis": "synthetic",
        "price_basis": "raw_as_traded",
        "volume_basis": "raw_shares",
        "quality_flags": ["SYNTHETIC_DATA_ONLY"],
    }


def manifest() -> dict[str, Any]:
    # These hashes are schema-only references, not claimed file-integrity evidence.
    return {
        "schema_version": 1,
        "mode": "synthetic_fixture",
        "source": {
            "provider": "offline_fixture",
            "adapter_version": "1",
            "normalization_version": "1",
            "rights_reference": None,
            "rights_status": "synthetic_owned",
            "capabilities_sha256": "1" * 64,
        },
        "price_basis": {
            "ohlc": "raw_as_traded",
            "adjusted_close": "fixture_v1",
            "volume": "raw_shares",
            "currency": "USD",
            "corporate_action_policy": "us_eod_next_open_v1",
        },
        "calendar": {
            "id": "XNYS",
            "timezone": "America/New_York",
            "version": "0" * 64,
            "artifact_path": "calendar.json",
        },
        "coverage": {
            "asset_ids": ["DEMO:AAA"],
            "first_session": "2026-10-23",
            "last_session": "2026-10-23",
            "latest_completed_session": "2026-10-23",
            "missing_sessions": [],
            "membership_basis": "synthetic",
        },
        "quality": "usable_with_warnings",
        "warnings": ["SYNTHETIC_DATA_ONLY"],
        "artifacts": [
            {
                "path": name + (".parquet" if name in {"assets", "bars"} else ".json"),
                "role": name,
                "format": "parquet" if name in {"assets", "bars"} else "json",
                "schema_version": 1,
                "sha256": ("1" if name == "provenance" else "0") * 64,
                "size_bytes": 10,
                "row_count": 1,
            }
            for name in ("assets", "bars", "calendar", "provenance", "universe")
        ],
    }


def test_bar_roundtrip_and_temporal_metadata() -> None:
    value = MarketBarV1.model_validate(bar())
    assert value.model_dump(mode="json") == bar()
    assert value.close == "101.25"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("low", "102"),
        ("high", "100"),
        ("volume", -1),
        ("volume", True),
        ("currency", "EUR"),
        ("close", "0"),
        ("schema_version", True),
        ("availability_basis", "published"),
        ("broker_account_id", "not-supported"),
    ],
)
def test_bad_market_bars_fail(field: str, value: object) -> None:
    data = bar()
    data[field] = value
    with pytest.raises(ValidationError):
        MarketBarV1.model_validate(data)


def test_unsupported_instrument_fails() -> None:
    with pytest.raises(ValidationError):
        AssetV1.model_validate(
            {
                "asset_id": "DEMO:AAA",
                "venue": "XNYS",
                "symbol": "AAA",
                "currency": "USD",
                "instrument": "option",
                "sector": "Unknown",
                "provider": "offline_fixture",
                "provider_id": "aaa",
            }
        )


def test_manifest_identity_uses_canonical_content_not_key_order() -> None:
    source = manifest()
    value = SnapshotManifestV1.model_validate(source)
    reordered = SnapshotManifestV1.model_validate(dict(reversed(list(source.items()))))
    assert reordered.manifest_hash() == value.manifest_hash()
    assert reordered.snapshot_id() == value.snapshot_id()
    source["artifacts"][0]["sha256"] = "2" * 64
    changed = SnapshotManifestV1.model_validate(source)
    assert changed.manifest_hash() != value.manifest_hash()
    assert changed.snapshot_id() != value.snapshot_id()


@pytest.mark.parametrize(
    "path", ["../outside", "/absolute", "a/../b", "a//b", "./a", "C:/file", "a\\b", "manifest.json"]
)
def test_lexically_unsafe_paths_rejected(path: str) -> None:
    data = manifest()["artifacts"][0]
    data["path"] = path
    with pytest.raises(ValidationError):
        SnapshotArtifact.model_validate(data)


def test_manifest_cross_references_and_fixture_warnings_required() -> None:
    for section, field, value in [
        ("calendar", "version", "2" * 64),
        ("source", "capabilities_sha256", "2" * 64),
        ("coverage", "membership_basis", "current_only"),
    ]:
        data = manifest()
        data[section][field] = value
        with pytest.raises(ValidationError):
            SnapshotManifestV1.model_validate(data)
    data = manifest()
    data["warnings"] = []
    with pytest.raises(ValidationError):
        SnapshotManifestV1.model_validate(data)
