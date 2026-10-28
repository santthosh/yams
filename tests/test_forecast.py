from app import forecast
from tests.conftest import make_market


def test_seeded_forecast_is_reproducible_and_ordered(market):
    close = market[0]
    cur, prop = {"AAA": 0.5}, {"AAA": 0.3, "CCC": 0.4}
    a = forecast.run_forecast(close, cur, prop, 1000.0, 1.0)
    b = forecast.run_forecast(close, cur, prop, 1000.0, 1.0)
    assert a == b and a["status"] == "available"
    for side in ("proposed", "hold"):
        s = a[side]
        assert s["p10_return"] <= s["median_return"] <= s["p90_return"]
        assert 0 <= s["prob_loss"] <= 1
    assert a["horizon_sessions"] == 62


def test_all_cash_is_flat(market):
    f = forecast.run_forecast(market[0], {}, {}, 1000.0, 0.0)
    assert f["hold"]["median_return"] == 0 and f["proposed"]["prob_loss"] == 0


def test_short_history_is_unavailable_not_zero():
    close = make_market(n_days=200)[0]
    f = forecast.run_forecast(close, {}, {"AAA": 0.9}, 1000.0, 1.0)
    assert f["status"] == "unavailable" and "AAA" in f["reason"]
    assert "proposed" not in f
