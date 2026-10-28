from fastapi.testclient import TestClient

from backend.api.main import create_app
from backend.persistence.database import Settings


def test_data_unavailable_uses_typed_envelope() -> None:
    with TestClient(create_app(Settings())) as client:
        response = client.get("/api/v1/data/snapshots?mode=synthetic_fixture")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "NOT_READY"


def test_invalid_mode_and_limit_are_validation_errors() -> None:
    with TestClient(create_app(Settings())) as client:
        for query in (
            "mode=live",
            "mode=synthetic_fixture&limit=101",
            "mode=synthetic_fixture&limit=0",
        ):
            response = client.get("/api/v1/data/snapshots?" + query)
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_refresh_requires_idempotency_key_and_mode_specific_inputs() -> None:
    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/v1/data/refresh", json={"schema_version": 1, "source_mode": "synthetic_fixture"}
        )
        assert response.status_code == 422
