"""Pinned common-history ADR-006 comparisons, without financial state mutations."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import TYPE_CHECKING, Any
from uuid import NAMESPACE_URL, UUID, uuid5

from backend.domain.common import ArtifactReference
from backend.domain.forecast import ForecastAllocation, ForecastV1, RNGMetadata
from backend.domain.types import canonical_json
from backend.forecasting.bootstrap import (
    BLOCK,
    LOOKBACK,
    NUMPY_VERSION,
    PATHS,
    array_bytes,
    array_digest,
    draw_starts,
    outcome,
    simulate,
)
from backend.forecasting.contracts import ForecastInputs
from backend.forecasting.horizon import map_horizon
from backend.market_data.repository import MarketRepository
from backend.portfolio.execution import calendar_digest
from backend.strategies.clock import decision_cutoff

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray

LIMITATIONS = (
    "SCENARIO_NOT_CALIBRATED_PREDICTION",
    "ZERO_CASH_YIELD",
    "CONSTANT_WEIGHT_APPROXIMATION",
    "ESTIMATED_UPFRONT_COST",
)


@dataclass(frozen=True)
class ScenarioBundle:
    forecast: ForecastV1
    reproducibility: dict[str, Any]
    artifacts: dict[str, bytes]


def _normalized_decimal(value: str) -> str:
    # Validated decimal strings only; avoid context-sensitive Decimal.normalize rounding.
    whole, _, fractional = value.partition(".")
    fractional = fractional.rstrip("0")
    return whole + ("." + fractional if fractional else "")


def _allocation(value: ForecastAllocation) -> dict[str, Any]:
    return {
        "weights": [
            {"asset_id": row.asset_id, "weight": _normalized_decimal(row.weight)}
            for row in sorted(value.weights, key=lambda row: row.asset_id)
            if Decimal(row.weight) > 0
        ],
        "cash_weight": _normalized_decimal(value.cash_weight),
        "upfront_cost_usd": (
            _normalized_decimal(value.upfront_cost_usd)
            if value.upfront_cost_usd is not None
            else None
        ),
    }


def normalized_inputs(inputs: ForecastInputs) -> dict[str, Any]:
    value = inputs.model_dump(mode="json")
    value["current_allocation"] = _allocation(inputs.current_allocation)
    value["proposed_allocation"] = _allocation(inputs.proposed_allocation)
    if inputs.initial_value_usd is not None:
        value["initial_value_usd"] = _normalized_decimal(inputs.initial_value_usd)
    return value


def _reference(role: str, content: bytes) -> ArtifactReference:
    digest = hashlib.sha256(content).hexdigest()
    return ArtifactReference(
        id=uuid5(NAMESPACE_URL, f"yams:forecast:{role}:{digest}"), sha256=digest, schema_version=1
    )


def compare_scenarios(
    repository: MarketRepository,
    inputs: ForecastInputs,
    *,
    forecast_id: UUID,
    engine_version: str,
    cancelled: Callable[[], bool] = lambda: False,
    progress: Callable[[int, int], None] = lambda completed, total: None,
) -> ScenarioBundle:
    import numpy as np

    if np.__version__ != NUMPY_VERSION:
        raise ValueError("Unsupported numerical version")
    manifest = repository.snapshot.manifest
    calendar = repository.calendar
    if (
        manifest.snapshot_id() != inputs.snapshot_id
        or manifest.manifest_hash() != inputs.snapshot_sha256
        or manifest.mode != inputs.source_mode
        or calendar_digest(calendar) != inputs.calendar_sha256
    ):
        raise ValueError("INPUT_FINGERPRINT_MISMATCH")
    horizon = map_horizon(calendar, inputs.decision_cutoff_utc)
    union = tuple(
        sorted(
            {
                row.asset_id
                for allocation in (inputs.current_allocation, inputs.proposed_allocation)
                for row in allocation.weights
                if Decimal(row.weight) > 0
            }
        )
    )
    metadata: dict[str, Any] = {
        "fingerprint_schema_version": 1,
        "inputs": normalized_inputs(inputs),
        "method": "multivariate_block_bootstrap_v1",
        "simulation_count": PATHS,
        "lookback_sessions": LOOKBACK,
        "block_length_sessions": BLOCK,
        "horizon_calendar_days": 90,
        "decision_start_at": inputs.decision_cutoff_utc.isoformat(),
        "horizon_end_at": horizon.end_at.isoformat() if horizon.end_at else None,
        "future_sessions": [day.isoformat() for day in horizon.sessions]
        if horizon.sessions is not None
        else None,
        "asset_order": list(union),
        "input_row_dates": None,
        "input_shape": None,
        "input_encoding": "little_endian_float64_c_order_v1",
        "input_array_sha256": None,
        "sampled_indices_sha256": None,
        "sampled_indices_shape": None,
        "sampled_indices_encoding": "little_endian_int64_c_order_v1",
        "rng_initial_state_sha256": None,
        "numpy_version": NUMPY_VERSION,
        "generator": "PCG64",
        "sampling_version": "noncircular_c_order_v1",
        "engine_version": engine_version,
        "cash_return_fraction": 0,
        "limitations": sorted(set(LIMITATIONS) | set(manifest.warnings)),
    }
    artifacts: dict[str, bytes] = {}
    rng_reference: ArtifactReference | None = None
    index_reference: ArtifactReference | None = None

    def result(reason: str | None, paths: NDArray[np.float64] | None = None) -> ScenarioBundle:
        available = reason is None
        nav = float(inputs.initial_value_usd) if inputs.initial_value_usd is not None else None
        hold = proposal = None
        if available:
            assert paths is not None and nav is not None
            hold = outcome(paths[0, :, -1], inputs.initial_value_usd or "0", "0.00")
            proposal = outcome(
                paths[1, :, -1],
                inputs.initial_value_usd or "0",
                inputs.proposed_allocation.upfront_cost_usd or "0.00",
            )
            artifacts["paths.f64"] = array_bytes(paths, integer=False)
            metadata["path_shape"] = list(paths.shape)
            metadata["path_encoding"] = "little_endian_float64_c_order_v1"
            metadata["path_unit"] = "gross_growth_factor"
            metadata["capital_cost_policy"] = "exact_upfront_capital_v1"
        # Resource UUID and creation/publication clocks are deliberately excluded.
        fingerprint = hashlib.sha256(canonical_json(metadata)).hexdigest() if available else None
        forecast = ForecastV1(
            id=forecast_id,
            status="available" if available else "unavailable",
            unavailable_reason=reason,
            as_of_session=inputs.as_of_session,
            decision_cutoff_utc=inputs.decision_cutoff_utc,
            data_status=inputs.source_mode,
            snapshot_id=inputs.snapshot_id,
            snapshot_sha256=inputs.snapshot_sha256,
            calendar_version=inputs.calendar_sha256,
            horizon_calendar_days=90,
            horizon_trading_sessions=len(horizon.sessions)
            if horizon.sessions is not None
            else None,
            horizon_end_at=horizon.end_at,
            future_sessions=horizon.sessions,
            method="multivariate_block_bootstrap_v1",
            seed=inputs.seed,
            simulation_count=PATHS,
            lookback_sessions=LOOKBACK,
            block_length_sessions=BLOCK,
            cash_return_fraction=0,
            initial_value_usd=inputs.initial_value_usd,
            current_allocation=inputs.current_allocation,
            proposed_allocation=inputs.proposed_allocation,
            rng=RNGMetadata(
                generator="PCG64",
                numpy_version=NUMPY_VERSION,
                sampling_version="noncircular_c_order_v1",
                initial_state=rng_reference,
            ),
            input_array_sha256=metadata["input_array_sha256"],
            sampled_indices=index_reference,
            fingerprint=fingerprint,
            fingerprint_schema_version=1,
            engine_version=engine_version,
            proposed=proposal,
            hold_unchanged=hold,
            median_return_delta_fraction=(
                proposal.median_return_fraction - hold.median_return_fraction
                if proposal is not None and hold is not None
                else None
            ),
            comparability="common_shock_paths",
            limitations=tuple(metadata["limitations"]),
        )
        return ScenarioBundle(forecast, metadata, dict(artifacts))

    try:
        expected_cutoff = decision_cutoff(calendar, inputs.as_of_session)
    except ValueError:
        return result("CALENDAR_UNAVAILABLE")
    if expected_cutoff != inputs.decision_cutoff_utc:
        raise ValueError("DECISION_CUTOFF_MISMATCH")
    if horizon.unavailable_reason:
        return result(horizon.unavailable_reason)
    if inputs.initial_value_usd is None or inputs.valuation_as_of_session != inputs.as_of_session:
        return result("VALUATION_UNAVAILABLE")
    if (
        inputs.current_allocation.upfront_cost_usd is None
        or inputs.proposed_allocation.upfront_cost_usd is None
    ):
        return result("COST_UNAVAILABLE")
    if len(union) > 16:
        return result("WORKLOAD_LIMIT")
    assert horizon.sessions is not None
    history: NDArray[np.float64] | None = None
    starts: NDArray[np.int64] | None = None
    if union:
        if manifest.quality == "blocked":
            return result("INSUFFICIENT_ALIGNED_HISTORY")
        if manifest.price_basis.adjusted_close not in {
            "identity_no_actions_v1",
            "provider_observed",
        }:
            return result("UNSAFE_PRICE_BASIS")
        if not set(union) <= set(manifest.coverage.asset_ids):
            return result("ASSET_UNAVAILABLE")
        days = [row.session_date for row in calendar.sessions]
        if inputs.as_of_session not in days or days.index(inputs.as_of_session) < LOOKBACK:
            return result("INSUFFICIENT_ALIGNED_HISTORY")
        position = days.index(inputs.as_of_session)
        window = days[position - LOOKBACK : position + 1]
        try:
            view = repository.accounting_as_of(inputs.decision_cutoff_utc, inputs.as_of_session)
        except ValueError:
            return result("CALENDAR_UNAVAILABLE")
        bars = {(row.asset_id, row.session_date): row for row in view.bars}
        closes: list[list[Fraction]] = []
        for day in window:
            values = []
            for asset in union:
                bar = bars.get((asset, day))
                if bar is None:
                    return result("INSUFFICIENT_ALIGNED_HISTORY")
                if set(bar.quality_flags) - {"SYNTHETIC_DATA_ONLY"}:
                    return result("UNSAFE_PRICE_BASIS")
                values.append(Fraction(Decimal(bar.adjusted_close)))
            closes.append(values)
        try:
            history = np.array(
                [
                    [float(new[i] / old[i] - 1) for i in range(len(union))]
                    for old, new in zip(closes[:-1], closes[1:], strict=True)
                ],
                dtype=np.float64,
            )
        except (OverflowError, ValueError):
            return result("NONFINITE_RESULT")
        if not np.isfinite(history).all():
            return result("NONFINITE_RESULT")
        artifacts["returns.f64"] = array_bytes(history, integer=False)
        metadata["input_array_sha256"] = array_digest(history, integer=False)
        metadata["input_row_dates"] = [day.isoformat() for day in window[1:]]
        metadata["input_shape"] = list(history.shape)
        sampling = draw_starts(len(horizon.sessions), inputs.seed)
        starts = sampling.starts
        artifacts["indices.i64"] = array_bytes(starts, integer=True)
        artifacts["rng-state.json"] = canonical_json(sampling.initial_state)
        rng_reference = _reference("rng-state", artifacts["rng-state.json"])
        index_reference = _reference("indices", artifacts["indices.i64"])
        metadata["sampled_indices_sha256"] = index_reference.sha256
        metadata["sampled_indices_shape"] = list(starts.shape)
        metadata["rng_initial_state_sha256"] = rng_reference.sha256
    weights = np.array(
        [
            [
                float(
                    next(
                        (
                            Decimal(row.weight)
                            for row in allocation.weights
                            if row.asset_id == asset
                        ),
                        Decimal(0),
                    )
                )
                for asset in union
            ]
            for allocation in (inputs.current_allocation, inputs.proposed_allocation)
        ],
        dtype=np.float64,
    )
    try:
        nav, cost = (
            float(inputs.initial_value_usd),
            float(inputs.proposed_allocation.upfront_cost_usd),
        )
        if not math.isfinite(nav) or not math.isfinite(cost):
            return result("NONFINITE_RESULT")
        paths = simulate(
            history,
            starts,
            weights,
            len(horizon.sessions),
            cancelled=cancelled,
            progress=progress,
        )
        return result(None, paths)
    except (FloatingPointError, OverflowError):
        return result("NONFINITE_RESULT")
    except ValueError as error:
        if str(error) != "NONFINITE_RESULT":
            raise
        return result("NONFINITE_RESULT")
