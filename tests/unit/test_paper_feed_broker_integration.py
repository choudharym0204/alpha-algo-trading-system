from __future__ import annotations

"""Round-trip tests: feed output -> real P8-001 paper machinery.

These prove that a feed-built reference map plugs into the verified
``PaperBrokerAdapter`` with zero adapter changes: MARKET fills at the mapped
``last``, LIMIT orders honestly reject on missing quote legs, and orders for
instruments absent from the feed-built map reject with the adapter's own
error path.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from alpha_algo_broker_adapters import (
    BrokerCredentialsRef,
    BrokerOrderRequest,
    BrokerOrderStatus,
    OrderSide,
    OrderType,
    TradingMode,
)
from alpha_algo_contracts import MarketTick
from alpha_algo_execution_engine import OrderEventType
from alpha_algo_paper_feed import tick_to_reference
from alpha_algo_paper_trading import PaperBrokerAdapter, paper_order_id

FIXED_NOW = datetime(2026, 3, 1, 9, 30, tzinfo=UTC)
BROKER_ACCOUNT_ID = UUID("10000000-0000-0000-0000-000000000001")
INSTRUMENT_ID = UUID("20000000-0000-0000-0000-000000000002")
CLIENT_ORDER_ID = "paper-feed-rt-1"


def _tick(
    *,
    ltp: Decimal = Decimal("100.00"),
    bid: Decimal | None = Decimal("99.50"),
    ask: Decimal | None = Decimal("100.50"),
    source_sequence: str = "feed-seq-001",
) -> MarketTick:
    return MarketTick(
        instrument_id=INSTRUMENT_ID,
        exchange="NSE",
        symbol="RELIANCE",
        timestamp=FIXED_NOW,
        ltp=ltp,
        bid=bid,
        ask=ask,
        source_broker="test-broker",
        source_sequence=source_sequence,
        received_at=FIXED_NOW,
    )


def _request(
    *,
    side: OrderSide = OrderSide.BUY,
    order_type: OrderType = OrderType.MARKET,
    limit_price: Decimal | None = None,
    risk_approval_id: str = "risk-approval-feed",
) -> BrokerOrderRequest:
    return BrokerOrderRequest(
        broker_account_id=BROKER_ACCOUNT_ID,
        instrument_id=INSTRUMENT_ID,
        trading_mode=TradingMode.PAPER,
        client_order_id=CLIENT_ORDER_ID,
        side=side,
        order_type=order_type,
        quantity=10,
        risk_approval_id=risk_approval_id,
        limit_price=limit_price,
        metadata={
            "order_id": str(paper_order_id(BROKER_ACCOUNT_ID, CLIENT_ORDER_ID)),
        },
    )


def _connected_adapter(reference_map) -> PaperBrokerAdapter:
    adapter = PaperBrokerAdapter(
        clock=lambda: FIXED_NOW,
        reference_prices=reference_map,
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


def test_feed_output_drives_paper_broker_market_fill() -> None:
    snapshot = tick_to_reference(_tick())
    adapter = _connected_adapter({INSTRUMENT_ID: snapshot})

    response = _run(adapter.submit_order(_request()))
    assert response.status is BrokerOrderStatus.ACCEPTED

    events = adapter.pending_events()
    assert [e.event_type for e in events] == [
        OrderEventType.BROKER_ACKNOWLEDGED,
        OrderEventType.FILL,
    ]
    fill = events[1]
    # FILL events carry the price in metadata (BrokerOrderEvent has no
    # fill_price field); the mapped ltp -> last must appear verbatim.
    assert fill.metadata["paper_fill_price"] == "100.00"
    assert fill.fill_quantity == Decimal("10")
    assert fill.metadata["fill_source"] == "paper_simulator"


def test_feed_output_drives_limit_reject_on_missing_ask() -> None:
    # bid-only tick: no ask leg -> LIMIT BUY honestly rejects at fill time.
    snapshot = tick_to_reference(_tick(ask=None))
    adapter = _connected_adapter({INSTRUMENT_ID: snapshot})

    response = _run(
        adapter.submit_order(
            _request(
                order_type=OrderType.LIMIT,
                limit_price=Decimal("100.00"),
            )
        )
    )
    assert response.status is BrokerOrderStatus.REJECTED
    events = adapter.pending_events()
    assert len(events) == 1
    assert events[0].event_type is OrderEventType.REJECTED
    assert events[0].fill_quantity == Decimal("0")


def test_feed_map_missing_instrument_rejects() -> None:
    # Order for an instrument absent from the feed-built map -> REJECTED.
    snapshot = tick_to_reference(_tick())
    other_instrument = UUID("99999999-0000-0000-0000-000000000099")
    adapter = _connected_adapter({other_instrument: snapshot})

    response = _run(adapter.submit_order(_request()))
    assert response.status is BrokerOrderStatus.REJECTED
    events = adapter.pending_events()
    assert len(events) == 1
    assert events[0].event_type is OrderEventType.REJECTED
