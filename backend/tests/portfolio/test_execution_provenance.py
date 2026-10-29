"""ADR-014: two authored immutable sources, no future data in decision evidence."""

import hashlib
from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.domain.types import canonical_json
from backend.portfolio.execution import ExecutionContext, ExecutionResult, execute_order
from backend.tests.portfolio.test_execution import at, bar, calendar, context, market, order, state

EXECUTION_ID = UUID("22222222-2222-4222-8222-222222222222")


def test_legacy_context_and_execution_round_trip_without_added_nulls() -> None:
    original = context().model_dump(mode="json")
    assert (
        hashlib.sha256(canonical_json(original)).hexdigest()
        == "9b9fdf491ed0f485745cdd543fb3b02b918ae1156c0e8120b3e2a0de9cf7a07e"
    )
    assert "execution_snapshot_id" not in original
    assert "execution_snapshot_sha256" not in original
    assert canonical_json(
        ExecutionContext.model_validate(original).model_dump(mode="json")
    ) == canonical_json(original)
    result = execute_order(
        state(),
        order(),
        context(),
        calendar(),
        market(bar()),
        min_trade_usd="5.00",
        observed_at=at(4),
    )
    stored = result.model_dump(mode="json")
    assert (
        hashlib.sha256(canonical_json(stored)).hexdigest()
        == "e11754253c07b362d05c62e991bcf2e2b0fed55bcae3365db10edc57723e5b85"
    )
    assert canonical_json(
        ExecutionResult.model_validate(stored).model_dump(mode="json")
    ) == canonical_json(stored)
    assert "execution_snapshot_id" not in stored["context"]


def test_later_execution_source_keeps_original_decision_and_original_session() -> None:
    original = context().model_dump(mode="json")
    decision_evidence = market(bar(day=3))
    ctx = context(execution_snapshot_id=EXECUTION_ID, execution_snapshot_sha256="b" * 64)
    evidence = market(bar(), snapshot_id=EXECUTION_ID, snapshot_sha256="b" * 64)
    result = execute_order(
        state(), order(), ctx, calendar(), evidence, min_trade_usd="5.00", observed_at=at(4)
    )
    assert result.fill is not None
    assert result.state_after.cash_usd == "799.80"
    assert result.state_after.positions[0].quantity == "2.000000"
    assert result.context.snapshot_id == context().snapshot_id
    assert result.context.execution_snapshot_id == EXECUTION_ID
    assert result.eligible_session.session_date == bar().session_date
    assert context().model_dump(mode="json") == original
    assert all(b.session_date == context().decision_session for b in decision_evidence.bars)
    with pytest.raises(ValueError, match="lineage"):
        execute_order(
            state(),
            order(),
            ctx,
            calendar(),
            decision_evidence,
            min_trade_usd="5.00",
            observed_at=at(4),
        )


@pytest.mark.parametrize(
    "updates",
    [
        {"execution_snapshot_id": EXECUTION_ID},
        {"execution_snapshot_sha256": "b" * 64},
    ],
)
def test_execution_reference_is_a_pair(updates: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ExecutionContext.model_validate(context().model_dump(mode="json") | updates)


def test_later_publication_does_not_substitute_a_later_open_or_future_availability() -> None:
    ctx = context(execution_snapshot_id=EXECUTION_ID, execution_snapshot_sha256="b" * 64)
    evidence = market(bar(day=8), snapshot_id=EXECUTION_ID, snapshot_sha256="b" * 64)
    result = execute_order(
        state(), order(), ctx, calendar(), evidence, min_trade_usd="5.00", observed_at=at(8)
    )
    assert result.fill is None and not result.terminal
    assert result.state_after == state()
    future = market(bar(), snapshot_id=EXECUTION_ID, snapshot_sha256="b" * 64)
    result = execute_order(
        state(), order(), ctx, calendar(), future, min_trade_usd="5.00", observed_at=at(4, 14, 30)
    )
    assert result.fill is None and not result.terminal
