from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import uuid4

from alpha_algo_broker_adapters import OrderSide

from paper_test_support import (
    FIXED_NOW,
    connect_broker,
    make_account,
    make_reference,
)
from alpha_algo_paper_trading import PaperBrokerAdapter
from alpha_algo_paper_runtime import PaperTradingService


def _run(coro):
    return asyncio.run(coro)


# Module-level fixed identities: the same process reuses them across runs so the
# full outcome (including ids) is comparable for the determinism assertion.
_FIXED_INST = uuid4()
_FIXED_ACCOUNT_ID = uuid4()
_FIXED_RUN_ID = uuid4()


def _scenario():
    """Run the same deterministic scenario and return (outcomes, funds)."""
    account = make_account(
        account_id=_FIXED_ACCOUNT_ID, paper_run_id=_FIXED_RUN_ID, starting_capital="100000"
    )
    refs = {_FIXED_INST: make_reference(_FIXED_INST, last="100")}
    broker = PaperBrokerAdapter(clock=lambda: FIXED_NOW, reference_prices=refs)
    connect_broker(broker, account.account_id)
    svc = PaperTradingService(
        account=account, broker=broker, reference_prices=refs, clock=lambda: FIXED_NOW
    )
    buy = _run(svc.submit(instrument_id=_FIXED_INST, side=OrderSide.BUY, quantity=10))
    svc.set_reference_price(_FIXED_INST, make_reference(_FIXED_INST, last="110"))
    sell = _run(svc.submit(instrument_id=_FIXED_INST, side=OrderSide.SELL, quantity=10))
    return (buy, sell, svc.funds.available_cash)


def test_identical_inputs_produce_identical_results() -> None:
    a = _scenario()
    b = _scenario()
    assert a[0] == b[0]
    assert a[1] == b[1]
    assert a[2] == b[2]


def test_deterministic_cash_after_round_trip() -> None:
    _, _, cash = _scenario()
    # 100000 - 1000 (buy) + 1100 (sell) = 100100, always.
    assert cash == Decimal("100100")


def test_deterministic_fill_prices() -> None:
    buy, sell, _ = _scenario()
    assert buy.fill_price == Decimal("100")
    assert sell.fill_price == Decimal("110")
    assert buy.net_cash == Decimal("-1000")
    assert sell.net_cash == Decimal("1100")
