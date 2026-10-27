import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from backend.domain.common import JobV1
from backend.domain.experiment import ExperimentRunV1, MetricValue
from backend.domain.forecast import ForecastV1
from backend.domain.orders import PaperOrderBatchV1
from backend.domain.recommendation import FeatureValue, RecommendationV1

EXAMPLES = Path(__file__).parent / "examples"


def example(name: str) -> dict[str, Any]:
    result: dict[str, Any] = json.loads((EXAMPLES / name).read_text())
    return result


@pytest.mark.parametrize(
    ("model", "name"),
    [
        (RecommendationV1, "recommendation.json"),
        (ForecastV1, "forecast.json"),
        (PaperOrderBatchV1, "order_batch.json"),
        (ExperimentRunV1, "experiment.json"),
    ],
)
def test_payload_roundtrip_and_unknown_financial_keys(model: type[BaseModel], name: str) -> None:
    data = example(name)
    assert model.model_validate(data).model_dump(mode="json") == data
    data["brokerage_account"] = "not_supported"
    with pytest.raises(ValidationError):
        model.model_validate(data)


def test_complete_target_weights_and_duplicate_assets() -> None:
    data = example("recommendation.json")
    data["summary_action"] = "REBALANCE"
    data["target_weights"] = [
        {"asset_id": "DEMO:AAA", "weight": "0.123456789", "reason_codes": ["RISK_LIMIT"]}
    ]
    data["cash_target_weight"] = "0.876543211"
    assert RecommendationV1.model_validate(data).target_weights[0].weight == "0.123456789"
    data["cash_target_weight"] = "0.5"
    with pytest.raises(ValidationError):
        RecommendationV1.model_validate(data)
    data["target_weights"] *= 2
    with pytest.raises(ValidationError):
        RecommendationV1.model_validate(data)


def test_null_metrics_and_features_need_reasons() -> None:
    cases: list[tuple[type[BaseModel], dict[str, object]]] = [
        (MetricValue, {"value": None, "unavailable_reason": None}),
        (FeatureValue, {"name": "VOL60", "value": None, "unavailable_reason": None}),
    ]
    for model, data in cases:
        with pytest.raises(ValidationError):
            model.model_validate(data)
    assert MetricValue(value=None, unavailable_reason="ZERO_VARIANCE").value is None


def test_forecast_unavailable_has_no_invented_outcomes() -> None:
    data = example("forecast.json")
    data.update(status="unavailable", unavailable_reason="INSUFFICIENT_ALIGNED_HISTORY")
    with pytest.raises(ValidationError):
        ForecastV1.model_validate(data)
    data.update(proposed=None, hold_unchanged=None, median_return_delta_fraction=None)
    assert ForecastV1.model_validate(data).status == "unavailable"
    data["unavailable_reason"] = None
    with pytest.raises(ValidationError):
        ForecastV1.model_validate(data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("simulation_count", 100),
        ("cash_return_fraction", 0.01),
        ("median_return_delta_fraction", float("nan")),
        ("horizon_trading_sessions", 0),
        ("unavailable_reason", "COST_UNAVAILABLE"),
        ("fingerprint", None),
    ],
)
def test_available_forecast_rejects_missing_or_changed_assumptions(
    field: str, value: object
) -> None:
    data = example("forecast.json")
    data[field] = value
    with pytest.raises(ValidationError):
        ForecastV1.model_validate(data)


def test_forecast_requires_shared_asset_evidence_and_ordered_quantiles() -> None:
    data = example("forecast.json")
    data["proposed"]["p10_return_fraction"] = 0.1
    with pytest.raises(ValidationError):
        ForecastV1.model_validate(data)


def test_forecast_delta_uses_relative_float64_tolerance_without_hiding_wrong_delta() -> None:
    data = example("forecast.json")
    data["proposed"].update(
        p10_return_fraction=999999,
        median_return_fraction=1000000,
        p90_return_fraction=1000001,
        median_ending_value_usd="1000001000.00",
    )
    data["median_return_delta_fraction"] = 1000000.000001
    assert ForecastV1.model_validate(data).status == "available"
    data["median_return_delta_fraction"] = 1000000.01
    with pytest.raises(ValidationError, match="delta"):
        ForecastV1.model_validate(data)
    data = example("forecast.json")
    data["proposed_allocation"].update(
        weights=[{"asset_id": "DEMO:AAA", "weight": "0.2"}], cash_weight="0.8"
    )
    with pytest.raises(ValidationError, match="evidence"):
        ForecastV1.model_validate(data)


def test_partial_order_is_exact_and_can_be_terminal() -> None:
    data = example("order_batch.json")
    data.update(status="partially_filled", terminal=True, reason="INSUFFICIENT_CASH")
    order = data["orders"][0]
    order.update(
        status="partially_filled",
        terminal=True,
        filled_quantity="0.999000",
        pending_quantity="0.000000",
        cancelled_or_skipped_quantity="0.001000",
        reason="INSUFFICIENT_CASH",
    )
    assert PaperOrderBatchV1.model_validate(data).terminal is True
    order["status"] = "filled"
    with pytest.raises(ValidationError):
        PaperOrderBatchV1.model_validate(data)


def test_order_open_equality_and_quantity_conservation_fail() -> None:
    data = example("order_batch.json")
    data["eligible_open_at"] = data["approved_at"]
    with pytest.raises(ValidationError):
        PaperOrderBatchV1.model_validate(data)
    data = example("order_batch.json")
    data["orders"][0]["pending_quantity"] = "0.999999"
    with pytest.raises(ValidationError):
        PaperOrderBatchV1.model_validate(data)


def test_experiment_cannot_publish_partial_or_unexplained_failed_result() -> None:
    data = example("experiment.json")
    for status in ("completed", "failed"):
        data["status"] = status
        with pytest.raises(ValidationError):
            ExperimentRunV1.model_validate(data)
    data = example("experiment.json")
    data["inputs"]["end_session_exclusive"] = data["inputs"]["start_session"]
    with pytest.raises(ValidationError):
        ExperimentRunV1.model_validate(data)


def test_job_terminal_state_requires_result_or_error() -> None:
    data = {
        "id": "00000000-0000-4000-8000-000000000001",
        "kind": "diagnostic",
        "status": "queued",
        "attempts": 0,
        "max_attempts": 3,
        "progress": 0,
        "created_at": "2030-01-01T00:00:00Z",
        "updated_at": "2030-01-01T00:00:00Z",
        "result": None,
        "error": None,
    }
    assert JobV1.model_validate(data).status == "queued"
    data["status"] = "completed"
    with pytest.raises(ValidationError):
        JobV1.model_validate(data)
    data.update(
        progress=100,
        result={"kind": "diagnostic", "resource_id": None, "message": "Completed"},
    )
    assert JobV1.model_validate(data).status == "completed"


def test_experiment_completed_and_failed_states_roundtrip() -> None:
    data = example("experiment.json")
    artifact = {
        "id": data["id"],
        "sha256": "0" * 64,
        "schema_version": 1,
    }
    metrics = {
        name: {"value": None, "unavailable_reason": "INSUFFICIENT_OBSERVATIONS"}
        for name in (
            "cumulative_return_fraction",
            "annualized_return_fraction",
            "annualized_volatility_fraction",
            "max_drawdown_fraction",
            "turnover_fraction",
            "sharpe_ratio",
        )
    }
    data.update(
        status="completed",
        metrics={**metrics, "slippage_usd": "0.00", "fees_usd": "0.00", "trade_count": 0},
        curve_artifact=artifact,
        trade_artifact=artifact,
        reproducibility_manifest=artifact,
    )
    assert ExperimentRunV1.model_validate(data).model_dump(mode="json") == data
    data = example("experiment.json")
    data.update(
        status="failed",
        error={
            "code": "TIME_LIMIT",
            "message": "Attempt exceeded runtime budget.",
            "details": {},
            "retryable": False,
            "correlation_id": data["id"],
        },
    )
    assert ExperimentRunV1.model_validate(data).model_dump(mode="json") == data
