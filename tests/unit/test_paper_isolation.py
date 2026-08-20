from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import uuid4

from alpha_algo_broker_adapters import OrderSide
from alpha_algo_paper_trading import PaperBrokerAdapter, paper_order_id
from alpha_algo_paper_runtime import PaperTradingService

from paper_test_support import (
    FIXED_NOW,
    connect_broker,
    make_account,
    make_reference,
)


def _run(coro):
    return asyncio.run(coro)


def _service(account, inst, last="100"):
    refs = {inst: make_reference(inst, last=last)}
    broker = PaperBrokerAdapter(clock=lambda: FIXED_NOW, reference_prices=refs)
    connect_broker(broker, account.account_id)
    return PaperTradingService(
        account=account, broker=broker, reference_prices=refs, clock=lambda: FIXED_NOW
    )


def test_two_accounts_have_isolated_funds() -> None:
    inst = uuid4()
    a1 = make_account(starting_capital="100000")
    a2 = make_account(starting_capital="50000")
    s1 = _service(a1, inst)
    s2 = _service(a2, inst)

    _run(s1.submit(instrument_id=inst, side=OrderSide.BUY, quantity=10))
    assert s1.funds.available_cash == Decimal("99000")
    assert s2.funds.available_cash == Decimal("50000")  # untouched


def test_two_runs_isolate_order_identity() -> None:
    inst = uuid4()
    run_a = uuid4()
    run_b = uuid4()
    a1 = make_account(paper_run_id=run_a)
    a2 = make_account(paper_run_id=run_b)
    assert a1.paper_run_id != a2.paper_run_id

    # Same client order id across runs/accounts yields distinct order ids.
    oid_a = paper_order_id(a1.account_id, "same-client-id")
    oid_b = paper_order_id(a2.account_id, "same-client-id")
    assert oid_a != oid_b


def test_two_accounts_do_not_share_positions() -> None:
    inst = uuid4()
    a1 = make_account(starting_capital="100000")
    a2 = make_account(starting_capital="100000")
    s1 = _service(a1, inst)
    s2 = _service(a2, inst)

    _run(s1.submit(instrument_id=inst, side=OrderSide.BUY, quantity=10))
    assert len(_run(s1.positions())) == 1
    assert _run(s2.positions()) == []  # isolated
