"""Diagnostic transport tests use an explicit fixture cutoff, not an arrival policy."""

import json
import shutil
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.api.main import create_app
from backend.domain.evaluation import (
    StrategyEvaluationPayload,
    StrategyEvaluationRequest,
    StrategyEvaluationResultV1,
    StrategyEvaluationV1,
)
from backend.domain.strategy import StrategyConfigV1
from backend.market_data.files import PinnedSnapshot
from backend.portfolio.allocation import allocate_momentum
from backend.strategies.build import engine_fingerprint
from backend.strategies.evaluations import result_from_engine
from backend.strategies.momentum import evaluate_snapshot
from backend.strategies.registry import DEFAULT_VERSION_ID

ROOT = Path(__file__).resolve().parents[3] / "data/fixtures"


def explicit_fixture_result(
    tmp_path: Path,
) -> tuple[StrategyEvaluationPayload, StrategyEvaluationResultV1]:
    shutil.copytree(ROOT / "snapshot", tmp_path / "snapshot")
    digest = json.loads((ROOT / "manifest.json").read_text())["snapshot_sha256"]
    pinned = PinnedSnapshot.open(tmp_path / "snapshot", digest)
    config = StrategyConfigV1.from_json((ROOT / "fix-01/strategy.canonical.json").read_bytes())
    # Approved Q15: FIX-01 session400 closes20:00Z; decision is20:15Z.
    cutoff = datetime(2028, 7, 17, 20, 15, tzinfo=UTC)
    measured = allocate_momentum(
        evaluate_snapshot(
            pinned, config, cutoff, date(2028, 7, 17), engine_version=engine_fingerprint()
        ),
        config,
    )
    payload = StrategyEvaluationPayload(
        evaluation_id=uuid4(),
        inputs=StrategyEvaluationRequest(
            strategy_version_id=DEFAULT_VERSION_ID,
            snapshot_id=pinned.manifest.snapshot_id(),
            as_of_session=date(2028, 7, 17),
        ),
        source_mode=pinned.manifest.mode,
        config_sha256=config.config_hash(),
        snapshot_sha256=digest,
        calendar_sha256=measured.momentum.calendar_sha256,
        engine_version=measured.momentum.engine_version,
        decision_cutoff_utc=cutoff,
        config_canonical_json=config.canonical_bytes().decode(),
    )
    return payload, result_from_engine(payload, measured)


def test_explicit_fixture_transport_and_independent_momentum_oracle(tmp_path: Path) -> None:
    payload, result = explicit_fixture_result(tmp_path)
    expected = json.loads((ROOT / "fix-01/case.json").read_text())["expected"][
        "full_snapshot_probe"
    ]
    row = next(row for row in result.candidates if row.asset_id == expected["asset_id"])
    assert row.features is not None
    assert row.features.momentum_long == pytest.approx(expected["momentum126"], abs=1e-12)
    assert row.features.volatility == pytest.approx(expected["volatility60"], abs=1e-12)
    assert result.reproducibility.config_sha256 == payload.config_sha256
    assert StrategyEvaluationResultV1.model_validate_json(result.model_dump_json()) == result
    assert (
        result.result_hash()
        == StrategyEvaluationResultV1.model_validate_json(result.canonical_bytes()).result_hash()
    )
    envelope = dict(
        id=payload.evaluation_id,
        job_id=uuid4(),
        status="completed",
        inputs=payload.inputs,
        mode=payload.source_mode,
        provider=json.loads((ROOT / "snapshot/manifest.json").read_text())["source"]["provider"],
        config_sha256=payload.config_sha256,
        snapshot_sha256=payload.snapshot_sha256,
        engine_version=payload.engine_version,
        created_at=datetime.now(UTC),
        strategy_config=StrategyConfigV1.from_json(payload.config_canonical_json),
        result=result,
        result_sha256=result.result_hash(),
        error=None,
    )
    assert StrategyEvaluationV1.model_validate(envelope).result == result
    for patch in ({"status": "running"}, {"result_sha256": "0" * 64}, {"engine_version": "0" * 64}):
        with pytest.raises(ValidationError):
            StrategyEvaluationV1.model_validate(envelope | patch)
    assert engine_fingerprint() == engine_fingerprint()


def test_request_is_closed_and_unavailable_api_uses_typed_errors() -> None:
    request = dict(
        strategy_version_id=str(uuid4()), snapshot_id=str(uuid4()), as_of_session="2028-07-17"
    )
    with pytest.raises(ValidationError):
        StrategyEvaluationRequest.model_validate(
            request | {"decision_cutoff_utc": "2028-07-17T20:00:00Z"}
        )
    with TestClient(create_app()) as client:
        result = client.post("/api/v1/strategy-evaluations", json=request)
        assert result.status_code == 503 and result.json()["error"]["code"] == "NOT_READY"
        assert client.get(f"/api/v1/strategy-evaluations/{uuid4()}").status_code == 503
        assert (
            client.post("/api/v1/strategy-evaluations", json=request | {"extra": 1}).status_code
            == 422
        )
