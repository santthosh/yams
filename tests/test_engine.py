from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from app import engine
from app.config import STRATEGY
from tests.conftest import make_market

MEMBERS = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]


def test_scores_deterministic_and_reasons(market):
    close, _, volume, sectors = market
    a = engine.evaluate(close, volume, sectors, MEMBERS)
    b = engine.evaluate(close, volume, sectors, MEMBERS)
    pd.testing.assert_frame_equal(a.candidates, b.candidates)
    assert a.candidates.at["EEE", "reason"] == "BELOW_TREND"
    assert set(a.eligible.index) <= set(MEMBERS) - {"EEE"}


def test_score_formula_subtracts_volatility(market):
    close, _, volume, sectors = market
    c = engine.evaluate(close, volume, sectors, MEMBERS).eligible
    expected = 0.60 * c["z_m126"] + 0.25 * c["z_m63"] - 0.15 * c["z_vol60"]
    np.testing.assert_allclose(c["score"], expected)
    assert STRATEGY.w_vol_penalty > 0  # stored as a positive magnitude


def test_filters_short_history_low_price_illiquid_no_sector(market):
    close, _, volume, sectors = market
    close = close.copy()
    volume = volume.copy()
    close.loc[close.index[:200], "AAA"] = np.nan  # short history
    close["BBB"] = close["BBB"] / 20  # price < $5
    volume["CCC"] = 1.0  # illiquid
    sectors = {**sectors, "DDD": ""}
    cand = engine.evaluate(close, volume, sectors, MEMBERS).candidates
    assert cand.at["AAA", "reason"] == "SHORT_HISTORY"
    assert cand.at["BBB", "reason"] == "LOW_PRICE"
    assert cand.at["CCC", "reason"] == "ILLIQUID"
    assert cand.at["DDD", "reason"] == "NO_SECTOR"


def test_zero_dispersion_gives_zero_z():
    s = pd.Series([1.0, 1.0, 1.0])
    assert (engine._zscore(s) == 0).all()


def test_ties_broken_by_ticker():
    close, _, volume, sectors = make_market(specs={
        "ZZZ": (0.001, 0.01, "A"), "SPY": (0.0005, 0.008, "B")})
    close["AAA"] = close["ZZZ"]
    volume["AAA"] = volume["ZZZ"]
    sectors["AAA"] = "A"
    cand = engine.evaluate(close, volume, sectors, ["ZZZ", "AAA"]).candidates
    assert cand.at["AAA", "rank"] == 1 and cand.at["ZZZ", "rank"] == 2


def test_weights_sum_to_one_and_caps_hold(market):
    close, _, volume, sectors = market
    ev = engine.evaluate(close, volume, sectors, MEMBERS)
    assert abs(sum(ev.targets.values()) + ev.cash_weight - 1) < 1e-9
    assert ev.cash_weight >= STRATEGY.min_cash_weight - 1e-9
    assert all(w <= STRATEGY.max_position_weight + 1e-9 for w in ev.targets.values())
    by_sector = {}
    for t, w in ev.targets.items():
        by_sector[sectors[t]] = by_sector.get(sectors[t], 0) + w
    assert all(w <= STRATEGY.max_sector_weight + 1e-9 for w in by_sector.values())


def test_allocate_caps_and_leaves_cash():
    raw = {"A": 10.0, "B": 1.0, "C": 1.0}
    w, capped = engine.allocate(raw, {"A": "x", "B": "y", "C": "y"}, 0.95, 0.20, 0.40)
    assert w["A"] == pytest.approx(0.20) and capped["A"] == "position"
    assert sum(w.values()) == pytest.approx(0.60)  # only 3 names × 20% can be funded; rest is cash
    w, capped = engine.allocate({"A": 1, "B": 1, "C": 1, "D": 3}, {"A": "s", "B": "s", "C": "s", "D": "t"},
                                0.95, 0.5, 0.40)
    assert w["A"] + w["B"] + w["C"] == pytest.approx(0.40)  # sector "s" capped at 40%
    assert w["D"] == pytest.approx(0.40)  # absorbs the excess until its own sector cap binds


def test_empty_universe_is_all_cash(market):
    close, _, volume, sectors = market
    ev = engine.evaluate(close, volume, sectors, ["EEE"])
    assert ev.targets == {} and ev.cash_weight == 1.0


def test_risk_off_regime_raises_cash_floor(market):
    close, _, volume, sectors = market
    close = close.copy()
    close.loc[close.index[-20:], "SPY"] = close["SPY"].iloc[-21] * 0.5  # crash below SMA200
    ev = engine.evaluate(close, volume, sectors, MEMBERS)
    assert ev.regime == "risk_off"
    assert ev.cash_weight >= STRATEGY.risk_off_cash_weight - 1e-9


def test_no_lookahead(market):
    close, _, volume, sectors = market
    cut = close.index[350]
    base = engine.evaluate(close.loc[:cut], volume.loc[:cut], sectors, MEMBERS)
    future = close.copy()
    future.loc[future.index > cut] *= 3.0  # wildly different future
    again = engine.evaluate(future.loc[:cut], volume.loc[:cut], sectors, MEMBERS)
    pd.testing.assert_frame_equal(base.candidates, again.candidates)
    assert base.targets == again.targets


def test_orders_band_min_trade_and_full_exit():
    prices = {"A": 10.0, "B": 10.0, "C": 10.0, "D": 10.0}
    holdings = {"A": Decimal("20"), "B": Decimal("30"), "C": Decimal("5")}
    cash = Decimal("450")  # value = 1000
    targets = {"A": 0.21, "B": 0.10, "D": 0.004}
    orders = {o.ticker: o for o in engine.plan_orders(holdings, cash, prices, targets)}
    assert orders["A"].action == "HOLD" and orders["A"].reasons == ["IN_BAND"]
    assert orders["B"].action == "REDUCE" and orders["B"].qty == Decimal("20")
    assert orders["C"].action == "SELL" and orders["C"].qty == Decimal("5")  # full exit ignores band
    assert orders["D"].action == "HOLD"  # 0.4% is inside the band


def test_execute_sells_first_cash_never_negative_truncates():
    prices = {"A": 100.0, "B": 3.0}
    holdings = {"A": Decimal("1")}
    orders = engine.plan_orders(holdings, Decimal("0"), prices, {"B": 0.95})
    new_h, cash, fills, skipped = engine.execute(orders, holdings, Decimal("0"), prices)
    assert [f.side for f in fills] == ["SELL", "BUY"]
    assert cash >= 0
    assert new_h["B"] == new_h["B"].quantize(Decimal("0.000001"))
    assert "A" not in new_h
    # conservation: cash + value + costs == starting value
    total = cash + new_h["B"] * Decimal("3") + sum(f.cost for f in fills)
    assert abs(total - Decimal("100")) <= Decimal("0.02")


def test_execute_skips_tiny_and_unpriced():
    orders = engine.plan_orders({}, Decimal("1000"), {"A": 10.0, "B": 10.0}, {"A": 0.5, "B": 0.4})
    _, cash, fills, skipped = engine.execute(orders, {}, Decimal("3"), {"A": 10.0})
    assert fills == [] and set(skipped) == {"A", "B"} and cash == Decimal("3")
