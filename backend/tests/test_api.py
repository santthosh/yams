from fastapi.testclient import TestClient

from backend.api.main import create_app


def test_liveness_is_paper_only_without_database() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/livez")
    assert response.status_code == 200
    assert response.json() == {"status": "alive", "paper_only": True}


def test_unimplemented_routes_do_not_claim_readiness_or_financial_results() -> None:
    with TestClient(create_app()) as client:
        for path in ("/api/v1/health", "/api/v1/portfolios", "/missing"):
            response = client.get(path)
            assert response.status_code == 404
            assert response.json() == {"detail": "Not Found"}
