from fastapi.testclient import TestClient

from backend.api.main import create_app


def test_liveness_is_paper_only_without_database() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/livez")
    assert response.status_code == 200
    assert response.json() == {"status": "alive", "paper_only": True}


def test_unimplemented_routes_do_not_claim_readiness_or_financial_results() -> None:
    with TestClient(create_app()) as client:
        for path in ("/api/v1/recommendations", "/missing"):
            response = client.get(path)
            assert response.status_code == 404
            error = response.json()["error"]
            assert error["code"] == "NOT_FOUND"
            assert error["retryable"] is False
            assert error["details"] == {}


def test_account_route_is_explicitly_unavailable_without_database() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/portfolios")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "NOT_READY"
        assert "cash_usd" not in response.json()


def test_schedule_status_without_database_is_explicitly_unavailable() -> None:
    from uuid import uuid4

    from backend.persistence.database import Settings

    with TestClient(create_app(Settings(None))) as client:
        response = client.get(f"/api/v1/portfolios/{uuid4()}/schedule")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "NOT_READY"
        assert "next_review_due_at" not in response.json()


def test_schedule_transport_is_readonly_and_validates_portfolio_identity() -> None:
    from uuid import uuid4

    from backend.persistence.database import Settings

    with TestClient(create_app(Settings(None))) as client:
        assert client.get("/api/v1/portfolios/invalid/schedule").status_code == 422
        assert (
            client.post(
                f"/api/v1/portfolios/{uuid4()}/schedule", json={"clock": "future"}
            ).status_code
            == 405
        )
