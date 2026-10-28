import pandas as pd
import pytest

from app import backtest
from tests.conftest import make_market

MEMBERS = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]


def test_metrics_known_path():
    eq = pd.Series([100.0, 110.0, 99.0, 121.0])
    m = backtest.metrics(eq)
    assert m["total_return"] == pytest.approx(0.21)
    assert m["max_drawdown"] == pytest.approx(99 / 110 - 1)
    assert m["ending_value"] == 121.0


def test_fills_happen_at_next_open():
    close, open_, volume, sectors = make_market(n_days=420)
    r = backtest.run_backtest(close, open_, volume, sectors, MEMBERS, initial_cash=1000, years=1)
    first_decision = close.index.get_loc(pd.Timestamp(r.start))
    first_fill_day = close.index[first_decision + 1].strftime("%Y-%m-%d")
    first = [t for t in r.trades if t["date"] == r.trades[0]["date"]]
    assert r.trades[0]["date"] == first_fill_day
    for t in first:
        assert t["side"] == "BUY"
        assert t["price"] == pytest.approx(open_.at[pd.Timestamp(first_fill_day), t["ticker"]] * 1.001, rel=1e-6)
    assert r.equity[0] == 1000 and r.benchmark[0] == 1000
    assert len(r.equity) == len(r.dates) == len(r.benchmark)


def test_backtest_ignores_future_data():
    close, open_, volume, sectors = make_market(n_days=420)
    r1 = backtest.run_backtest(close, open_, volume, sectors, MEMBERS, years=1)
    cut = pd.Timestamp(r1.dates[100])
    close2, open2 = close.copy(), open_.copy()
    close2.loc[close2.index > cut] *= 3.0  # change only the future after `cut`
    open2.loc[open2.index > cut] *= 3.0
    r2 = backtest.run_backtest(close2, open2, volume, sectors, MEMBERS, years=1)
    early = lambda r: [t for t in r.trades if pd.Timestamp(t["date"]) <= cut]  # noqa: E731
    assert early(r1) and early(r1) == early(r2)
    assert r1.equity[:101] == r2.equity[:101]
