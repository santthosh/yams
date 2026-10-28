from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from backend.api.main import create_app
from backend.jobs.queue import Queue
from backend.jobs.worker import Worker
from backend.persistence.bootstrap import bootstrap
from backend.persistence.database import Settings
from backend.tests.integration.test_bootstrap import database as database
from backend.tests.market_data.test_files import IDENTITY

pytestmark = pytest.mark.integration


def test_refresh_health_search_and_failed_refresh_preserve_snapshot(
    database: Engine, tmp_path: Path
) -> None:
    bootstrap(database)
    settings = Settings(
        database_url=database.url.render_as_string(hide_password=False), artifact_root=tmp_path
    )
    payload = {
        "schema_version": 1,
        "source_mode": "synthetic_fixture",
        "expected_manifest_hash": IDENTITY,
    }
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/data/health?mode=synthetic_fixture").json()["status"] == "empty"
        key = str(uuid4())
        response = client.post(
            "/api/v1/data/refresh", json=payload, headers={"Idempotency-Key": key}
        )
        assert response.status_code == 202
        repeated = client.post(
            "/api/v1/data/refresh", json=payload, headers={"Idempotency-Key": key}
        )
        assert repeated.json()["id"] == response.json()["id"]
        assert Worker(Queue(database), artifact_root=tmp_path).run_once()
        health = client.get("/api/v1/data/health?mode=synthetic_fixture").json()
        assert health["status"] == "ready" and health["freshness"] == "synthetic"
        snapshot = health["current_snapshot"]
        snapshots = client.get("/api/v1/data/snapshots?mode=synthetic_fixture").json()
        assert snapshots["items"][0]["id"] == snapshot["id"]
        params = {"mode": "synthetic_fixture", "snapshot_id": snapshot["id"], "limit": 2}
        first = client.get("/api/v1/data/assets", params=params).json()
        assert len(first["items"]) == 2 and first["next_cursor"]
        second = client.get(
            "/api/v1/data/assets", params={**params, "cursor": first["next_cursor"]}
        ).json()
        assert set(row["asset_id"] for row in first["items"]).isdisjoint(
            row["asset_id"] for row in second["items"]
        )
        assert (
            client.get("/api/v1/data/assets", params={**params, "query": "no-such-asset"}).json()[
                "items"
            ]
            == []
        )
        assert (
            client.get(
                "/api/v1/data/assets",
                params={**params, "query": "AAA", "cursor": first["next_cursor"]},
            ).status_code
            == 422
        )
        assert (
            client.get(
                "/api/v1/data/assets", params={**params, "mode": "research_market_data"}
            ).status_code
            == 404
        )
        queue = Queue(database)
        queue.enqueue("refresh_market_data", payload, uuid4())
        lease = queue.claim("failure-test")
        assert lease is not None
        queue.fail(lease, "PROVIDER_UNAVAILABLE", reason="PROVIDER_RIGHTS_UNVERIFIED")
        failed = client.get("/api/v1/data/health?mode=synthetic_fixture").json()
        assert failed["status"] == "failed" and failed["freshness"] == "refresh_failed"
        assert failed["current_snapshot"]["id"] == snapshot["id"]
        assert failed["latest_job"]["error"]["details"]["reason"] == "PROVIDER_RIGHTS_UNVERIFIED"
        research = client.get("/api/v1/data/health?mode=research_market_data").json()
        assert research["current_snapshot"] is None and research["latest_job"] is None
