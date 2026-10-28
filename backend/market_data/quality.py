"""Exact, inspectable data-quality guards; never repair provider observations."""

from decimal import Decimal


def extreme_adjusted_move(previous: str, current: str) -> bool:
    """Strict 50% boundary, without rounding a division near the boundary.

    Callers supply validated positive prices for adjacent calendar sessions.
    Integer scaling avoids Decimal context rounding even for long provider values.
    """
    before, after = Decimal(previous), Decimal(current)
    if not before.is_finite() or not after.is_finite() or before <= 0 or after <= 0:
        raise ValueError("Quality comparison requires positive finite prices")
    before_n, before_d = before.as_integer_ratio()
    after_n, after_d = after.as_integer_ratio()
    return 2 * abs(after_n * before_d - before_n * after_d) > before_n * after_d
