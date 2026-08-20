"""Phase 10 — adapter parsing / normalization tests (per broker)."""

import asyncio
from decimal import Decimal

from alpha_algo_broker_integration.contracts import BrokerOrderStatus
from alpha_algo_broker_integration.events import BrokerEventType
from alpha_algo_broker_integration.transport import TransportResponse

from broker_test_support import (
    ACCOUNT_ID,
    ORDER_ID,
    SYMBOL,
    creds_ref,
    make_angel_one,
    make_upstox,
    make_zerodha,
)
from alpha_algo_broker_integration.contracts import BrokerName


def run(coro):
    return asyncio.run(coro)


def _ok(body):
    return TransportResponse(status_code=200, body=body)


# ------------------------------------------------------------------- Zerodha
def test_zerodha_cancel_order():
    adapter, transport = make_zerodha()
    transport.script("DELETE", "/orders/kite-1", _ok({"data": {"order_id": "kite-1"}}))
    run(adapter.connect(creds_ref(BrokerName.ZERODHA)))
    resp = run(adapter.cancel_order("kite-1"))
    assert resp.status == BrokerOrderStatus.CANCELLED
    assert resp.broker_order_id == "kite-1"


def test_zerodha_get_orders_normalizes_status():
    adapter, transport = make_zerodha()
    transport.script(
        "GET",
        "/orders",
        _ok(
            {
                "data": [
                    {"order_id": "kite-1", "status": "COMPLETE", "filled_quantity": 10, "quantity": 10},
                    {"order_id": "kite-2", "status": "OPEN", "filled_quantity": 4, "quantity": 10},
                    {"order_id": "kite-3", "status": "REJECTED", "filled_quantity": 0, "quantity": 10},
                ]
            }
        ),
    )
    run(adapter.connect(creds_ref(BrokerName.ZERODHA)))
    orders = run(adapter.get_orders())
    statuses = {o.broker_order_id: o.status for o in orders}
    assert statuses["kite-1"] == BrokerOrderStatus.FILLED
    assert statuses["kite-2"] == BrokerOrderStatus.PARTIALLY_FILLED
    assert statuses["kite-3"] == BrokerOrderStatus.REJECTED


def test_zerodha_get_positions():
    adapter, transport = make_zerodha()
    transport.script(
        "GET",
        "/portfolio/positions",
        _ok({"data": {"net": [{"tradingsymbol": SYMBOL, "exchange": "NSE", "quantity": 5, "average_price": 100.0}]}}),
    )
    run(adapter.connect(creds_ref(BrokerName.ZERODHA)))
    positions = run(adapter.get_positions())
    assert len(positions) == 1
    assert positions[0].quantity == Decimal("5")


def test_zerodha_parse_event_fill():
    adapter, _ = make_zerodha()
    event = adapter.parse_event(
        {"order_id": "kite-1", "status": "COMPLETE", "filled_quantity": 10, "quantity": 10}
    )
    assert event.event_type == BrokerEventType.FILL
    assert event.broker_order_id == "kite-1"
    assert event.order_id == ORDER_ID  # resolved via injected resolver


# ------------------------------------------------------------------- Upstox
def test_upstox_cancel_order():
    adapter, transport = make_upstox()
    transport.script(
        "DELETE", "/order/cancel", _ok({"data": {"order_id": "upstox-1"}})
    )
    run(adapter.connect(creds_ref(BrokerName.UPSTOX)))
    resp = run(adapter.cancel_order("upstox-1"))
    assert resp.status == BrokerOrderStatus.CANCELLED


def test_upstox_get_orders_normalizes_status():
    adapter, transport = make_upstox()
    transport.script(
        "GET",
        "/order/retrieve-all",
        _ok(
            {
                "data": [
                    {"order_id": "u1", "status": "complete", "filled_quantity": 10, "quantity": 10},
                    {"order_id": "u2", "status": "open", "filled_quantity": 0, "quantity": 10},
                ]
            }
        ),
    )
    run(adapter.connect(creds_ref(BrokerName.UPSTOX)))
    orders = run(adapter.get_orders())
    statuses = {o.broker_order_id: o.status for o in orders}
    assert statuses["u1"] == BrokerOrderStatus.FILLED
    assert statuses["u2"] == BrokerOrderStatus.OPEN


def test_upstox_parse_event_partial_fill():
    adapter, _ = make_upstox()
    event = adapter.parse_event(
        {"order_id": "u1", "status": "open", "filled_quantity": 3, "quantity": 10}
    )
    assert event.event_type == BrokerEventType.PARTIAL_FILL
    assert event.fill_quantity == Decimal("3")


# ------------------------------------------------------------------- Angel One
def test_angel_cancel_order():
    adapter, transport = make_angel_one()
    transport.script(
        "POST",
        "/rest/secure/angelbroking/order/v1/cancelOrder",
        _ok({"status": True, "data": {"orderid": "angel-1"}}),
    )
    run(adapter.connect(creds_ref(BrokerName.ANGEL_ONE)))
    resp = run(adapter.cancel_order("angel-1"))
    assert resp.status == BrokerOrderStatus.CANCELLED


def test_angel_get_orders_normalizes_status():
    adapter, transport = make_angel_one()
    transport.script(
        "GET",
        "/rest/secure/angelbroking/order/v1/getOrderBook",
        _ok(
            {
                "data": [
                    {"orderid": "a1", "orderstatus": "complete", "filledquantity": 10, "quantity": 10},
                    {"orderid": "a2", "orderstatus": "rejected", "filledquantity": 0, "quantity": 10},
                ]
            }
        ),
    )
    run(adapter.connect(creds_ref(BrokerName.ANGEL_ONE)))
    orders = run(adapter.get_orders())
    statuses = {o.broker_order_id: o.status for o in orders}
    assert statuses["a1"] == BrokerOrderStatus.FILLED
    assert statuses["a2"] == BrokerOrderStatus.REJECTED


def test_angel_parse_event_rejected():
    adapter, _ = make_angel_one()
    event = adapter.parse_event({"orderid": "a2", "orderstatus": "rejected"})
    assert event.event_type == BrokerEventType.REJECTED


# --------------------------------------------------------------- common: funds
def test_all_brokers_get_funds():
    for name, factory in ((BrokerName.ZERODHA, make_zerodha), (BrokerName.UPSTOX, make_upstox), (BrokerName.ANGEL_ONE, make_angel_one)):
        adapter, transport = factory()
        if name == BrokerName.ZERODHA:
            transport.script("GET", "/user/margins", _ok({"data": {"equity": {"available": {"cash": "1000"}}}}))
        elif name == BrokerName.UPSTOX:
            transport.script("GET", "/user/get-funds-and-margin", _ok({"data": {"equity": {"available_margin": "500"}}}))
        else:
            transport.script("GET", "/rest/secure/angelbroking/user/v1/getRMS", _ok({"data": {"availablecash": "700"}}))
        run(adapter.connect(creds_ref(name)))
        funds = run(adapter.get_funds())
        assert funds.broker_account_id == ACCOUNT_ID
