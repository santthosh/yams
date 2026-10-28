"""Publication validation fails before storage; no implicit defaults or executable rules."""

from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.api.main import create_app
from backend.strategies.registry import default_config


@pytest.mark.parametrize("name", ["", "   ", "x" * 121, "bad\nname", 123])
def test_invalid_name(name: object) -> None:
    response = TestClient(create_app()).post(
        "/api/v1/strategies",
        json={"name": name, "config": default_config().model_dump(mode="json")},
    )
    assert response.status_code == 422 and response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("mutation", ["operator", "cap", "unknown", "missing"])
def test_invalid_config_is_rejected_on_both_publication_routes(mutation: str) -> None:
    config = deepcopy(default_config().model_dump(mode="json"))
    if mutation == "operator":
        config["signals"]["kind"] = "eval_arbitrary_code"
    elif mutation == "cap":
        config["portfolio"]["max_position_weight"] = "1.1"
    elif mutation == "unknown":
        config["arbitrary_code"] = "private untrusted input"
    else:
        del config["execution_policy"]
    client = TestClient(create_app())
    for path, body in [
        ("/api/v1/strategies", {"name": "Valid name", "config": config}),
        (f"/api/v1/strategies/{uuid4()}/versions", config),
    ]:
        response = client.post(path, json=body)
        assert (
            response.status_code == 422 and response.json()["error"]["code"] == "VALIDATION_ERROR"
        )
        assert "private untrusted input" not in response.text


def test_unconfigured_storage_has_safe_error_for_all_new_routes() -> None:
    client = TestClient(create_app())
    config = default_config().model_dump(mode="json")
    path = f"/api/v1/strategies/{uuid4()}"
    results = [
        client.post("/api/v1/strategies", json={"name": "Valid", "config": config}),
        client.get(path),
        client.get(path + "/versions"),
        client.post(path + "/versions", json=config),
    ]
    assert all(
        result.status_code == 503 and result.json()["error"]["code"] == "NOT_READY"
        for result in results
    )
