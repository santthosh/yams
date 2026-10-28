"""End-to-end API flow on the committed sample snapshot, in a temporary runtime dir (no network)."""

import importlib
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("YAMS_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("YAMS_LIVE_QUOTES", "0")  # tests never touch the network
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
    statuses = {r["id"]: r["status"] for r in client.get("/api/recommendations").json()}
    assert statuses == {a["id"]: "applied", b["id"]: "stale"}
    assert "Apply paper trades</button>" not in client.get(f"/recommendations/{b['id']}").text


def test_pages_render(client):
    assert client.get("/").status_code == 200
    rec = client.post("/api/recommendations").json()
    page = client.get(f"/recommendations/{rec['id']}")
    assert page.status_code == 200 and page.text.count("Apply paper trades</button>") == 2  # top + section 6
    assert "not applied yet" in client.get("/").text
    assert client.get("/backtest").status_code == 200


def test_reset_validates(client):
    assert client.post("/api/portfolio/reset", json={"initial_cash": 5}).status_code == 422
    r = client.post("/api/portfolio/reset", json={"initial_cash": 2500})
    assert r.status_code == 200 and r.json()["cash"] == 2500


def test_live_quotes_value_the_dashboard_but_not_decisions(client, monkeypatch):
    import app.data
    import app.main

    rec = client.post("/api/recommendations").json()
    client.post(f"/api/recommendations/{rec['id']}/apply")
    md = app.main.md()
    next_day = datetime.fromisoformat(md.as_of).replace(hour=11, tzinfo=app.data.NY) + timedelta(days=1)

    def fake(tickers):
        return {t: (md.latest_close(t) * 1.01, next_day) for t in tickers}

    monkeypatch.setattr(app.data, "LIVE_QUOTES", True)
    monkeypatch.setattr(app.data, "fetch_quotes", fake)
    p = client.get("/api/portfolio").json()
    live = p["live"]
    assert live["status"] == "live" and abs(live["spy_day_return"] - 0.01) < 1e-9
    invested = p["total"] - p["cash"]
    assert abs(live["total"] - (p["cash"] + invested * 1.01)) < 1e-6
    assert abs(live["day_change"] - invested * 0.01) < 1e-6
    assert "chip live" in client.get("/").text
    # Decisions still use the daily close: same prices, nothing to trade.
    rec2 = client.post("/api/recommendations").json()
    assert rec2["summary_action"] == "HOLD" and all(a["price"] == md.latest_close(a["ticker"]) for a in rec2["actions"])


def test_live_quotes_fall_back_to_closes(client, monkeypatch):
    import app.data
    import app.main

    md = app.main.md()
    same_day = datetime.fromisoformat(md.as_of).replace(hour=15, tzinfo=app.data.NY)
    monkeypatch.setattr(app.data, "LIVE_QUOTES", True)
    monkeypatch.setattr(app.data, "_quotes", {"key": None, "at": 0.0, "data": {}})
    monkeypatch.setattr(app.data, "fetch_quotes", lambda ts: {t: (1.0, same_day) for t in ts})
    assert client.get("/api/portfolio").json()["live"]["status"] == "closed"

    def offline(_):
        raise OSError("no network")

    monkeypatch.setattr(app.data, "_quotes", {"key": None, "at": 0.0, "data": {}})
    monkeypatch.setattr(app.data, "fetch_quotes", offline)
    p = client.get("/api/portfolio").json()
    assert p["live"]["status"] == "unavailable" and p["total"] == 1000
    assert "Live prices unavailable" in client.get("/").text


def test_backtest_start_date(client):
    default = client.get("/api/backtest").json()
    custom = client.get("/api/backtest", params={"start": "2024-06-03"}).json()
    assert custom["start"] == "2024-06-03" and custom["end"] == default["end"]
    assert custom["start"] > default["start"]
    assert client.get("/api/backtest", params={"start": "June 3"}).status_code == 422
    page = client.get("/backtest", params={"start": "2024-06-03"})
    assert page.status_code == 200 and 'value="2024-06-03"' in page.text
    assert "Start date must look like" in client.get("/backtest", params={"start": "nope"}).text
