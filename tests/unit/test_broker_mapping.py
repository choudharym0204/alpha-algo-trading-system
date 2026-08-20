"""Phase 10 — broker mapping tables (status / order-type / product / error)."""

from alpha_algo_broker_integration.contracts import BrokerOrderStatus
from alpha_algo_broker_integration.errors import BrokerErrorClass
from alpha_algo_broker_integration.transport import TransportResponse

from angel_one.mapping import (
    ORDER_TYPE_MAP as ANGEL_ORDER,
    PRODUCT_MAP as ANGEL_PRODUCT,
    map_error as angel_error,
    map_status as angel_status,
)
from upstox.mapping import (
    ORDER_TYPE_MAP as UPSTOX_ORDER,
    PRODUCT_MAP as UPSTOX_PRODUCT,
    map_error as upstox_error,
    map_status as upstox_status,
)
from zerodha.mapping import (
    ORDER_TYPE_MAP as ZERODHA_ORDER,
    PRODUCT_MAP as ZERODHA_PRODUCT,
    map_error as zerodha_error,
    map_status as zerodha_status,
)


# ---------------------------------------------------------------- status
def test_zerodha_status_mapping():
    assert zerodha_status("COMPLETE") == BrokerOrderStatus.FILLED
    assert zerodha_status("CANCELLED") == BrokerOrderStatus.CANCELLED
    assert zerodha_status("REJECTED") == BrokerOrderStatus.REJECTED
    assert zerodha_status("TRIGGER PENDING") == BrokerOrderStatus.PENDING
    assert zerodha_status("UNKNOWN_XYZ") == BrokerOrderStatus.UNKNOWN
    # partial fill refinement
    assert (
        zerodha_status("OPEN", filled=30, quantity=100)
        == BrokerOrderStatus.PARTIALLY_FILLED
    )
    assert zerodha_status("OPEN", filled=0, quantity=100) == BrokerOrderStatus.OPEN


def test_upstox_status_mapping():
    assert upstox_status("complete") == BrokerOrderStatus.FILLED
    assert upstox_status("cancelled") == BrokerOrderStatus.CANCELLED
    assert upstox_status("rejected") == BrokerOrderStatus.REJECTED
    assert upstox_status("trigger pending") == BrokerOrderStatus.PENDING
    assert upstox_status("open", filled=10, quantity=50) == BrokerOrderStatus.PARTIALLY_FILLED


def test_angel_status_mapping():
    assert angel_status("complete") == BrokerOrderStatus.FILLED
    assert angel_status("rejected") == BrokerOrderStatus.REJECTED
    assert angel_status("cancelled") == BrokerOrderStatus.CANCELLED
    assert angel_status("trigger pending") == BrokerOrderStatus.PENDING


# ---------------------------------------------------------------- order type
def test_order_type_mapping_is_explicit():
    # STOP never silently downgrades to MARKET.
    assert ZERODHA_ORDER["STOP"] == "SL"
    assert ZERODHA_ORDER["STOP_LIMIT"] == "SL-M"
    assert UPSTOX_ORDER["STOP"] == "SL"
    assert ANGEL_ORDER["STOP"] == "STOPLOSS_MARKET"
    assert ANGEL_ORDER["STOP_LIMIT"] == "STOPLOSS_LIMIT"
    assert "STOP" not in {ZERODHA_ORDER["MARKET"], UPSTOX_ORDER["MARKET"]}


# ---------------------------------------------------------------- product
def test_product_type_mapping():
    assert ZERODHA_PRODUCT["CNC"] == "CNC"
    assert UPSTOX_PRODUCT["CNC"] == "D"
    assert UPSTOX_PRODUCT["MIS"] == "I"
    assert ANGEL_PRODUCT["CNC"] == "DELIVERY"
    assert ANGEL_PRODUCT["MIS"] == "INTRADAY"


# ---------------------------------------------------------------- error
def test_error_normalization_http_status():
    for mapper in (zerodha_error, upstox_error, angel_error):
        assert mapper(TransportResponse(status_code=401)).error_class == BrokerErrorClass.AUTHENTICATION
        assert mapper(TransportResponse(status_code=429)).error_class == BrokerErrorClass.RATE_LIMIT
        assert mapper(TransportResponse(status_code=400)).error_class == BrokerErrorClass.VALIDATION
        assert mapper(TransportResponse(status_code=403)).error_class == BrokerErrorClass.AUTHORIZATION
        assert mapper(TransportResponse(status_code=503)).error_class in {
            BrokerErrorClass.PROVIDER_UNAVAILABLE,
            BrokerErrorClass.UNKNOWN,
        }


def test_angel_error_with_status_false_body():
    resp = TransportResponse(
        status_code=200,
        body={"status": False, "message": "Invalid Token.", "errorcode": "AG8001"},
    )
    err = angel_error(resp)
    assert err.error_class == BrokerErrorClass.AUTHENTICATION


def test_error_preserves_provider_code():
    resp = TransportResponse(
        status_code=400, body={"message": "bad order", "error_type": "InputException"}
    )
    err = zerodha_error(resp)
    assert err.provider_code == "InputException"
