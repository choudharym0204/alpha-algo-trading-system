"""Phase 10 — error normalization + failure-injection + validation tests."""

import asyncio

import pytest

from alpha_algo_broker_integration.contracts import (
    BrokerName,
    UniversalOrderType,
    UniversalProductType,
)
from alpha_algo_broker_integration.errors import BrokerError, BrokerErrorClass
from alpha_algo_broker_integration.mapping import validate_quantity
from alpha_algo_broker_integration.transport import TransportResponse

from broker_test_support import (
    creds_ref,
    make_angel_one,
    make_order_request,
    make_upstox,
    make_zerodha,
)


def run(coro):
    return asyncio.run(coro)


# ------------------------------------------------------- framework validation
def test_validate_quantity_rejects_invalid():
    with pytest.raises(BrokerError) as e:
        validate_quantity(quantity=0, lot_size=1)
    assert e.value.error_class == BrokerErrorClass.VALIDATION

    with pytest.raises(BrokerError):
        validate_quantity(quantity=7, lot_size=5)  # not a lot multiple


def test_validate_quantity_accepts_valid():
    validate_quantity(quantity=10, lot_size=5)  # no raise


def test_instrument_mapping_missing_rejected():
    from alpha_algo_broker_integration.mapping import InstrumentMapping
    from uuid import uuid4

    mapping = InstrumentMapping()
    with pytest.raises(BrokerError) as e:
        mapping.resolve(uuid4(), exchange="NSE", symbol="MISSING")
    assert e.value.error_class == BrokerErrorClass.VALIDATION


# ------------------------------------------------------- unsupported downgrade
def test_unsupported_product_type_is_not_downgraded():
    adapter, _ = make_upstox()  # Upstox has no NRML
    run(adapter.connect(creds_ref(BrokerName.UPSTOX)))
    with pytest.raises(BrokerError) as e:
        run(
            adapter.submit_order(
                make_order_request(product_type=UniversalProductType.NRML)
            )
        )
    assert e.value.error_class == BrokerErrorClass.UNSUPPORTED


# ------------------------------------------------------- submit failure mapping
def test_submit_order_rejection_maps_to_error():
    adapter, transport = make_zerodha()
    transport.script(
        "POST", "/orders", TransportResponse(status_code=400, body={"message": "bad qty", "error_type": "InputException"})
    )
    run(adapter.connect(creds_ref(BrokerName.ZERODHA)))
    with pytest.raises(BrokerError) as e:
        run(adapter.submit_order(make_order_request()))
    assert e.value.error_class == BrokerErrorClass.VALIDATION


def test_submit_rate_limit_maps_to_rate_limit():
    adapter, transport = make_zerodha()
    transport.script("POST", "/orders", TransportResponse(status_code=429, body={}))
    run(adapter.connect(creds_ref(BrokerName.ZERODHA)))
    with pytest.raises(BrokerError) as e:
        run(adapter.submit_order(make_order_request()))
    assert e.value.error_class == BrokerErrorClass.RATE_LIMIT


def test_provider_outage_maps_to_unavailable():
    adapter, transport = make_zerodha()
    transport.script("POST", "/orders", TransportResponse(status_code=503, body={}))
    run(adapter.connect(creds_ref(BrokerName.ZERODHA)))
    with pytest.raises(BrokerError) as e:
        run(adapter.submit_order(make_order_request()))
    assert e.value.error_class in {
        BrokerErrorClass.PROVIDER_UNAVAILABLE,
        BrokerErrorClass.UNKNOWN,
    }


# ------------------------------------------------------- auth failure
def test_invalid_credentials_at_connect():
    adapter, transport = make_zerodha()
    transport.script("GET", "/user/profile", TransportResponse(status_code=401, body={}))
    with pytest.raises(BrokerError) as e:
        run(adapter.connect(creds_ref(BrokerName.ZERODHA)))
    assert e.value.error_class == BrokerErrorClass.AUTHENTICATION


def test_angel_invalid_credentials():
    adapter, transport = make_angel_one()
    transport.script(
        "POST",
        "/rest/auth/angelbroking/user/v1/loginByPassword",
        TransportResponse(status_code=200, body={"status": False, "message": "Invalid token", "errorcode": "AG8001"}),
    )
    with pytest.raises(BrokerError) as e:
        run(adapter.connect(creds_ref(BrokerName.ANGEL_ONE)))
    assert e.value.error_class == BrokerErrorClass.AUTHENTICATION


# ------------------------------------------------------- malformed response
def test_malformed_response_does_not_crash():
    adapter, transport = make_zerodha()
    # non-JSON, empty response on a read endpoint
    transport.script("GET", "/orders", TransportResponse(status_code=200, body=None, text="<html>oops</html>"))
    run(adapter.connect(creds_ref(BrokerName.ZERODHA)))
    orders = run(adapter.get_orders())
    assert orders == []  # no crash, empty normalized result


# ------------------------------------------------------- retryability
def test_retryability_classification():
    from alpha_algo_broker_integration.errors import is_safe_to_retry

    assert is_safe_to_retry(BrokerErrorClass.RATE_LIMIT) is True
    assert is_safe_to_retry(BrokerErrorClass.TIMEOUT) is True
    assert is_safe_to_retry(BrokerErrorClass.NETWORK) is True
    assert is_safe_to_retry(BrokerErrorClass.AUTHENTICATION) is False
    assert is_safe_to_retry(BrokerErrorClass.VALIDATION) is False
    assert is_safe_to_retry(BrokerErrorClass.ORDER_REJECTED) is False
