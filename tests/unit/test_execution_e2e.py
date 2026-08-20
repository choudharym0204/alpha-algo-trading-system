"""Phase 9 — end-to-end: TradingIntent → OMS → Execution Engine → FILLED.

Uses the in-memory OMS store and TEST in-memory adapter. No real broker.
"""

from decimal import Decimal
from uuid import uuid4

import pytest

from alpha_algo_execution_engine.adapter import ExecutionRequest, InMemoryAdapter
from alpha_algo_execution_engine.engine import ExecutionEngine
from alpha_algo_execution_engine.events import OrderEventType
from alpha_algo_execution_engine.identity import compute_execution_id
from alpha_algo_execution_engine.lifecycle import OrderState
from alpha_algo_oms.identity import compute_order_identity_key
from alpha_algo_oms.repository import OrderRepository
from alpha_algo_oms.service import OmsService

from execution_test_support import InMemoryExecutionRepository, make_event
from oms_test_support import InMemoryOmsStore, OmsSessionFactory, make_intent


def _request_from_intent(intent, order_id):
    identity_key = compute_order_identity_key(
        orchestration_id=intent.orchestration_id,
        signal_id=intent.signal_id,
        strategy_id=intent.strategy_id,
        account_id=intent.account_id,
        instrument_id=intent.instrument_id,
        side=intent.action,
        quantity=int(intent.quantity),
        order_type=intent.order_type,
        trading_mode=intent.trading_mode,
        risk_approval_id=str(intent.approval_id),
    )
    return ExecutionRequest(
        order_id=order_id,
        client_order_id=f"ord-{intent.orchestration_id}",
        execution_id=compute_execution_id(order_id, identity_key),
        correlation_id=str(intent.correlation_id),
        account_id=intent.account_id,
        instrument_id=intent.instrument_id,
        signal_id=intent.signal_id,
        strategy_id=intent.strategy_id,
        strategy_version=intent.strategy_version,
        side=intent.action,
        quantity=int(intent.quantity),
        order_type=intent.order_type,
        limit_price=intent.limit_price,
        trading_mode=intent.trading_mode,
        risk_approval_id=str(intent.approval_id),
        approval_expires_at=intent.approval_expires_at,
        binding_hash=intent.binding_hash,
        orchestration_id=intent.orchestration_id,
    )


def test_full_chain_intent_to_filled():
    intent = make_intent(quantity="100", account_id=uuid4())

    # Phase 8: OMS -> SUBMISSION_REQUESTED (no broker).
    store = InMemoryOmsStore()
    oms = OmsService(
        repository=OrderRepository(OmsSessionFactory(store)),
        global_halt_active=lambda: False,
    )
    result = oms.create_order(intent)
    assert result.status == OrderState.SUBMISSION_REQUESTED

    # Phase 9: Execution Engine consumes the OMS-approved order.
    adapter = InMemoryAdapter()
    exec_repo = InMemoryExecutionRepository()
    engine = ExecutionEngine(
        adapter=adapter,
        repository=exec_repo,
        global_halt_active=lambda: False,
    )
    req = _request_from_intent(intent, result.order_id)

    # Seed the execution store with the OMS's SUBMISSION_REQUESTED state.
    exec_repo.register_order(result.order_id, 100)

    outcome = engine.submit(req)
    assert outcome.submission_state.value == "ACKNOWLEDGED"
    assert outcome.order_state == OrderState.BROKER_ACKNOWLEDGED
    assert len(adapter.submissions) == 1

    # Execution events drive the order to FILLED (ACK already applied by submit).
    state = exec_repo.load_execution_state(result.order_id)
    assert state.lifecycle.state == OrderState.BROKER_ACKNOWLEDGED
    engine.apply_event(
        make_event(
            result.order_id,
            OrderEventType.PARTIAL_FILL,
            fill_quantity=Decimal("60"),
            source_event_id="f1",
        )
    )
    final = engine.apply_event(
        make_event(
            result.order_id,
            OrderEventType.FILL,
            fill_quantity=Decimal("40"),
            source_event_id="f2",
        )
    )
    assert final.lifecycle.state == OrderState.FILLED
    assert final.filled_quantity == Decimal("100")


def test_live_intent_never_reaches_execution():
    intent = make_intent(quantity="10", trading_mode="LIVE", account_id=uuid4())

    store = InMemoryOmsStore()
    oms = OmsService(
        repository=OrderRepository(OmsSessionFactory(store)),
        global_halt_active=lambda: False,
    )
    # Phase 8 already blocks LIVE before the OMS can create the order.
    from alpha_algo_oms.errors import TradingModeError

    with pytest.raises(TradingModeError):
        oms.create_order(intent)
