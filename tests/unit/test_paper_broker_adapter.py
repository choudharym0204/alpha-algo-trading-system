from __future__ import annotations

import asyncio
from datetime import UTC, datetime
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
from alpha_algo_execution_engine import OrderEventType
from alpha_algo_paper_trading import (
    ClientOrderIdConflictError,
    PaperAdapterError,
    PaperBrokerAdapter,
    PaperMarketDataUnavailableError,
    PaperModeViolationError,
    PaperReferencePrice,
    paper_order_id,
)

FIXED_NOW = datetime(2026, 3, 1, 9, 30, tzinfo=UTC)
BROKER_ACCOUNT_ID = UUID("10000000-0000-0000-0000-000000000001")
INSTRUMENT_ID = UUID("20000000-0000-0000-0000-000000000002")
CLIENT_ORDER_ID = "paper-order-1"

REFERENCE = PaperReferencePrice(
    instrument_id=INSTRUMENT_ID,
    last=Decimal("100.00"),
    bid=Decimal("99.50"),
    ask=Decimal("100.50"),
    reference_at=FIXED_NOW,
)


def _request(
    *,
    side: OrderSide = OrderSide.BUY,
    order_type: OrderType = OrderType.MARKET,
    quantity: int = 10,
    client_order_id: str = CLIENT_ORDER_ID,
    limit_price: Decimal | None = None,
    trading_mode: TradingMode = TradingMode.PAPER,
    metadata: dict[str, object] | None = None,
) -> BrokerOrderRequest:
    return BrokerOrderRequest(
        broker_account_id=BROKER_ACCOUNT_ID,
        instrument_id=INSTRUMENT_ID,
        trading_mode=trading_mode,
        client_order_id=client_order_id,
        side=side,
        order_type=order_type,
        quantity=quantity,
        risk_approval_id="risk-approval-1",
        limit_price=limit_price,
        metadata=(
            metadata
            if metadata is not None
            else {
                "order_id": str(paper_order_id(BROKER_ACCOUNT_ID, client_order_id)),
            }
        ),
    )


def _adapter(*, reference_prices: dict[UUID, PaperReferencePrice] | None = None) -> PaperBrokerAdapter:
    adapter = PaperBrokerAdapter(
        clock=lambda: FIXED_NOW,
        reference_prices=(
            reference_prices
            if reference_prices is not None
            else {INSTRUMENT_ID: REFERENCE}
        ),
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


def _submit(adapter: PaperBrokerAdapter, request: BrokerOrderRequest):
    return asyncio.run(adapter.submit_order(request))


# -- Protocol conformance ---------------------------------------------------


def test_paper_adapter_exposes_full_broker_adapter_surface() -> None:
    adapter = _adapter()
    for name in (
        "capabilities",
        "connect",
        "disconnect",
        "get_quote",
        "submit_order",
        "cancel_order",
        "get_positions",
    ):
        assert hasattr(adapter, name), f"missing BrokerAdapter member {name}"


def test_paper_adapter_async_methods_are_coroutine_functions() -> None:
    adapter = _adapter()
    for name in (
        "connect",
        "disconnect",
        "get_quote",
        "submit_order",
        "cancel_order",
        "get_positions",
    ):
        import inspect

        assert inspect.iscoroutinefunction(getattr(adapter, name)), name


def test_paper_capabilities_never_support_live_trading() -> None:
    capabilities = _adapter().capabilities
    assert capabilities.broker_name == "paper"
    assert capabilities.supports_live_trading is False
    assert capabilities.supports_market_data is False
    assert capabilities.supports_order_submission is True
    assert capabilities.supports_order_cancel is False  # v1: no working orders
    assert capabilities.supports_positions is True


# -- connect / disconnect ---------------------------------------------------


def test_connect_requires_paper_broker_name() -> None:
    adapter = PaperBrokerAdapter(clock=lambda: FIXED_NOW, reference_prices={})
    with pytest.raises(PaperAdapterError, match="broker_name"):
        asyncio.run(
            adapter.connect(
                BrokerCredentialsRef(
                    broker_name="live",
                    account_identifier="x",
                    secret_ref="s",
                )
            )
        )


def test_connect_requires_account_identifier() -> None:
    adapter = PaperBrokerAdapter(clock=lambda: FIXED_NOW, reference_prices={})
    with pytest.raises(PaperAdapterError, match="account_identifier"):
        asyncio.run(
            adapter.connect(
                BrokerCredentialsRef(
                    broker_name="paper",
                    account_identifier="   ",
                    secret_ref="s",
                )
            )
        )


def test_connect_never_authenticates_and_ignores_secret() -> None:
    adapter = PaperBrokerAdapter(clock=lambda: FIXED_NOW, reference_prices={})
    session = asyncio.run(
        adapter.connect(
            BrokerCredentialsRef(
                broker_name="paper",
                account_identifier="paper-account-1",
                secret_ref="__MUST_NOT_BE_READ__",
            )
        )
    )
    assert session.connected is True
    assert session.authenticated is False  # paper performs no authentication
    assert session.broker_name == "paper"
    assert session.expires_at is None


def test_disconnect_clears_connection() -> None:
    adapter = _adapter()
    asyncio.run(adapter.disconnect())
    with pytest.raises(PaperAdapterError, match="not connected"):
        _submit(adapter, _request())


def test_submit_requires_connection() -> None:
    adapter = PaperBrokerAdapter(
        clock=lambda: FIXED_NOW, reference_prices={INSTRUMENT_ID: REFERENCE}
    )
    with pytest.raises(PaperAdapterError, match="not connected"):
        _submit(adapter, _request())


# -- mode isolation ---------------------------------------------------------


def test_submit_rejects_live_mode() -> None:
    adapter = _adapter()
    with pytest.raises(PaperModeViolationError, match="PAPER"):
        _submit(adapter, _request(trading_mode=TradingMode.LIVE))


def test_submit_rejects_backtest_mode() -> None:
    adapter = _adapter()
    with pytest.raises(PaperModeViolationError, match="PAPER"):
        _submit(adapter, _request(trading_mode=TradingMode.BACKTEST))


# -- fill behavior ----------------------------------------------------------


def test_market_buy_fills_at_reference_last() -> None:
    adapter = _adapter()
    response = _submit(adapter, _request(side=OrderSide.BUY, order_type=OrderType.MARKET))
    assert response.status is BrokerOrderStatus.ACCEPTED
    assert response.broker_order_id == f"paper-{paper_order_id(BROKER_ACCOUNT_ID, CLIENT_ORDER_ID).hex}"

    events = adapter.pending_events()
    assert [event.event_type for event in events] == [
        OrderEventType.BROKER_ACKNOWLEDGED,
        OrderEventType.FILL,
    ]
    fill = events[1]
    assert fill.fill_quantity == Decimal("10")
    assert fill.metadata["trading_mode"] == "PAPER"
    assert fill.metadata["fill_source"] == "paper_simulator"
    assert Decimal(fill.metadata["paper_fill_price"]) == Decimal("100.00")


def test_market_sell_fills_at_reference_last() -> None:
    adapter = _adapter()
    response = _submit(adapter, _request(side=OrderSide.SELL, order_type=OrderType.MARKET))
    assert response.status is BrokerOrderStatus.ACCEPTED
    fill = adapter.pending_events()[1]
    assert Decimal(fill.metadata["paper_fill_price"]) == Decimal("100.00")


def test_limit_buy_fills_when_limit_above_ask() -> None:
    adapter = _adapter()
    response = _submit(
        adapter,
        _request(
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            limit_price=Decimal("100.60"),
        ),
    )
    assert response.status is BrokerOrderStatus.ACCEPTED
    fill = adapter.pending_events()[1]
    assert Decimal(fill.metadata["paper_fill_price"]) == Decimal("100.50")  # ask


def test_limit_buy_rejects_when_limit_below_ask() -> None:
    adapter = _adapter()
    response = _submit(
        adapter,
        _request(
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            limit_price=Decimal("100.40"),
        ),
    )
    assert response.status is BrokerOrderStatus.REJECTED
    assert "not executable" in (response.reason or "")
    events = adapter.pending_events()
    assert len(events) == 1
    assert events[0].event_type is OrderEventType.REJECTED
    assert events[0].fill_quantity == Decimal("0")


def test_limit_sell_fills_when_limit_below_bid() -> None:
    adapter = _adapter()
    response = _submit(
        adapter,
        _request(
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            limit_price=Decimal("99.40"),
        ),
    )
    assert response.status is BrokerOrderStatus.ACCEPTED
    fill = adapter.pending_events()[1]
    assert Decimal(fill.metadata["paper_fill_price"]) == Decimal("99.50")  # bid


def test_limit_sell_rejects_when_limit_above_bid() -> None:
    adapter = _adapter()
    response = _submit(
        adapter,
        _request(
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            limit_price=Decimal("99.60"),
        ),
    )
    assert response.status is BrokerOrderStatus.REJECTED


def test_stop_order_type_rejected_with_event() -> None:
    adapter = _adapter()
    response = _submit(
        adapter,
        _request(
            order_type=OrderType.STOP,
            limit_price=Decimal("101.00"),
        ),
    )
    assert response.status is BrokerOrderStatus.REJECTED
    assert "unsupported order type" in (response.reason or "")
    events = adapter.pending_events()
    assert len(events) == 1
    assert events[0].event_type is OrderEventType.REJECTED


def test_stop_limit_order_type_rejected_with_event() -> None:
    adapter = _adapter()
    response = _submit(
        adapter,
        _request(order_type=OrderType.STOP_LIMIT),
    )
    assert response.status is BrokerOrderStatus.REJECTED


def test_missing_reference_price_rejects() -> None:
    adapter = _adapter(reference_prices={})
    response = _submit(adapter, _request())
    assert response.status is BrokerOrderStatus.REJECTED
    assert "no reference price" in (response.reason or "")
    events = adapter.pending_events()
    assert len(events) == 1
    assert events[0].event_type is OrderEventType.REJECTED


def test_reference_price_for_wrong_instrument_is_rejected() -> None:
    adapter = _adapter()
    request = _request()
    # tamper: submit with a request whose instrument has no reference by using
    # an instrument not in the adapter mapping
    other_instrument_request = BrokerOrderRequest(
        broker_account_id=BROKER_ACCOUNT_ID,
        instrument_id=UUID("99999999-0000-0000-0000-000000000009"),
        trading_mode=TradingMode.PAPER,
        client_order_id="paper-order-other",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=10,
        risk_approval_id="risk-approval-1",
        metadata={
            "order_id": str(
                paper_order_id(BROKER_ACCOUNT_ID, "paper-order-other")
            ),
        },
    )
    response = _submit(adapter, other_instrument_request)
    assert response.status is BrokerOrderStatus.REJECTED
    assert "no reference price" in (response.reason or "")


def test_get_quote_always_raises() -> None:
    adapter = _adapter()
    with pytest.raises(PaperMarketDataUnavailableError, match="injected"):
        asyncio.run(
            adapter.get_quote(INSTRUMENT_ID)
        )


def test_cancel_order_fails_loud() -> None:
    adapter = _adapter()
    with pytest.raises(PaperAdapterError, match="cancellation unsupported"):
        asyncio.run(
            adapter.cancel_order("paper-anything")
        )


# -- idempotency ------------------------------------------------------------


def test_duplicate_submission_returns_identical_response_and_no_new_events() -> None:
    adapter = _adapter()
    first = _submit(adapter, _request())
    first_events = adapter.pending_events()

    second = _submit(adapter, _request())
    second_events = adapter.pending_events()

    assert second == first
    assert second_events == ()
    assert adapter.events_for(CLIENT_ORDER_ID) == first_events


def test_duplicate_submission_with_different_payload_raises_conflict() -> None:
    adapter = _adapter()
    _submit(adapter, _request(quantity=10))
    with pytest.raises(ClientOrderIdConflictError, match="different payload"):
        _submit(adapter, _request(quantity=20))


def test_duplicate_submission_with_tampered_order_id_fails_loud() -> None:
    """M1 regression: the metadata order-id contract must be enforced on
    idempotent retries too, not only on the first submission."""
    adapter = _adapter()
    _submit(adapter, _request())
    with pytest.raises(PaperAdapterError, match="does not match"):
        _submit(
            adapter,
            _request(
                metadata={"order_id": "00000000-0000-0000-0000-000000000000"}
            ),
        )


def test_duplicate_submission_with_missing_order_id_fails_loud() -> None:
    """M1 regression: a retry with a missing metadata order id must not
    silently return the cached response."""
    adapter = _adapter()
    _submit(adapter, _request())
    with pytest.raises(PaperAdapterError, match="order_id"):
        _submit(adapter, _request(metadata={}))


def test_cross_account_same_client_order_id_does_not_collide() -> None:
    """M3 regression: the idempotency cache is scoped per broker account, so
    two accounts may legitimately reuse the same client order id."""
    adapter = _adapter()
    other_account = UUID("10000000-0000-0000-0000-000000000099")
    other_request = BrokerOrderRequest(
        broker_account_id=other_account,
        instrument_id=INSTRUMENT_ID,
        trading_mode=TradingMode.PAPER,
        client_order_id=CLIENT_ORDER_ID,  # same client id as the first order
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=5,
        risk_approval_id="risk-approval-1",
        metadata={"order_id": str(paper_order_id(other_account, CLIENT_ORDER_ID))},
    )

    first = _submit(adapter, _request())
    second = _submit(adapter, other_request)

    assert first.status is BrokerOrderStatus.ACCEPTED
    assert second.status is BrokerOrderStatus.ACCEPTED
    assert first.broker_order_id != second.broker_order_id
    # The adapter-level events_for(client_order_id) resolves the most recent
    # account for that client id (single-account engine convenience); the
    # account-scoped book API is exact. Both orders emitted ACK + FILL.
    assert len(adapter.events_for(CLIENT_ORDER_ID)) == 2


def test_limit_buy_fills_at_exact_ask_boundary() -> None:
    adapter = _adapter()
    response = _submit(
        adapter,
        _request(
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            limit_price=Decimal("100.50"),  # == ask
        ),
    )
    assert response.status is BrokerOrderStatus.ACCEPTED


def test_limit_sell_fills_at_exact_bid_boundary() -> None:
    adapter = _adapter()
    response = _submit(
        adapter,
        _request(
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            limit_price=Decimal("99.50"),  # == bid
        ),
    )
    assert response.status is BrokerOrderStatus.ACCEPTED


def test_naive_clock_output_raises_paper_adapter_error() -> None:
    """L4 regression: a naive clock output must raise PaperAdapterError, not a
    raw ValueError. The clock is valid for connect, then goes naive for the
    submit timestamp."""
    calls = {"n": 0}

    def flaky_clock() -> datetime:
        calls["n"] += 1
        if calls["n"] == 1:  # connect's checked_at
            return FIXED_NOW
        return datetime(2026, 3, 1, 9, 30)  # naive for submit's accepted_at

    adapter = PaperBrokerAdapter(
        clock=flaky_clock,
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
    with pytest.raises(PaperAdapterError, match="timezone-aware"):
        _submit(adapter, _request())


# -- metadata order_id contract ---------------------------------------------


def test_submit_requires_metadata_order_id() -> None:
    adapter = _adapter()
    with pytest.raises(PaperAdapterError, match="order_id"):
        _submit(adapter, _request(metadata={}))


def test_submit_rejects_mismatched_metadata_order_id() -> None:
    adapter = _adapter()
    with pytest.raises(PaperAdapterError, match="does not match"):
        _submit(
            adapter,
            _request(
                metadata={
                    "order_id": "00000000-0000-0000-0000-000000000000",
                }
            ),
        )


def test_submit_rejects_invalid_metadata_order_id() -> None:
    adapter = _adapter()
    with pytest.raises(PaperAdapterError, match="valid UUID"):
        _submit(adapter, _request(metadata={"order_id": "not-a-uuid"}))


# -- determinism ------------------------------------------------------------


def test_identical_inputs_produce_identical_events_across_adapters() -> None:
    first = _adapter()
    second = _adapter()
    request = _request(side=OrderSide.BUY, order_type=OrderType.MARKET)

    first_response = _submit(first, request)
    first_events = first.pending_events()
    second_response = _submit(second, request)
    second_events = second.pending_events()

    assert first_response == second_response
    assert first_events == second_events
