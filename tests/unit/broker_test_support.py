"""Shared helpers for Phase 10 broker-adapter tests (not a test module).

Provides fake credentials (no real secrets), an instrument mapping, a
``BrokerOrderRequest`` factory, and per-broker adapter factories backed by a
deterministic ``FakeTransport`` (no real network).
"""

from __future__ import annotations

from uuid import UUID

from alpha_algo_broker_integration.contracts import (
    BrokerCredentialsRef,
    BrokerName,
    BrokerOrderRequest,
    OrderSide,
    OrderValidity,
    TradingMode,
    UniversalOrderType,
    UniversalProductType,
)
from alpha_algo_broker_integration.mapping import BrokerInstrument, InstrumentMapping
from alpha_algo_broker_integration.transport import FakeTransport, TransportResponse

from angel_one.adapter import AngelOneAdapter
from upstox.adapter import UpstoxAdapter
from zerodha.adapter import ZerodhaAdapter

ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000001")
INSTRUMENT_ID = UUID("00000000-0000-0000-0000-000000000002")
ORDER_ID = UUID("00000000-0000-0000-0000-000000000003")

SYMBOL = "RELIANCE"
EXCHANGE = "NSE"
BROKER_TOKEN = "NSE_EQ|INE002A01018"


def fake_credentials(secret_ref: str) -> dict[str, str]:
    """Returns fake/test credential values only (never real secrets)."""
    return {
        "api_key": "fake_api_key",
        "access_token": "fake_access_token",
        "client_code": "C12345",
        "password": "fake_password",
        "totp": "123456",
    }


def creds_ref(broker: BrokerName) -> BrokerCredentialsRef:
    return BrokerCredentialsRef(
        broker_name=broker,
        account_identifier="acc-1",
        secret_ref="secret-ref-1",
    )


def make_instrument_mapping() -> InstrumentMapping:
    mapping = InstrumentMapping()
    mapping.register(
        BrokerInstrument(
            internal_instrument_id=INSTRUMENT_ID,
            exchange=EXCHANGE,
            symbol=SYMBOL,
            broker_token=BROKER_TOKEN,
            instrument_key=f"{SYMBOL}-EQ",
            lot_size=1,
        )
    )
    return mapping


def make_order_request(**overrides) -> BrokerOrderRequest:
    kwargs = dict(
        broker_account_id=ACCOUNT_ID,
        instrument_id=INSTRUMENT_ID,
        client_order_id="ord-1",
        side=OrderSide.BUY,
        order_type=UniversalOrderType.MARKET,
        product_type=UniversalProductType.CNC,
        quantity=1,
        trading_mode=TradingMode.PAPER,
        exchange=EXCHANGE,
        symbol=SYMBOL,
        validity=OrderValidity.DAY,
    )
    kwargs.update(overrides)
    return BrokerOrderRequest(**kwargs)


def _ok(body: dict | None = None) -> TransportResponse:
    return TransportResponse(status_code=200, body=body or {})


def make_zerodha():
    transport = FakeTransport()
    transport.script("GET", "/user/profile", _ok({"status": "success", "data": {}}))
    transport.script(
        "POST", "/orders", _ok({"status": "success", "data": {"order_id": "kite-1"}})
    )
    adapter = ZerodhaAdapter(
        transport,
        broker_account_id=ACCOUNT_ID,
        credential_resolver=fake_credentials,
        instrument_mapping=make_instrument_mapping(),
        global_halt_active=lambda: False,
        order_id_resolver=lambda broker_id: ORDER_ID,
    )
    return adapter, transport


def make_upstox():
    transport = FakeTransport()
    transport.script("GET", "/user/profile", _ok({"status": "success", "data": {}}))
    transport.script(
        "POST",
        "/order/place",
        _ok({"status": "success", "data": {"order_id": "upstox-1"}}),
    )
    adapter = UpstoxAdapter(
        transport,
        broker_account_id=ACCOUNT_ID,
        credential_resolver=fake_credentials,
        instrument_mapping=make_instrument_mapping(),
        global_halt_active=lambda: False,
        order_id_resolver=lambda broker_id: ORDER_ID,
    )
    return adapter, transport


def make_angel_one():
    transport = FakeTransport()
    transport.script(
        "POST",
        "/rest/auth/angelbroking/user/v1/loginByPassword",
        _ok({"status": True, "data": {"jwtToken": "fake_jwt"}}),
    )
    transport.script(
        "POST",
        "/rest/secure/angelbroking/order/v1/placeOrder",
        _ok({"status": True, "data": {"orderid": "angel-1"}}),
    )
    adapter = AngelOneAdapter(
        transport,
        broker_account_id=ACCOUNT_ID,
        credential_resolver=fake_credentials,
        instrument_mapping=make_instrument_mapping(),
        global_halt_active=lambda: False,
        order_id_resolver=lambda broker_id: ORDER_ID,
    )
    return adapter, transport


def adapters():
    """Yield (broker_name, adapter_factory) for the universal contract suite."""
    return [
        (BrokerName.ZERODHA, make_zerodha),
        (BrokerName.UPSTOX, make_upstox),
        (BrokerName.ANGEL_ONE, make_angel_one),
    ]
