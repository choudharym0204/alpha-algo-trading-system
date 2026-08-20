"""Phase 10 — universal broker contract suite (applies to all adapters)."""

import asyncio

import pytest

from alpha_algo_broker_integration.contracts import (
    BrokerCapabilities,
    BrokerName,
    ConnectionState,
    TradingMode,
)
from alpha_algo_broker_integration.errors import BrokerError, BrokerErrorClass

from broker_test_support import adapters, creds_ref, make_order_request


def run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize("broker,factory", adapters())
def test_connect_and_health(broker, factory):
    adapter, _ = factory()
    state = run(adapter.connect(creds_ref(broker)))
    assert state.connected is True
    assert state.authenticated is True
    assert adapter.connection_state == ConnectionState.CONNECTED
    assert run(adapter.health()) is True


@pytest.mark.parametrize("broker,factory", adapters())
def test_disconnect(broker, factory):
    adapter, _ = factory()
    run(adapter.connect(creds_ref(broker)))
    run(adapter.disconnect())
    assert adapter.connection_state == ConnectionState.DISCONNECTED
    assert run(adapter.health()) is False


@pytest.mark.parametrize("broker,factory", adapters())
def test_capabilities_are_truthful(broker, factory):
    adapter, _ = factory()
    caps = adapter.capabilities
    assert caps.broker_name == broker
    assert caps.supports_order_submission is True
    assert caps.supports_live_trading is False
    assert "MARKET" in caps.supported_order_types
    assert "PAPER" in caps.supported_modes


@pytest.mark.parametrize("broker,factory", adapters())
def test_submit_order_acknowledged(broker, factory):
    adapter, _ = factory()
    run(adapter.connect(creds_ref(broker)))
    resp = run(adapter.submit_order(make_order_request()))
    assert resp.status.value == "BROKER_ACKNOWLEDGED"
    assert resp.broker_order_id is not None


@pytest.mark.parametrize("broker,factory", adapters())
def test_submit_requires_connection(broker, factory):
    adapter, _ = factory()
    with pytest.raises(BrokerError) as exc:
        run(adapter.submit_order(make_order_request()))
    assert exc.value.error_class == BrokerErrorClass.NETWORK


@pytest.mark.parametrize("broker,factory", adapters())
def test_live_mode_blocked(broker, factory):
    adapter, _ = factory()
    run(adapter.connect(creds_ref(broker)))
    with pytest.raises(BrokerError) as exc:
        run(adapter.submit_order(make_order_request(trading_mode=TradingMode.LIVE)))
    assert exc.value.error_class == BrokerErrorClass.UNSUPPORTED


@pytest.mark.parametrize("broker,factory", adapters())
def test_global_halt_blocks_submission(broker, factory):
    adapter, _ = factory()
    run(adapter.connect(creds_ref(broker)))
    adapter._global_halt_active = lambda: True  # halt ACTIVE
    with pytest.raises(BrokerError) as exc:
        run(adapter.submit_order(make_order_request()))
    assert exc.value.error_class == BrokerErrorClass.ORDER_REJECTED


@pytest.mark.parametrize("broker,factory", adapters())
def test_order_payload_carries_client_order_id(broker, factory):
    adapter, transport = factory()
    run(adapter.connect(creds_ref(broker)))
    run(adapter.submit_order(make_order_request(client_order_id="ord-client-1")))
    submitted = transport.calls[-1][3]  # json body of the submit call
    assert submitted is not None
    if broker in (BrokerName.ZERODHA, BrokerName.UPSTOX):
        # Kite + Upstox expose a `tag` field for the client order id.
        assert submitted.get("tag") == "ord-client-1"
    else:
        # Angel One has no client-tag field; the order identity is kept internal.
        assert submitted.get("quantity") == "1"
