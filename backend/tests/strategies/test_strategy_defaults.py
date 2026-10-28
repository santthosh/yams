"""Independent FIX-01 default parameters and visibly invalid package cases."""

import json
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.api.main import create_app
from backend.domain.registry import strategy_name
from backend.strategies import registry

ROOT = Path(__file__).resolve().parents[3] / "data/fixtures"


def test_packaged_default_matches_independent_fixture() -> None:
    config = registry.default_config()
    fixture = json.loads((ROOT / "fix-01/case.json").read_text())
    assert config.config_hash() == fixture["expected"]["config_sha256"]
    assert config.canonical_bytes() == (ROOT / "fix-01/strategy.canonical.json").read_bytes()
    assert UUID(str(registry.DEFAULT_STRATEGY_ID)) != UUID(str(registry.DEFAULT_VERSION_ID))
    assert config.portfolio.max_positions == 8
    assert config.portfolio.max_sector_weight == "0.4"
    assert config.portfolio.max_position_weight == "0.2"
    assert config.portfolio.min_cash_weight == "0.05"


def test_missing_invalid_and_changed_defaults_fail_visibly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(registry, "files", lambda _: tmp_path)
    with pytest.raises(FileNotFoundError):
        registry.default_config()
    path = tmp_path / "default_momentum.json"
    value = json.loads((ROOT / "fix-01/strategy.canonical.json").read_text())
    value["signals"]["kind"] = "execute_python"
    path.write_text(json.dumps(value))
    with pytest.raises(ValidationError):
        registry.default_config()
    value["signals"]["kind"] = "risk_adjusted_momentum"
    value["portfolio"]["max_positions"] = 9
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="ratified"):
        registry.default_config()


def test_name_normalization_and_unavailable_api() -> None:
    assert strategy_name("\u2003Straße\u2003") == "Straße"
    assert strategy_name("Straße").casefold() == strategy_name("STRASSE").casefold()
    for value in ["", "  ", "bad\x00name", "bad\ud800name", "x" * 121]:
        with pytest.raises(ValueError):
            strategy_name(value)
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/strategies")
        assert response.status_code == 503 and response.json()["error"]["code"] == "NOT_READY"
        assert client.get("/api/v1/strategies?limit=101").status_code == 422
        assert client.get("/api/v1/strategies?cursor=not-uuid").status_code == 422
        assert client.post("/api/v1/strategies", json={}).status_code == 405
