"""Phase 14 — execution/trade reconciliation tests."""

from __future__ import annotations

from uuid import uuid4

from alpha_algo_reconciliation_engine.contracts import DiscrepancyKind
from alpha_algo_reconciliation_engine.matching import MatchContext, reconcile_executions
from alpha_algo_reconciliation_engine.tolerance import Tolerance

from reconciliation_test_support import make_exec_obs


def _ctx():
    return MatchContext(run_id=uuid4(), account_id=uuid4(), broker="PAPER", trading_mode="PAPER")


def test_perfect_match():
    internal = [make_exec_obs(broker_execution_id="X1", quantity="100", price="100")]
    broker = [make_exec_obs(source="broker", broker_execution_id="X1", quantity="100", price="100")]
    result = reconcile_executions(_ctx(), internal, broker)
    assert result.matched == 1
    assert result.discrepancies == ()


def test_internal_only_execution():
    result = reconcile_executions(_ctx(), [make_exec_obs(execution_id="E1")], [])
    assert result.internal_only == 1
    assert result.discrepancies[0].kind == DiscrepancyKind.INTERNAL_ONLY


def test_broker_only_execution_is_critical():
    broker = [make_exec_obs(source="broker", broker_execution_id="X9")]
    result = reconcile_executions(_ctx(), [], broker)
    assert result.broker_only == 1
    d = result.discrepancies[0]
    assert d.kind == DiscrepancyKind.BROKER_ONLY
    assert d.severity.value == "CRITICAL"


def test_duplicate_execution():
    broker = [
        make_exec_obs(source="broker", broker_execution_id="X1"),
        make_exec_obs(source="broker", broker_execution_id="X1"),
    ]
    result = reconcile_executions(_ctx(), [], broker)
    assert any(d.kind == DiscrepancyKind.DUPLICATE_EXECUTION for d in result.discrepancies)


def test_quantity_mismatch():
    internal = [make_exec_obs(broker_execution_id="X1", quantity="100")]
    broker = [make_exec_obs(source="broker", broker_execution_id="X1", quantity="50")]
    kinds = {d.kind for d in reconcile_executions(_ctx(), internal, broker).discrepancies}
    assert DiscrepancyKind.QUANTITY_MISMATCH in kinds


def test_price_mismatch():
    internal = [make_exec_obs(broker_execution_id="X1", price="100")]
    broker = [make_exec_obs(source="broker", broker_execution_id="X1", price="101")]
    kinds = {d.kind for d in reconcile_executions(_ctx(), internal, broker).discrepancies}
    assert DiscrepancyKind.PRICE_MISMATCH in kinds


def test_price_rounding_tolerance_is_not_mismatch():
    internal = [make_exec_obs(broker_execution_id="X1", price="100.0000")]
    broker = [make_exec_obs(source="broker", broker_execution_id="X1", price="100.0001")]
    result = reconcile_executions(_ctx(), internal, broker, Tolerance())
    assert result.matched == 1


def test_fee_mismatch():
    internal = [make_exec_obs(broker_execution_id="X1", fees="10")]
    broker = [make_exec_obs(source="broker", broker_execution_id="X1", fees="15")]
    kinds = {d.kind for d in reconcile_executions(_ctx(), internal, broker).discrepancies}
    assert DiscrepancyKind.FEE_MISMATCH in kinds


def test_order_link_mismatch():
    internal = [make_exec_obs(broker_execution_id="X1", order_id=uuid4())]
    broker = [make_exec_obs(source="broker", broker_execution_id="X1", order_id=uuid4())]
    kinds = {d.kind for d in reconcile_executions(_ctx(), internal, broker).discrepancies}
    assert DiscrepancyKind.ORDER_LINK_MISMATCH in kinds
