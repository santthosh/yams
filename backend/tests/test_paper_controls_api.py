"""Closed public authorization contracts; no caller prices, timestamps or private keys."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.api.main import create_app
from backend.persistence.database import Settings


@pytest.mark.parametrize("value", [True, 0, -1, 1.0, "1", 9223372036854775808])
def test_approval_revision_is_a_positive_strict_int64(value: object) -> None:
    with TestClient(create_app(Settings(None))) as client:
        response = client.post(
            f"/api/v1/recommendations/{uuid4()}/apply",
            json={"expected_revision": value},
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert response.status_code == 422


@pytest.mark.parametrize("suffix", ["apply", "apply-result"])
def test_approval_requires_uuid_key(suffix: str) -> None:
    with TestClient(create_app(Settings(None))) as client:
        path = f"/api/v1/recommendations/{uuid4()}/{suffix}"
        call = client.post if suffix == "apply" else client.get
        kwargs = {"json": {"expected_revision": 1}} if suffix == "apply" else {}
        assert call(path, **kwargs).status_code == 422
        assert (
            call(path, headers={"Idempotency-Key": "secret-invalid"}, **kwargs).status_code == 422
        )


@pytest.mark.parametrize(
    "resource,action",
    [
        ("recommendations", "dismiss"),
        ("order-batches", "cancel"),
        ("order-batches", "advance-fixture"),
    ],
)
def test_control_body_rejects_clock_and_price_overrides(resource: str, action: str) -> None:
    with TestClient(create_app(Settings(None))) as client:
        response = client.post(
            f"/api/v1/{resource}/{uuid4()}/{action}",
            json={"approved_at": "2028-07-18T12:00:00Z", "price": "1"},
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert response.status_code == 422
        assert "2028-07-18" not in response.text


def test_valid_paper_controls_explicitly_unavailable_without_database() -> None:
    with TestClient(create_app(Settings(None))) as client:
        response = client.post(
            f"/api/v1/recommendations/{uuid4()}/apply",
            json={"expected_revision": 1},
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert response.status_code == 503 and response.json()["error"]["code"] == "NOT_READY"
