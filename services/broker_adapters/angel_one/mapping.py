"""Angel One SmartAPI — provider-specific constants + mapping tables.

Provider documentation basis:
  * Angel One SmartAPI — https://smartapi.angelone.in/docs/ (REST + WebSocket).
  * Static-IP requirement for order execution effective 2026-04-01 per Angel One
    (orders & GTT must originate from a registered static IP).

Never contains credential values.
"""

from __future__ import annotations

from alpha_algo_broker_integration.contracts import (
    BrokerCapabilities,
    BrokerName,
    BrokerOrderStatus,
)
from alpha_algo_broker_integration.errors import BrokerError, BrokerErrorClass
from alpha_algo_broker_integration.transport import TransportResponse

ANGEL_BASE_URL = "https://apiconnect.angelone.in"

STATIC_IP_REQUIRED = True
STATIC_IP_NOTE = (
    "Angel One SmartAPI requires a registered static IP for order execution "
    "(place/modify/cancel + GTT) effective 2026-04-01."
)

# ------------------------------------------------------------------ status map
STATUS_MAP: dict[str, BrokerOrderStatus] = {
    "complete": BrokerOrderStatus.FILLED,
    "rejected": BrokerOrderStatus.REJECTED,
    "cancelled": BrokerOrderStatus.CANCELLED,
    "open": BrokerOrderStatus.OPEN,
    "pending": BrokerOrderStatus.PENDING,
    "trigger pending": BrokerOrderStatus.PENDING,
    "amo": BrokerOrderStatus.PENDING,
}


def map_status(status: str | None, *, filled: int = 0, quantity: int = 0) -> BrokerOrderStatus:
    if status is None:
        return BrokerOrderStatus.UNKNOWN
    normalized = STATUS_MAP.get(status.lower(), BrokerOrderStatus.UNKNOWN)
    if normalized == BrokerOrderStatus.OPEN and quantity > 0 and 0 < filled < quantity:
        return BrokerOrderStatus.PARTIALLY_FILLED
    return normalized


# ------------------------------------------------------------------ order type
ORDER_TYPE_MAP: dict[str, str] = {
    "MARKET": "MARKET",
    "LIMIT": "LIMIT",
    "STOP": "STOPLOSS_MARKET",
    "STOP_LIMIT": "STOPLOSS_LIMIT",
}

PRODUCT_MAP: dict[str, str] = {
    "CNC": "DELIVERY",
    "MIS": "INTRADAY",
    "NRML": "CARRYFORWARD",
}

VALIDITY_MAP: dict[str, str] = {
    "DAY": "DAY",
    "IOC": "IOC",
    "GTC": "DAY",  # SmartAPI equity orders are DAY; GTC not universally supported
}

# SmartAPI uses a "variety" field: STOPLOSS orders need variety=STOPLOSS.
def variety_for(order_type: str) -> str:
    return "STOPLOSS" if order_type in ("STOP", "STOP_LIMIT") else "NORMAL"


# ------------------------------------------------------------------ error map
# SmartAPI returns HTTP 200 with {"status": false, "message", "errorcode"} on
# many failures; non-200 also occurs. Classify by errorcode + status flag.
ERROR_CODE_MAP: dict[str, BrokerErrorClass] = {
    "AG8001": BrokerErrorClass.AUTHENTICATION,
    "AG8002": BrokerErrorClass.AUTHENTICATION,
    "AG8003": BrokerErrorClass.AUTHORIZATION,
    "AB1004": BrokerErrorClass.RATE_LIMIT,
    "AB1005": BrokerErrorClass.VALIDATION,
}


def map_error(resp: TransportResponse) -> BrokerError:
    body = resp.body or {}
    status_flag = body.get("status")
    error_code = (body.get("errorcode") or body.get("code") or "").strip()
    message = body.get("message") or resp.text or "provider error"
    code = resp.status_code

    # HTTP 200 with status:false is still a provider error.
    if code == 200 and status_flag is False:
        error_class = ERROR_CODE_MAP.get(
            error_code, _classify_message(message, BrokerErrorClass.UNKNOWN)
        )
    else:
        error_class = ERROR_CODE_MAP.get(error_code, _http_error_class(code))

    return BrokerError(
        error_class=error_class,
        message=message,
        provider_code=error_code or str(code),
        provider_message=message,
    )


def _classify_message(message: str, default: BrokerErrorClass) -> BrokerErrorClass:
    lowered = message.lower()
    if "token" in lowered or "login" in lowered or "session" in lowered:
        return BrokerErrorClass.AUTHENTICATION
    if "rate" in lowered or "limit" in lowered:
        return BrokerErrorClass.RATE_LIMIT
    if "reject" in lowered:
        return BrokerErrorClass.ORDER_REJECTED
    if "invalid" in lowered or "required" in lowered:
        return BrokerErrorClass.VALIDATION
    return default


def _http_error_class(code: int) -> BrokerErrorClass:
    if code == 429:
        return BrokerErrorClass.RATE_LIMIT
    if code == 401:
        return BrokerErrorClass.AUTHENTICATION
    if code == 403:
        return BrokerErrorClass.AUTHORIZATION
    if code in (400, 422):
        return BrokerErrorClass.VALIDATION
    if code == 404:
        return BrokerErrorClass.NOT_FOUND
    if code in (502, 503, 504):
        return BrokerErrorClass.PROVIDER_UNAVAILABLE
    return BrokerErrorClass.UNKNOWN


def build_capabilities() -> BrokerCapabilities:
    return BrokerCapabilities(
        broker_name=BrokerName.ANGEL_ONE,
        supports_order_submission=True,
        supports_modify=True,
        supports_cancel=True,
        supports_order_stream=True,
        supports_trade_stream=True,
        supports_positions=True,
        supports_holdings=True,
        supports_funds=True,
        supports_margin=True,
        supports_market_data=True,
        supports_historical_data=True,
        supports_live_trading=False,
        supported_exchanges=frozenset({"NSE", "BSE", "NFO", "MCX"}),
        supported_order_types=frozenset({"MARKET", "LIMIT", "STOP", "STOP_LIMIT"}),
        supported_products=frozenset({"CNC", "MIS", "NRML"}),
        supported_modes=frozenset({"BACKTEST", "PAPER"}),
        broker_specific_constraints=frozenset({STATIC_IP_NOTE}),
    )
