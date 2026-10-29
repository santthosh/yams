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
