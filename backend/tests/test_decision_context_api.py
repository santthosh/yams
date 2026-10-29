"""Readonly routes are explicit when storage is unavailable."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.api.main import create_app
from backend.persistence.database import Settings


@pytest.mark.parametrize(
    "path", ["portfolios/{id}/decision-inputs", "recommendations/{id}/approval-preview"]
)
def test_context_is_readonly_and_requires_available_storage(path: str) -> None:
    with TestClient(create_app(Settings(None))) as client:
        url = "/api/v1/" + path.format(id=uuid4())
        assert client.get(url).status_code == 503
        assert client.post(url, json={}).status_code == 405
