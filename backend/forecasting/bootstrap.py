"""Pinned whole-vector sampling and constant-weight float64 scenario arithmetic."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from typing import TYPE_CHECKING, Any

from backend.domain.forecast import ForecastOutcome

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray

PATHS = 5000
LOOKBACK = 252
BLOCK = 5
NUMPY_VERSION = "2.5.4"


class ForecastCancelled(Exception):
    """Cooperative cancellation publishes no partial scenario."""


@dataclass(frozen=True)
class Sampling:
    starts: NDArray[np.int64]
    initial_state: dict[str, Any]


def draw_starts(horizon: int, seed: int) -> Sampling:
    # Import after the worker establishes its numerical-thread/resource limits.
    import numpy as np

    if np.__version__ != NUMPY_VERSION:
        raise ValueError("Unsupported numerical version")
    if type(horizon) is not int or not 1 <= horizon <= 90:
        raise ValueError("Invalid forecast horizon")
    if type(seed) is not int or not 0 <= seed <= 18446744073709551615:
        raise ValueError("Invalid forecast seed")
    generator = np.random.Generator(np.random.PCG64(seed))
    state = dict(generator.bit_generator.state)
    starts = generator.integers(
        low=0,
        high=248,
        size=(PATHS, (horizon + BLOCK - 1) // BLOCK),
        dtype=np.int64,
        endpoint=False,
    )
    starts.setflags(write=False)
    return Sampling(starts, state)


def array_bytes(values: NDArray[np.float64] | NDArray[np.int64], *, integer: bool) -> bytes:
    """Raw little-endian C-order bytes; shape/columns/dates are separate metadata."""
    import numpy as np

    return np.ascontiguousarray(values, dtype="<i8" if integer else "<f8").tobytes(order="C")


def array_digest(values: NDArray[np.float64] | NDArray[np.int64], *, integer: bool) -> str:
    return hashlib.sha256(array_bytes(values, integer=integer)).hexdigest()


def expand_blocks(
    history: NDArray[np.float64], starts: NDArray[np.int64], block: int, horizon: int
) -> NDArray[np.float64]:
    """Small independent-fixture seam; production always uses 252 rows/five blocks."""
    import numpy as np

    if (
        history.ndim != 2
        or starts.ndim != 2
        or block < 1
        or horizon < 1
        or starts.shape[1] != (horizon + block - 1) // block
        or not np.issubdtype(starts.dtype, np.integer)
        or np.any(starts < 0)
        or np.any(starts + block > history.shape[0])
    ):
        raise ValueError("Invalid noncircular blocks")
    rows = (starts[:, :, None] + np.arange(block)).reshape(starts.shape[0], -1)[:, :horizon]
    return np.asarray(history[rows], dtype=np.float64)


def simulate(
    history: NDArray[np.float64] | None,
    starts: NDArray[np.int64] | None,
    weights: NDArray[np.float64],
    horizon: int,
    *,
    cancelled: Callable[[], bool] = lambda: False,
    progress: Callable[[int, int], None] = lambda completed, total: None,
) -> NDArray[np.float64]:
    """Unrounded gross growth factors; both cases use each same whole vector.

    Capital/cost enter the ending-value equation once, after compounding, so a
    known small cost cannot disappear through float cancellation at large NAV.
    """
    import numpy as np

    if (
        not 1 <= horizon <= 90
        or weights.ndim != 2
        or weights.shape[0] != 2
        or not np.isfinite(weights).all()
        or np.any(weights < 0)
    ):
        raise ValueError("Invalid scenario arithmetic inputs")
    union = weights.shape[1]
    if union > 16:
        raise ValueError("WORKLOAD_LIMIT")
    if union and (
        history is None
        or starts is None
        or history.shape != (LOOKBACK, union)
        or not np.isfinite(history).all()
        or np.any(history < -1)
        or starts.shape != (PATHS, (horizon + BLOCK - 1) // BLOCK)
        or not np.issubdtype(starts.dtype, np.integer)
        or np.any(starts < 0)
        or np.any(starts >= 248)
    ):
        raise ValueError("Invalid aligned history or sampled indices")
    if not union and (history is not None or starts is not None):
        raise ValueError("Cash-only cases must not draw random indices")
    paths = np.empty((2, PATHS, horizon + 1), dtype=np.float64)
    paths[:, :, 0] = 1.0
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        for step in range(horizon):
            if cancelled():
                raise ForecastCancelled()
            if union:
                assert history is not None and starts is not None
                rows = starts[:, step // BLOCK] + step % BLOCK
                vectors = history[rows]
                for case in range(2):
                    returns = np.sum(vectors * weights[case], axis=1)
                    paths[case, :, step + 1] = paths[case, :, step] * (1 + returns)
            else:
                paths[:, :, step + 1] = paths[:, :, step]
            progress(step + 1, horizon)
    if not np.isfinite(paths).all() or np.any(paths < 0):
        raise ValueError("NONFINITE_RESULT")
    paths.setflags(write=False)
    return paths


def linear_quantile(values: NDArray[np.float64], q: float) -> float:
    import numpy as np

    if values.ndim != 1 or not len(values) or not np.isfinite(values).all() or not 0 <= q <= 1:
        raise ValueError("Invalid quantile inputs")
    ordered = np.sort(values)
    index = (len(values) - 1) * q
    lower, upper = math.floor(index), math.ceil(index)
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower))


def _money(exact: Decimal) -> str:
    if not exact.is_finite() or exact < 0:
        raise ValueError("NONFINITE_RESULT")
    with localcontext() as context:
        context.prec = max(64, len(exact.as_tuple().digits) + 16)
        rounded = exact.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        if rounded >= Decimal("10000000000000000000000"):
            raise ValueError("NONFINITE_RESULT")
        return format(rounded, "f")


def money_from_float(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError("NONFINITE_RESULT")
    return _money(Decimal.from_float(value) if value else Decimal(0))


def outcome(
    growth: NDArray[np.float64],
    original_value: str | float | Decimal,
    upfront_cost: str | float | Decimal = 0.0,
) -> ForecastOutcome:
    import numpy as np

    original, cost = Decimal(original_value), Decimal(upfront_cost)
    if (
        not original.is_finite()
        or original <= 0
        or not cost.is_finite()
        or not 0 <= cost < original
        or np.any(growth < 0)
    ):
        raise ValueError("Invalid terminal growth or capital")
    with localcontext() as context:
        context.prec = max(64, len(original.as_tuple().digits) + 16)
        starting = original - cost
        relative_cost = float(cost / original)
        remaining_fraction = float(starting / original)
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        # Algebraically G*(V-C)/V-1; this ordering retains tiny known costs at G=1.
        returns = (
            (growth - 1) - growth * relative_cost
            if relative_cost <= 0.5
            else growth * remaining_fraction - 1
        )
    median_growth = Decimal.from_float(linear_quantile(growth, 0.5))
    with localcontext() as context:
        context.prec = max(
            64, len(median_growth.as_tuple().digits) + len(starting.as_tuple().digits) + 16
        )
        median_value = starting * median_growth
    return ForecastOutcome(
        median_return_fraction=linear_quantile(returns, 0.5),
        p10_return_fraction=linear_quantile(returns, 0.1),
        p90_return_fraction=linear_quantile(returns, 0.9),
        probability_of_loss=float(np.count_nonzero(returns < 0) / len(returns)),
        median_ending_value_usd=_money(median_value),
    )
