"""Phase 13 — end-to-end test (Execution → Position → P&L → read-back)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from alpha_algo_pnl_engine.contracts import PnlApplyStatus, PnlStatus
from alpha_algo_pnl_engine.engine import PnlEngine
from alpha_algo_position_engine.arithmetic import apply_buy, apply_sell

from pnl_test_support import (
    InMemoryPnlRepository,
    make_cost,
    make_fill,
    make_position,
    make_price,
)


def _t():
    return datetime(2026, 8, 20, 10, 0, tzinfo=UTC)


def test_execution_to_position_to_pnl_end_to_end():
    acc, strat, inst = uuid4(), uuid4(), uuid4()
    position_id = uuid4()
    repo = InMemoryPnlRepository()
    engine = PnlEngine(repository=repo, global_halt_active=lambda: False)

    # Phase 11 authoritatively applies the fills (quantity + weighted average).
    d1 = apply_buy(quantity=0, average_price=None, opened_at=None, closed_at=None,
                   fill_quantity=100, fill_price=Decimal("100"), occurred_at=_t())
    d2 = apply_buy(quantity=d1.quantity, average_price=d1.average_price, opened_at=d1.opened_at,
                   closed_at=None, fill_quantity=50, fill_price=Decimal("110"), occurred_at=_t())
    # position before the sell: 150 @ 103.3333
    before = make_position(position_id=position_id, account_id=acc, strategy_run_id=strat,
                           instrument_id=inst, quantity=d2.quantity, average_price=str(d2.average_price))

    # P&L realizes the SELL of 40 @ 120 against the weighted-average cost.
    sell = make_fill(account_id=acc, strategy_run_id=strat, instrument_id=inst,
                     side="SELL", quantity="40", price="120", execution_id="e1", occurred_at=_t())
    result = engine.record_fill(fill=sell, position_before=before, costs=(make_cost("20"),))

    assert result.status == PnlApplyStatus.APPLIED
    assert result.realized.gross_pnl == Decimal("666.6680")  # (120 - 103.3333) * 40
    assert result.realized.costs == Decimal("20.0000")
    assert result.realized.net_pnl == Decimal("646.6680")

    # Phase 11 applies the sell to derive the post-sell position (110 @ 103.3333).
    d3 = apply_sell(quantity=d2.quantity, average_price=d2.average_price, opened_at=d2.opened_at,
                    closed_at=None, fill_quantity=40, fill_price=Decimal("120"), occurred_at=_t())
    after = make_position(position_id=position_id, account_id=acc, strategy_run_id=strat,
                          instrument_id=inst, quantity=d3.quantity, average_price=str(d3.average_price))

    # Position-level read model: realized + unrealized.
    realized = repo.realized_pnl_for_position(position_id=position_id)
    assert realized == Decimal("646.6680")

    pnl = engine.position_pnl(position=after, price=make_price(inst, "125", _t()),
                              realized_pnl=realized, now=_t())
    assert pnl.quantity == 110
    assert pnl.unrealized_pnl == Decimal("2383.3370")  # (125 - 103.3333) * 110
    assert pnl.market_value == Decimal("13750.0000")   # 125 * 110
    assert pnl.status == PnlStatus.READY

    # Account aggregation over the persisted event.
    accounts = engine.account_pnl(repo.list_events(account_id=acc))
    assert len(accounts) == 1
    assert accounts[0].realized_gross == Decimal("666.6680")
    assert accounts[0].realized_net == Decimal("646.6680")
    assert accounts[0].trade_count == 1
