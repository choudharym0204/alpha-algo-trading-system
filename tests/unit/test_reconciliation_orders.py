"""Phase 14 — order reconciliation tests."""

from __future__ import annotations

from uuid import uuid4

from alpha_algo_reconciliation_engine.contracts import DiscrepancyKind, EntityType
from alpha_algo_reconciliation_engine.matching import MatchContext, reconcile_orders

from reconciliation_test_support import make_order_obs


def _ctx():
    return MatchContext(run_id=uuid4(), account_id=uuid4(), broker="PAPER", trading_mode="PAPER")


def test_perfect_match():
    acc, inst = uuid4(), uuid4()
    internal = [make_order_obs(broker_order_id="B1", client_order_id="C1", account_id=acc, instrument_id=inst)]
    broker = [make_order_obs(source="broker", broker_order_id="B1", client_order_id="C1", account_id=acc, instrument_id=inst)]
    result = reconcile_orders(_ctx(), internal, broker)
    assert result.matched == 1
    assert result.discrepancies == ()


def test_internal_only():
    internal = [make_order_obs(client_order_id="C1")]
    result = reconcile_orders(_ctx(), internal, [])
    assert result.internal_only == 1
    assert result.discrepancies[0].kind == DiscrepancyKind.INTERNAL_ONLY


def test_broker_only():
    broker = [make_order_obs(source="broker", broker_order_id="B9")]
    result = reconcile_orders(_ctx(), [], broker)
    assert result.broker_only == 1
    assert result.discrepancies[0].kind == DiscrepancyKind.BROKER_ONLY


def test_status_mismatch():
    internal = [make_order_obs(broker_order_id="B1", status="FILLED")]
    broker = [make_order_obs(source="broker", broker_order_id="B1", status="PARTIALLY_FILLED")]
    result = reconcile_orders(_ctx(), internal, broker)
    kinds = {d.kind for d in result.discrepancies}
    assert DiscrepancyKind.STATUS_MISMATCH in kinds


def test_quantity_mismatch():
    internal = [make_order_obs(broker_order_id="B1", quantity=100)]
    broker = [make_order_obs(source="broker", broker_order_id="B1", quantity=50)]
    kinds = {d.kind for d in reconcile_orders(_ctx(), internal, broker).discrepancies}
    assert DiscrepancyKind.QUANTITY_MISMATCH in kinds


def test_side_mismatch():
    internal = [make_order_obs(broker_order_id="B1", side="BUY")]
    broker = [make_order_obs(source="broker", broker_order_id="B1", side="SELL")]
    kinds = {d.kind for d in reconcile_orders(_ctx(), internal, broker).discrepancies}
    assert DiscrepancyKind.SIDE_MISMATCH in kinds


def test_order_type_mismatch():
    internal = [make_order_obs(broker_order_id="B1", order_type="LIMIT")]
    broker = [make_order_obs(source="broker", broker_order_id="B1", order_type="MARKET")]
    kinds = {d.kind for d in reconcile_orders(_ctx(), internal, broker).discrepancies}
    assert DiscrepancyKind.ORDER_TYPE_MISMATCH in kinds


def test_instrument_mismatch():
    internal = [make_order_obs(broker_order_id="B1", instrument_id=uuid4())]
    broker = [make_order_obs(source="broker", broker_order_id="B1", instrument_id=uuid4())]
    kinds = {d.kind for d in reconcile_orders(_ctx(), internal, broker).discrepancies}
    assert DiscrepancyKind.INSTRUMENT_MISMATCH in kinds


def test_account_mismatch():
    internal = [make_order_obs(broker_order_id="B1", account_id=uuid4())]
    broker = [make_order_obs(source="broker", broker_order_id="B1", account_id=uuid4())]
    kinds = {d.kind for d in reconcile_orders(_ctx(), internal, broker).discrepancies}
    assert DiscrepancyKind.ACCOUNT_MISMATCH in kinds


def test_duplicate_broker_order_conflict():
    broker = [
        make_order_obs(source="broker", broker_order_id="B1"),
        make_order_obs(source="broker", broker_order_id="B1"),
    ]
    result = reconcile_orders(_ctx(), [], broker)
    assert any(d.kind == DiscrepancyKind.CONFLICT for d in result.discrepancies)
