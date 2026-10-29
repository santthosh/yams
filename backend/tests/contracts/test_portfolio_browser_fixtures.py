"""Owned browser fixtures must retain typed contracts and independent FIX-03 cents."""

import json
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from pathlib import Path
from typing import Any

from backend.domain.orders import PaperOrderBatchV1
from backend.domain.portfolio import PaperPortfolioV1, PortfolioTransactionV1


def test_authored_portfolio_transport_is_valid_and_financially_coherent() -> None:
    root = Path(__file__).resolve().parents[3]
    fixtures: dict[str, Any] = json.loads(
        (root / "apps/web/tests/portfolio-transport.json").read_text()
    )
    assert fixtures["label"] == "SYNTHETIC_DATA_ONLY"
    assert fixtures["fixture_plan"] == ["FIX-03", "FIX-06", "FIX-09"]
    accounts = {
        key: PaperPortfolioV1.model_validate(fixtures[key])
        for key in ("cash", "posted", "missing", "stale")
    }
    for value in fixtures["events"].values():
        PortfolioTransactionV1.model_validate(value)
    for value in fixtures["batches"].values():
        PaperOrderBatchV1.model_validate(value)
    cash, posted = accounts["cash"], accounts["posted"]
    assert cash.cash_usd == cash.total_value_usd == "1000.00"
    assert not cash.holdings and cash.valuation.cash_weight == "1"
    # Authored funding1000 minus buy2×100.10, mark2×101; no production math call.
    assert posted.cash_usd == "799.80" and posted.holdings[0].total_basis_usd == "200.20"
    assert posted.holdings[0].quantity == "2.000000"
    assert posted.holdings[0].market_value_usd == "202.00"
    assert posted.total_value_usd == "1001.80"
    with localcontext() as context:
        context.prec = 60
        expected = (Decimal("202.00") / Decimal("1001.80")).quantize(
            Decimal("0.000000000000000001"), rounding=ROUND_HALF_EVEN
        )
        assert Decimal(posted.holdings[0].weight or "0") == expected
    for key in ("missing", "stale"):
        assert accounts[key].total_value_usd is None
        assert accounts[key].holdings[0].mark_price_usd is None
        assert accounts[key].cash_usd == posted.cash_usd
        assert accounts[key].holdings[0].quantity == posted.holdings[0].quantity
