"""Actual PostgreSQL/worker/API proofs; all accounting inputs are synthetic."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from backend.api.main import create_app
from backend.domain.recommendation_api import RecommendationRequest
from backend.jobs.handlers.evaluate_portfolio import evaluate_portfolio
from backend.jobs.queue import Queue
from backend.jobs.worker import Worker
from backend.market_data.snapshots import PublicationFenceError
from backend.persistence.database import Settings
from backend.persistence.models.ledger import RecommendationReference
from backend.portfolio.ledger import digest
from backend.portfolio.recommendations import admit_recommendation, seal_recommendation
from backend.tests.integration.test_bootstrap import database as database
from backend.tests.integration.test_forecasts import prepare

pytestmark = pytest.mark.integration


def request_for(database: Engine, root: Path) -> tuple[UUID, RecommendationRequest]:
    inputs = prepare(database, root)
    return inputs.portfolio_id, RecommendationRequest(
        as_of_session=inputs.as_of_session,
        snapshot_id=inputs.snapshot_id,
        clock_mode="synthetic_replay",
        seed=18446744073709551615,
    )


def test_actual_recommendation_worker_forecast_and_readonly_api(
    database: Engine, tmp_path: Path
) -> None:
    owner, request = request_for(database, tmp_path)
    settings = Settings(database.url.render_as_string(hide_password=False), artifact_root=tmp_path)
    key = str(uuid4())
    with TestClient(create_app(settings)) as client:
        path = f"/api/v1/portfolios/{owner}/recommendations"
        response = client.post(
            path,
            content=request.model_dump_json(),
            headers={"Idempotency-Key": key, "Content-Type": "application/json"},
        )
        assert response.status_code == 202, response.text
        accepted = response.json()
        identity = accepted["recommendation_id"]
        assert (
            client.post(
                path,
                content=request.model_dump_json(),
                headers={"Idempotency-Key": key, "Content-Type": "application/json"},
            ).json()
            == accepted
        )
        changed = request.model_copy(update={"seed": 0})
        assert (
            client.post(
                path,
                content=changed.model_dump_json(),
                headers={"Idempotency-Key": key, "Content-Type": "application/json"},
            ).status_code
            == 409
        )
        page = client.get(path).json()
        assert len(page["items"]) == 1 and page["items"][0]["status"] == "queued"
        assert "18446744073709551615" in page["items"][0]["inputs_canonical_json"]
        pending = client.get(f"/api/v1/recommendations/{identity}")
        assert (
            pending.status_code == 409
            and pending.json()["error"]["details"]["job_id"] == accepted["job_id"]
        )
        queue = Queue(database)
        assert Worker(queue, artifact_root=tmp_path).run_once()
        analysis = client.get(f"/api/v1/recommendations/{identity}")
        assert analysis.status_code == 200, analysis.text
        initial = analysis.json()
        assert initial["computed_at"].endswith("Z")
        assert initial["summary_action"] == "BUY" and initial["is_current"]
        assert initial["forecast"] is None and initial["forecast_job"]["status"] == "queued"
        forecast_path = f"/api/v1/forecasts/{initial['forecast_id']}"
        pending_forecast = client.get(forecast_path)
        assert pending_forecast.status_code == 409
        assert (
            pending_forecast.json()["error"]["details"]["job_id"] == initial["forecast_job"]["id"]
        )
        assert Worker(queue, artifact_root=tmp_path).run_once()
        forecast = client.get(forecast_path)
        assert forecast.status_code == 200, forecast.text
        f = forecast.json()
        assert f["status"] == "available" and f["seed"] == 18446744073709551615
        assert f["hold_unchanged"]["median_ending_value_usd"] == "1000.00"
        assert f["hold_unchanged"]["probability_of_loss"] == 0
        final = client.get(f"/api/v1/recommendations/{identity}").json()
        assert final["forecast"] == f and final["forecast_job"]["status"] == "completed"
        assert {row["asset_id"]: row["estimated_quantity"] for row in final["actions"]} == {
            "SYN:AAA": "2.857142",
            "SYN:BBB": "2.857142",
            "SYN:CCC": "2.985074",
        }
        assert final["estimated_total_trade_cost_usd"] == "0.60"
        assert len(final["candidates"]) == 5 and any(
            row["exclusion_reasons"] for row in final["candidates"]
        )
        assert "18446744073709551615" in final["forecast_inputs_canonical_json"]
        assert final["inputs_canonical_json"] == initial["inputs_canonical_json"]
        for field in (
            "actions",
            "candidates",
            "target_weights",
            "created_at",
            "computed_at",
            "strategy_evidence",
        ):
            assert final[field] == initial[field]
        assert client.get(f"/api/v1/recommendations/{uuid4()}").status_code == 404
        assert client.get(f"/api/v1/forecasts/{uuid4()}").status_code == 404
        assert client.post(forecast_path, json={"initial_value_usd": "1.00"}).status_code == 405
        assert (
            client.post(
                path, json=request.model_dump(mode="json") | {"approved_at": "2028-07-18T12:30:00Z"}
            ).status_code
            == 422
        )
        assert client.get(path + "?limit=0").status_code == 422
        assert client.get(path + "?cursor=invalid").status_code == 422
    with database.connect() as connection:
        assert connection.execute(
            text("SELECT cash_usd,revision,last_sequence FROM paper_portfolio WHERE id=:id"),
            {"id": owner},
        ).one() == (1000, 1, 1)
        for table, count in [
            ("ledger_event", 1),
            ("paper_position", 0),
            ("paper_fill", 0),
            ("paper_order", 0),
            ("recommendation", 1),
            ("recommendation_run", 1),
            ("recommendation_publication", 1),
            ("forecast", 1),
            ("forecast_artifact", 1),
        ]:
            assert connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == count
    with Session(database) as session:
        row = session.get(RecommendationReference, UUID(identity))
        assert row is not None and digest(row.content) == row.content_sha256
        assert row.content["execution_intent"]["orders"]


@pytest.mark.parametrize("condition", ["cancel", "expired"])
def test_recommendation_cancel_fence_and_immutable_admission(
    database: Engine, tmp_path: Path, condition: str
) -> None:
    owner, request = request_for(database, tmp_path)
    accepted = admit_recommendation(database, tmp_path, owner, request)
    queue = Queue(database)
    lease = queue.claim("recommendation-cancel-proof")
    assert lease is not None and lease.job_id == accepted.job_id
    from multiprocessing import get_context

    encoded = evaluate_portfolio(lease.payload, get_context("spawn").Event(), root=tmp_path)
    if condition == "cancel":
        queue.cancel(lease.job_id)
    else:
        with database.begin() as connection:
            connection.execute(
                text(
                    "UPDATE job SET attempt_deadline=clock_timestamp()-interval '1 second' "
                    "WHERE id=:id"
                ),
                {"id": lease.job_id},
            )
    with pytest.raises(PublicationFenceError):
        seal_recommendation(queue, lease, encoded)
    with database.connect() as connection:
        for table in ("recommendation", "recommendation_publication", "forecast"):
            assert connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0
        assert (
            connection.execute(
                text("SELECT cash_usd FROM paper_portfolio WHERE id=:id"), {"id": owner}
            ).scalar_one()
            == 1000
        )
    for operation in [
        "UPDATE recommendation_run SET payload=payload",
        "DELETE FROM recommendation_run",
    ]:
        with pytest.raises(DBAPIError), database.begin() as connection:
            connection.execute(text(operation))


def test_concurrent_key_retries_and_history_pages(database: Engine, tmp_path: Path) -> None:
    owner, request = request_for(database, tmp_path)
    key = uuid4()
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: admit_recommendation(
                    database, tmp_path, owner, request, idempotency_key=key
                ),
                range(2),
            )
        )
    assert results[0] == results[1]
    second = admit_recommendation(database, tmp_path, owner, request)
    assert second.recommendation_id != results[0].recommendation_id
    settings = Settings(database.url.render_as_string(hide_password=False), artifact_root=tmp_path)
    with TestClient(create_app(settings)) as client:
        path = f"/api/v1/portfolios/{owner}/recommendations"
        first = client.get(path + "?limit=1").json()
        assert len(first["items"]) == 1 and first["next_cursor"]
        following = client.get(path + "?limit=1&cursor=" + first["next_cursor"]).json()
        assert len(following["items"]) == 1 and following["next_cursor"] is None
        assert {first["items"][0]["id"], following["items"][0]["id"]} == {
            str(second.recommendation_id),
            str(results[0].recommendation_id),
        }
        assert client.get(f"/api/v1/portfolios/{uuid4()}/recommendations").status_code == 404
