from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.main import create_app
from backend.persistence.bootstrap import main as bootstrap_main
from backend.persistence.database import Settings, database_engine
from backend.persistence.readiness import fixture_metadata


def test_missing_database_keeps_liveness_but_fails_readiness() -> None:
    with TestClient(create_app(Settings())) as client:
        assert client.get("/livez").status_code == 200
        response = client.get("/api/v1/health")
        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "not_ready"
        assert body["database"]["reason"] == "DATABASE_UNAVAILABLE"
        assert body["fixtures"]["status"] == "ready"
        assert body["fixture_metadata"]["label"] == "SYNTHETIC_DATA_ONLY"
        workspace = client.get("/api/v1/workspace")
        assert workspace.status_code == 503
        assert workspace.json()["error"]["code"] == "NOT_READY"


def test_invalid_configuration_and_missing_fixtures_never_leak_secrets(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    settings = Settings(database_url="invalid://secret-password", fixture_root=tmp_path)
    assert "secret-password" not in repr(settings)
    with pytest.raises(ValueError, match="Invalid PostgreSQL configuration") as error:
        database_engine(settings.database_url or "")
    assert "secret-password" not in str(error.value)
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/health")
        assert response.status_code == 503
        assert "secret-password" not in response.text
        assert response.json()["fixture_metadata"] is None
        assert response.json()["fixtures"]["reason"] == "FIXTURES_UNAVAILABLE"
        assert response.json()["database"]["reason"] == "DATABASE_MISCONFIGURED"
    assert "DATABASE_URL is set but invalid" in caplog.text
    assert "secret-password" not in caplog.text


def test_fixture_metadata_checks_complete_artifacts(tmp_path: Path) -> None:
    import shutil

    shutil.copytree(Settings.fixture_root / "snapshot", tmp_path / "snapshot")
    assert fixture_metadata(tmp_path).asset_count == 5
    bars = tmp_path / "snapshot/bars.json"
    bars.write_bytes(bars.read_bytes() + b" ")
    with pytest.raises(ValueError, match="integrity"):
        fixture_metadata(tmp_path)


def test_bootstrap_failure_diagnostic_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "invalid://secret-password")
    with pytest.raises(SystemExit) as failure:
        bootstrap_main()
    assert "error_type=ValueError" in str(failure.value)
    assert "secret-password" not in str(failure.value)
