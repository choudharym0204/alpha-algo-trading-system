from __future__ import annotations

"""Adapter â†’ BrokerOrderEvent â†’ OrderExecutionState round-trip tests.

This is THE integration test for the paper foundation: it proves that events
emitted by the paper adapter can be applied through the verified P6-003
execution state machine to reach terminal FILLED / REJECTED states, with the
exact-quantity and transition invariants enforced.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from alpha_algo_broker_adapters import (
    BrokerCredentialsRef,
    BrokerOrderRequest,
    BrokerOrderStatus,
    OrderSide,
    OrderType,
    TradingMode,
)
from alpha_algo_contracts import RiskDecision, RiskDecisionResult
from alpha_algo_execution_engine import (
    BrokerSubmissionGuard,
    InvalidOrderTransition,
    OrderEventType,
    OrderExecutionState,
    OrderLifecycle,
    OrderState,
)
from alpha_algo_paper_trading import (
    PaperBrokerAdapter,
    PaperReferencePrice,
    paper_order_id,
)

FIXED_NOW = datetime(2026, 3, 1, 9, 30, tzinfo=UTC)
SIGNAL_ID = UUID("30000000-0000-0000-0000-000000000003")
STRATEGY_ID = UUID("40000000-0000-0000-0000-000000000004")
BROKER_ACCOUNT_ID = UUID("10000000-0000-0000-0000-000000000001")
INSTRUMENT_ID = UUID("20000000-0000-0000-0000-000000000002")
CLIENT_ORDER_ID = "paper-order-rt-1"

REFERENCE = PaperReferencePrice(
    instrument_id=INSTRUMENT_ID,
    last=Decimal("100.00"),
    bid=Decimal("99.50"),
    ask=Decimal("100.50"),
    reference_at=FIXED_NOW,
)


def _approved_decision() -> RiskDecision:
    return RiskDecision(
        decision_id=UUID("50000000-0000-0000-0000-000000000005"),
        request_id=UUID("60000000-0000-0000-0000-000000000006"),
        signal_id=SIGNAL_ID,
        strategy_id=STRATEGY_ID,
        instrument_id=INSTRUMENT_ID,
        decision=RiskDecisionResult.APPROVED,
        reason_code="ALL_RULES_PASSED",
        reason="all configured risk rules passed",
        rule_id="core.risk-rule-engine",
        evaluated_at=FIXED_NOW,
        approval_id=UUID("70000000-0000-0000-0000-000000000007"),
        expires_at=FIXED_NOW + timedelta(seconds=30),
    )


def _submitted_lifecycle() -> tuple[OrderLifecycle, str]:
    """Drive a lifecycle to SUBMISSION_REQUESTED through the real guard."""
    order_id = paper_order_id(BROKER_ACCOUNT_ID, CLIENT_ORDER_ID)
    lifecycle = OrderLifecycle(order_id=order_id).transition_to(
        OrderState.INTERNAL_ORDER_CREATED,
        occurred_at=FIXED_NOW,
        reason="internal order created",
    )
    guard = BrokerSubmissionGuard()
    next_lifecycle, intent = guard.request_submission(
        lifecycle=lifecycle,
        risk_decision=_approved_decision(),
        signal_id=SIGNAL_ID,
        strategy_id=STRATEGY_ID,
        instrument_id=INSTRUMENT_ID,
        requested_at=FIXED_NOW + timedelta(seconds=1),
        metadata={"client_order_id": CLIENT_ORDER_ID},
    )
    return next_lifecycle, str(intent.risk_approval_id)


def _paper_request(
    *,
    side: OrderSide = OrderSide.BUY,
    order_type: OrderType = OrderType.MARKET,
    quantity: int = 10,
    limit_price: Decimal | None = None,
    risk_approval_id: str = "risk-approval-1",
) -> BrokerOrderRequest:
    return BrokerOrderRequest(
        broker_account_id=BROKER_ACCOUNT_ID,
        instrument_id=INSTRUMENT_ID,
        trading_mode=TradingMode.PAPER,
        client_order_id=CLIENT_ORDER_ID,
        side=side,
        order_type=order_type,
        quantity=quantity,
        risk_approval_id=risk_approval_id,
        limit_price=limit_price,
        metadata={
            "order_id": str(paper_order_id(BROKER_ACCOUNT_ID, CLIENT_ORDER_ID)),
        },
    )


def _connected_adapter() -> PaperBrokerAdapter:
    adapter = PaperBrokerAdapter(
        clock=lambda: FIXED_NOW,
        reference_prices={INSTRUMENT_ID: REFERENCE},
    )
    asyncio.run(
        adapter.connect(
            BrokerCredentialsRef(
                broker_name="paper",
                account_identifier="paper-account-1",
                secret_ref="__MUST_NOT_BE_READ__",
            )
        )
    )
    return adapter


def _run(coro):
    return asyncio.run(coro)


def test_market_order_round_trip_reaches_filled_terminal_state() -> None:
    lifecycle, risk_approval_id = _submitted_lifecycle()
    assert lifecycle.state is OrderState.SUBMISSION_REQUESTED

    adapter = _connected_adapter()
    response = _run(
        adapter.submit_order(
            _paper_request(risk_approval_id=risk_approval_id)
        )
    )
    assert response.status is BrokerOrderStatus.ACCEPTED
    assert response.broker_order_id is not None

    events = adapter.pending_events()
    assert [e.event_type for e in events] == [
        OrderEventType.BROKER_ACKNOWLEDGED,
        OrderEventType.FILL,
    ]

    state = OrderExecutionState(
        lifecycle=lifecycle, order_quantity=Decimal("10")
    )
    state = state.apply_event(events[0])
    assert state.lifecycle.state is OrderState.BROKER_ACKNOWLEDGED
    assert state.filled_quantity == Decimal("0")

    state = state.apply_event(events[1])
    assert state.lifecycle.state is OrderState.FILLED
    assert state.filled_quantity == Decimal("10")
    assert state.lifecycle.is_terminal
    assert state.broker_order_id == response.broker_order_id


def test_fill_event_completes_exact_quantity() -> None:
    lifecycle, risk_approval_id = _submitted_lifecycle()
    adapter = _connected_adapter()
    response = _run(
        adapter.submit_order(
            _paper_request(quantity=25, risk_approval_id=risk_approval_id)
        )
    )
    assert response.status is BrokerOrderStatus.ACCEPTED
    events = adapter.pending_events()
    fill = events[1]
    assert fill.event_type is OrderEventType.FILL
    assert fill.fill_quantity == Decimal("25")

    state = OrderExecutionState(lifecycle=lifecycle, order_quantity=Decimal("25"))
    state = state.apply_event(events[0]).apply_event(fill)
    assert state.lifecycle.state is OrderState.FILLED
    assert state.filled_quantity == Decimal("25")


def test_fill_without_ack_is_invalid_transition() -> None:
    """Documents why ACK must precede FILL in the v1 adapter."""
    lifecycle, risk_approval_id = _submitted_lifecycle()
    adapter = _connected_adapter()
    _run(adapter.submit_order(_paper_request(risk_approval_id=risk_approval_id)))
    events = adapter.pending_events()
    fill = events[1]

    state = OrderExecutionState(lifecycle=lifecycle, order_quantity=Decimal("10"))
    with pytest.raises(InvalidOrderTransition):
        state.apply_event(fill)  # SUBMISSION_REQUESTED -> FILLED has no edge


def test_rejected_order_round_trip_reaches_rejected_terminal_state() -> None:
    lifecycle, risk_approval_id = _submitted_lifecycle()
    adapter = _connected_adapter()
    response = _run(
        adapter.submit_order(
            _paper_request(
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                limit_price=Decimal("100.40"),  # below ask 100.50
                risk_approval_id=risk_approval_id,
            )
        )
    )
    assert response.status is BrokerOrderStatus.REJECTED
    assert response.broker_order_id is None

    events = adapter.pending_events()
    assert len(events) == 1
    assert events[0].event_type is OrderEventType.REJECTED
    assert events[0].fill_quantity == Decimal("0")
    assert events[0].reason

    state = OrderExecutionState(lifecycle=lifecycle, order_quantity=Decimal("10"))
    state = state.apply_event(events[0])
    assert state.lifecycle.state is OrderState.REJECTED
    assert state.lifecycle.is_terminal


def test_unsupported_order_type_reaches_rejected_terminal_state() -> None:
    lifecycle, risk_approval_id = _submitted_lifecycle()
    adapter = _connected_adapter()
    response = _run(
        adapter.submit_order(
            _paper_request(
                order_type=OrderType.STOP,
                limit_price=Decimal("101.00"),
                risk_approval_id=risk_approval_id,
            )
        )
    )
    assert response.status is BrokerOrderStatus.REJECTED
    events = adapter.pending_events()
    assert len(events) == 1
    assert events[0].event_type is OrderEventType.REJECTED

    state = OrderExecutionState(lifecycle=lifecycle, order_quantity=Decimal("10"))
    state = state.apply_event(events[0])
    assert state.lifecycle.state is OrderState.REJECTED


def test_all_emitted_events_are_timezone_aware_and_order_id_matched() -> None:
    lifecycle, risk_approval_id = _submitted_lifecycle()
    adapter = _connected_adapter()
    _run(adapter.submit_order(_paper_request(risk_approval_id=risk_approval_id)))

    events = adapter.events_for(CLIENT_ORDER_ID)
    assert len(events) == 2
    for event in events:
        assert event.order_id == lifecycle.order_id
        assert event.occurred_at.tzinfo is not None
        assert event.occurred_at.tzinfo.utcoffset(event.occurred_at) is not None
        assert event.reason.strip()
        assert event.metadata["trading_mode"] == "PAPER"
        assert event.metadata["fill_source"] == "paper_simulator"
    assert events[0].fill_quantity == Decimal("0")  # ACK carries no quantity
    assert events[1].fill_quantity == Decimal("10")  # FILL carries full quantity


def test_no_partial_fills_are_ever_emitted() -> None:
    adapter = _connected_adapter()
    _run(adapter.submit_order(_paper_request(quantity=7)))
    events = adapter.pending_events()
    assert OrderEventType.PARTIAL_FILL not in [e.event_type for e in events]


def test_duplicate_submit_does_not_double_fill_through_state_machine() -> None:
    lifecycle, risk_approval_id = _submitted_lifecycle()
    adapter = _connected_adapter()
    request = _paper_request(risk_approval_id=risk_approval_id)

    first_response = _run(adapter.submit_order(request))
    events = adapter.pending_events()

    second_response = _run(adapter.submit_order(request))
    assert second_response == first_response
    assert adapter.pending_events() == ()  # no new events on duplicate

    state = OrderExecutionState(lifecycle=lifecycle, order_quantity=Decimal("10"))
    for event in events:
        state = state.apply_event(event)
    assert state.lifecycle.state is OrderState.FILLED
    assert state.filled_quantity == Decimal("10")
