"""Synthetic, deterministic market fixtures (no network)."""

import numpy as np
import pandas as pd
import pytest


def make_market(n_days=400, specs=None, seed=7):
    """specs: {ticker: (daily_drift, daily_vol, sector)}. Returns close, open, volume, sectors."""
    rng = np.random.default_rng(seed)
    specs = specs or {
        "AAA": (0.0020, 0.010, "Tech"),
        "BBB": (0.0015, 0.020, "Tech"),
        "CCC": (0.0010, 0.012, "Health"),
        "DDD": (0.0008, 0.015, "Energy"),
        "EEE": (-0.0010, 0.015, "Energy"),  # downtrend → BELOW_TREND
        "FFF": (0.0012, 0.011, "Utilities"),
        "SPY": (0.0005, 0.008, "Benchmark"),
    }
    dates = pd.bdate_range("2022-01-03", periods=n_days)
    close, open_ = {}, {}
    for t, (mu, sd, _) in specs.items():
        r = mu + sd * rng.standard_normal(n_days)
        c = 50 * np.exp(np.cumsum(r))
        close[t] = c
        open_[t] = c * (1 + 0.001 * rng.standard_normal(n_days))
    close = pd.DataFrame(close, index=dates)
    open_ = pd.DataFrame(open_, index=dates)
    volume = pd.DataFrame(1_000_000.0, index=dates, columns=close.columns)
    sectors = {t: s for t, (_, _, s) in specs.items()}
    return close, open_, volume, sectors


@pytest.fixture
def market():
    return make_market()
