"""A hash seal cannot substitute for complete nested temporal/input lineage."""

from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from backend.backtesting.contracts import BacktestCorePayload
from backend.backtesting.runner import run_backtest
from backend.backtesting.service import validate_result
from backend.domain.types import canonical_json, load_json
from backend.market_data.repository import MarketRepository
from backend.portfolio.execution import calendar_digest
from backend.strategies.registry import template_config
from backend.tests.backtesting.test_core import pinned, request


@pytest.mark.parametrize(
    "mutation", ["decision", "context", "missing_execution", "fill_time", "initial_cash"]
)
def test_complete_nested_lineage_is_required(tmp_path: Path, mutation: str) -> None:
    snapshot = pinned(tmp_path)
    inputs = request(snapshot, initial_capital_usd="1000")
    config = template_config("mean_reversion")
    with MarketRepository(snapshot) as repository:
        result = run_backtest(repository, inputs, config, engine_version="a" * 64)
        payload = BacktestCorePayload(
            experiment_id=uuid4(),
            inputs_canonical_json=canonical_json(load_json(inputs.model_dump_json())).decode(),
            source_mode=snapshot.manifest.mode,
            config_sha256=config.config_hash(),
            snapshot_sha256=snapshot.manifest.manifest_hash(),
            calendar_sha256=calendar_digest(repository.calendar),
            engine_version="a" * 64,
            config_canonical_json=config.canonical_bytes().decode(),
        )
        validate_result(payload, result, repository.calendar)
        if mutation == "decision":
            decision = result.decisions[0]
            wrong = decision.measured.momentum.model_copy(
                update={"cutoff": decision.measured.momentum.cutoff + timedelta(seconds=1)}
            )
            result = result.model_copy(
                update={
                    "decisions": (
                        decision.model_copy(
                            update={
                                "measured": decision.measured.model_copy(update={"momentum": wrong})
                            }
                        ),
                    )
                }
            )
        elif mutation == "context":
            decision = result.decisions[0]
            wrong_plan = decision.plan.model_copy(
                update={
                    "context": decision.plan.context.model_copy(
                        update={"snapshot_sha256": "b" * 64}
                    )
                }
            )
            result = result.model_copy(
                update={"decisions": (decision.model_copy(update={"plan": wrong_plan}),)}
            )
        elif mutation == "missing_execution":
            result = result.model_copy(update={"executions": result.executions[:-1]})
        elif mutation == "fill_time":
            execution = result.executions[0]
            assert execution.fill is not None
            wrong_fill = execution.fill.model_copy(
                update={"execution_at": execution.fill.execution_at + timedelta(seconds=1)}
            )
            result = result.model_copy(
                update={
                    "executions": (
                        execution.model_copy(update={"fill": wrong_fill}),
                        *result.executions[1:],
                    )
                }
            )
        else:
            point = result.points[0]
            result = result.model_copy(
                update={
                    "points": (
                        point.model_copy(
                            update={"state": point.state.model_copy(update={"cash_usd": "999.00"})}
                        ),
                        *result.points[1:],
                    )
                }
            )
        with pytest.raises(ValueError):
            validate_result(payload, result, repository.calendar)
