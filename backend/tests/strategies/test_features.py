import math

import pytest

from backend.strategies.features import population_zscores, sample_log_volatility, window_momentum


def test_fix01_independent_population_zscore_and_constant_vector() -> None:
    assert population_zscores([1, 2, 3]) == pytest.approx(
        (-math.sqrt(1.5), 0, math.sqrt(1.5)), abs=1e-12
    )
    assert population_zscores([2, 2, 2]) == (0, 0, 0)
    assert population_zscores([2]) == (0,)
    assert population_zscores([]) == ()


def test_independent_sample_log_return_vector() -> None:
    # Log returns are [ln2, 0, -ln2]; mean=0 and sample variance=(2*ln2²)/2.
    assert sample_log_volatility(["100", "200", "200", "100"], 3) == pytest.approx(
        math.log(2) * math.sqrt(252), abs=1e-12
    )
    assert sample_log_volatility(["100"] * 61) == 0
    with pytest.raises(ValueError, match="history"):
        sample_log_volatility(["100"] * 60)


def test_momentum_endpoint_and_small_positive_volatility() -> None:
    assert window_momentum(["50"] * 126 + ["60"], 126) == pytest.approx(0.2, abs=1e-12)
    assert sample_log_volatility(["100", "100.0000000000000000000000000001", "100"], 2) > 0
