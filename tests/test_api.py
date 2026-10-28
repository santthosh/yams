"""End-to-end API flow on the committed sample snapshot, in a temporary runtime dir (no network)."""

import importlib
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("YAMS_RUNTIME_DIR", str(tmp_path))
    import app.config
    import app.data
    import app.main

    importlib.reload(app.config)
    importlib.reload(app.data)
    importlib.reload(app.main)
    with TestClient(app.main.app) as c:
        yield c


def test_recommend_apply_and_idempotency(client):
    p0 = client.get("/api/portfolio").json()
    assert p0["cash"] == 1000 and p0["holdings"] == []

    rec = client.post("/api/recommendations").json()
    assert rec["status"] == "ready" and rec["positions"]
    weights = sum(p["weight"] for p in rec["positions"]) + rec["cash_target_weight"]
    assert abs(weights - 1) < 1e-9
    assert all(p["explanation"] for p in rec["positions"])
    assert rec["forecast"]["status"] == "available"
    assert "made money" in rec["backtest"]["verdict"] or "lost money" in rec["backtest"]["verdict"]

    r = client.post(f"/api/recommendations/{rec['id']}/apply")
    assert r.status_code == 200
    p1 = r.json()["portfolio"]
    assert p1["holdings"] and p1["cash"] >= 0
    assert abs(p1["total"] - 1000) < 5  # only slippage lost at the same close

    again = client.post(f"/api/recommendations/{rec['id']}/apply")
    assert again.status_code == 409 and again.json()["error"]["code"] == "STATE_CONFLICT"

    # Ledger conservation: derived cash == initial + sum of cash deltas.
    import app.main

    led = app.main.ledger()
    deltas = sum(Decimal(t["cash_delta"]) for t in led.trades(1000))
    assert led.state()[1] == Decimal("1000.00") + deltas

    # A follow-up recommendation is relative to the holdings: mostly HOLDs, no re-buy of everything.
    rec2 = client.post("/api/recommendations").json()
    assert rec2["summary_action"] == "HOLD"


def test_stale_recommendation_rejected_after_other_apply(client):
    a = client.post("/api/recommendations").json()
    b = client.post("/api/recommendations").json()
    assert client.post(f"/api/recommendations/{a['id']}/apply").status_code == 200
    assert client.post(f"/api/recommendations/{b['id']}/apply").status_code == 409


def test_pages_render(client):
    assert client.get("/").status_code == 200
    rec = client.post("/api/recommendations").json()
    page = client.get(f"/recommendations/{rec['id']}")
    assert page.status_code == 200 and "Apply paper trades" in page.text
    assert client.get("/backtest").status_code == 200


def test_reset_validates(client):
    assert client.post("/api/portfolio/reset", json={"initial_cash": 5}).status_code == 422
    r = client.post("/api/portfolio/reset", json={"initial_cash": 2500})
    assert r.status_code == 200 and r.json()["cash"] == 2500
