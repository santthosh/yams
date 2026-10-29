"""Unknown payable evidence must not be treated as complete execution accounting."""

from datetime import date

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from backend.persistence.models.ledger import PaperOrder, PaperOrderBatch
from backend.portfolio.ledger import post_action, post_order, read_portfolio
from backend.tests.integration.test_bootstrap import database as database
from backend.tests.integration.test_paper_ledger import evidence_for, seed_batch
from backend.tests.portfolio.test_execution import action, at, calendar

pytestmark = pytest.mark.integration


def test_positive_dividend_without_payable_date_keeps_order_pending(database: Engine) -> None:
    owner, first = seed_batch(database)
    assert (
        post_order(
            database,
            first,
            calendar=calendar(),
            market=evidence_for(database, first),
            observed_at=at(4),
        )
        is not None
    )
    _, pending = seed_batch(database, identity=owner, decision=4)
    with Session(database) as session:
        order = session.get(PaperOrder, pending)
        assert order is not None
        batch = session.get(PaperOrderBatch, order.batch_id)
        assert batch is not None
        snapshot = batch.snapshot_id
    unknown = action("dividend", payable_session=None)
    assert (
        post_action(
            database,
            owner,
            action=unknown,
            snapshot_id=snapshot,
            calendar=calendar(),
            session_date=date(2030, 1, 8),
            observed_at=at(8),
            live=False,
        )
        is not None
    )
    before = read_portfolio(database, owner)
    assert before.state.entitlements[0].quantity == "2.000000"
    assert (
        post_order(
            database,
            pending,
            calendar=calendar(),
            market=evidence_for(database, pending, day=8),
            observed_at=at(8),
            actions=(unknown,),
        )
        is None
    )
    assert read_portfolio(database, owner) == before
