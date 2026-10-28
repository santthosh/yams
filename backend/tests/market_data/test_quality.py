from decimal import localcontext

import pytest

from backend.market_data.quality import extreme_adjusted_move


@pytest.mark.parametrize(
    ("current", "excluded"),
    [
        ("150", False),
        ("50", False),
        ("150.0000000000000000000000000001", True),
        ("49.9999999999999999999999999999", True),
        ("100", False),
        ("200", True),
    ],
)
def test_strict_fifty_percent_boundary(current: str, excluded: bool) -> None:
    with localcontext() as context:
        context.prec = 6
        assert extreme_adjusted_move("100", current) is excluded


@pytest.mark.parametrize("price", ["0", "-1", "NaN", "Infinity"])
def test_invalid_comparison_price(price: str) -> None:
    with pytest.raises(ValueError, match="positive finite"):
        extreme_adjusted_move("100", price)
