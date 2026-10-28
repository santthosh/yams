"""Canonical job requests preserve allowed statistical numbers without float ledger hashing."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.backtesting.contracts import BacktestCorePayload
from backend.domain.experiment import ExperimentRequest
from backend.domain.types import canonical_json, load_json
from backend.jobs.registry import validate_payload
from backend.strategies.registry import template_config


def test_job_envelope_hashes_exactly_and_preserves_request() -> None:
    request = ExperimentRequest.model_validate(
        dict(
            strategy_version_id=uuid4(),
            snapshot_id=uuid4(),
            start_session="2028-07-18",
            end_session_exclusive="2028-07-24",
            initial_capital_usd="1000.00",
            benchmark_asset_id="SYN:SPY",
            execution_policy_id="us_eod_next_open_v1",
            random_seed=42,
            evaluation_split={"kind": "chronological", "holdout_fraction": 0.25},
        )
    )
    config = template_config("mean_reversion")
    payload = BacktestCorePayload(
        experiment_id=uuid4(),
        inputs_canonical_json=canonical_json(load_json(request.model_dump_json())).decode(),
        source_mode="synthetic_fixture",
        config_sha256=config.config_hash(),
        snapshot_sha256="a" * 64,
        calendar_sha256="b" * 64,
        engine_version="c" * 64,
        config_canonical_json=config.canonical_bytes().decode(),
    )
    assert payload.inputs == request
    assert canonical_json(payload.model_dump(mode="json"))
    assert validate_payload("backtest_core", payload.model_dump(mode="json")) == payload
    for field in ["inputs_canonical_json", "config_canonical_json"]:
        data = payload.model_dump(mode="json")
        data[field] += " "
        with pytest.raises(ValidationError):
            BacktestCorePayload.model_validate(data)
