import json
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.exceptions import HTTPException

from backend.api.main import create_app
from backend.api.openapi import export
from backend.domain.common import PageRequest
from backend.domain.strategy import StrategyConfigV1


@pytest.mark.parametrize("limit", [0, 101, -1, True, "25"])
def test_pagination_rejects_invalid_limits(limit: object) -> None:
    with pytest.raises(ValidationError):
        PageRequest.model_validate({"limit": limit})


def test_pagination_defaults_bounds_and_opaque_cursor() -> None:
    assert PageRequest().limit == 25
    assert PageRequest(limit=100, cursor="opaque-abc_123").limit == 100
    with pytest.raises(ValidationError):
        PageRequest(cursor="../../anything")


def test_raw_json_contract_route_rejects_duplicates_and_lost_precision() -> None:
    app = create_app()

    @app.post("/contract-probe")
    def validate(config: StrategyConfigV1) -> dict[str, str]:
        return {"hash": config.config_hash()}

    data = (Path(__file__).parent / "examples/strategy.json").read_text()
    client = TestClient(app)
    good = client.post(
        "/contract-probe", content=data, headers={"content-type": "application/json"}
    )
    assert good.status_code == 200
    for bad in (
        data.replace('"schema_version": 1,', '"schema_version":1,"schema_version":1,'),
        data.replace('"momentum_long": 0.60', '"momentum_long": 0.60000000000000000001'),
        data.replace('"momentum_long": 0.60', '"momentum_long": NaN'),
    ):
        response = client.post(
            "/contract-probe", content=bad, headers={"content-type": "application/json"}
        )
        assert response.status_code == 422
        body = response.json()
        assert set(body) == {"error"}
        assert body["error"]["code"] == "VALIDATION_ERROR"
        assert set(body["error"]) == {"code", "message", "details", "retryable", "correlation_id"}
        UUID(body["error"]["correlation_id"])
        assert "Risk-Adjusted Momentum" not in response.text
        assert body["error"]["details"]["field_paths"]


def test_method_error_preserves_status_and_allow_header() -> None:
    response = TestClient(create_app()).post("/livez")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"
    assert response.headers["allow"] == "GET"


def test_internal_errors_never_expose_exception_payloads(caplog: pytest.LogCaptureFixture) -> None:
    app = create_app()

    @app.get("/broken-probe")
    def broken() -> None:
        raise RuntimeError("secret-provider-token")

    response = TestClient(app, raise_server_exceptions=False).get("/broken-probe")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "secret-provider-token" not in response.text
    assert response.json()["error"]["correlation_id"] in caplog.text
    assert "secret-provider-token" not in caplog.text


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (400, "VALIDATION_ERROR"),
        (401, "HTTP_ERROR"),
        (409, "STATE_CONFLICT"),
        (422, "VALIDATION_ERROR"),
        (429, "LIMIT_EXCEEDED"),
        (503, "PROVIDER_UNAVAILABLE"),
    ],
)
def test_http_exception_keeps_status_without_detail_leak(status: int, code: str) -> None:
    app = create_app()

    @app.get("/http-probe")
    def broken() -> None:
        raise HTTPException(status, "secret-provider-token", headers={"Retry-After": "2"})

    response = TestClient(app).get("/http-probe")
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert "secret-provider-token" not in response.text
    assert response.headers["retry-after"] == "2"
    assert response.json()["error"]["retryable"] is (status == 503)


def test_export_is_deterministic_and_detects_changed_schema(tmp_path: Path) -> None:
    export(tmp_path, check=False)
    export(tmp_path, check=True)
    schema = tmp_path / "contracts/schemas.json"
    original = schema.read_bytes()
    modified = json.loads(original)
    modified["StrategyConfigV1.validation"]["properties"]["schema_version"]["const"] = 99
    schema.write_text(json.dumps(modified))
    with pytest.raises(SystemExit, match="Contract drift"):
        export(tmp_path, check=True)
    export(tmp_path, check=False)
    assert schema.read_bytes() == original


def test_openapi_does_not_activate_future_handlers() -> None:
    app = create_app()
    schema = app.openapi()
    assert set(schema["paths"]) == {
        "/livez",
        "/api/v1/health",
        "/api/v1/workspace",
        "/api/v1/portfolios",
        "/api/v1/portfolios/{portfolio_id}",
        "/api/v1/portfolios/{portfolio_id}/transactions",
        "/api/v1/portfolios/{portfolio_id}/recommendations",
        "/api/v1/recommendations/{recommendation_id}",
        "/api/v1/forecasts/{forecast_id}",
        "/api/v1/recommendations/{recommendation_id}/apply",
        "/api/v1/recommendations/{recommendation_id}/apply-result",
        "/api/v1/recommendations/{recommendation_id}/dismiss",
        "/api/v1/order-batches/{batch_id}",
        "/api/v1/order-batches/{batch_id}/cancel",
        "/api/v1/order-batches/{batch_id}/advance-fixture",
        "/api/v1/jobs/{job_id}",
        "/api/v1/jobs/{job_id}/cancel",
        "/api/v1/experiments",
        "/api/v1/experiments/{experiment_id}",
        "/api/v1/experiments/{experiment_id}/series",
        "/api/v1/experiments/{experiment_id}/trades",
        "/api/v1/data/snapshots",
        "/api/v1/data/refresh",
        "/api/v1/data/assets",
        "/api/v1/data/health",
        "/api/v1/strategies",
        "/api/v1/strategies/{strategy_id}",
        "/api/v1/strategies/{strategy_id}/versions",
        "/api/v1/strategy-evaluations",
        "/api/v1/strategy-evaluations/{evaluation_id}",
    }
    components = schema["components"]["schemas"]
    for name in (
        "MarketBarV1",
        "ForecastV1",
        "RecommendationV1",
        "PaperOrderBatchV1",
        "ExperimentRunV1",
    ):
        assert name in components
    client = TestClient(app)
    assert client.get("/api/v1/forecasts/anything").status_code == 422
    assert (
        client.post(
            "/api/v1/recommendations/11111111-1111-4111-8111-111111111111/apply"
        ).status_code
        == 422
    )


def test_experiment_schema_keeps_exact_uint64_seed_and_no_dangling_refs() -> None:
    schema = create_app().openapi()
    components = schema["components"]["schemas"]
    assert (
        components["ExperimentRequest"]["properties"]["random_seed"]["maximum"]
        == 18446744073709551615
    )
    revision = components["ApplyRecommendationRequest"]["properties"]["expected_revision"][
        "maximum"
    ]
    assert type(revision) is int and revision == 9223372036854775807
    for name in ("RecommendationRequest", "ForecastV1"):
        bound = components[name]["properties"]["seed"]["maximum"]
        assert type(bound) is int and bound == 18446744073709551615

    def references(value: object) -> None:
        if isinstance(value, dict):
            if "$ref" in value:
                assert value["$ref"].rsplit("/", 1)[-1] in components
            for nested in value.values():
                references(nested)
        elif isinstance(value, list):
            for nested in value:
                references(nested)

    references(schema)


def test_legacy_report_projection_keeps_evidence_and_rejects_changed_rerun_text() -> None:
    from backend.domain.experiment_api import ExperimentDetailV1
    from backend.domain.types import canonical_json, load_json

    root = Path(__file__).resolve().parents[3]
    legacy = json.loads((root / "apps/web/tests/experiment-transport.json").read_bytes())
    assert isinstance(legacy, dict) and isinstance(legacy["completed"], dict)
    sample = legacy["completed"]
    actual = ExperimentDetailV1.model_validate(sample)
    assert actual.engine_version == sample["engine_version"]
    assert (
        actual.inputs_canonical_json
        == canonical_json(load_json(json.dumps(sample["inputs"]))).decode()
    )
    assert (
        actual.curve_artifact is not None
        and actual.curve_artifact.sha256 == sample["curve_artifact"]["sha256"]
    )
    for text in (
        actual.inputs_canonical_json.replace('"random_seed":42', '"random_seed":43'),
        " " + actual.inputs_canonical_json,
    ):
        with pytest.raises(ValidationError):
            ExperimentDetailV1.model_validate(sample | {"inputs_canonical_json": text})
