"""Zerodha Kite Connect v3 — provider-specific constants + mapping tables.

Provider documentation basis:
  * Kite Connect 3 API docs — https://kite.trade/docs/connect/v3/
  * Static-IP requirement (order placement) effective 2025-04-01 per Zerodha FAQ.

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

KITE_BASE_URL = "https://api.kite.trade"

# Order execution from Kite API requires a registered static IP (since 2025-04-01).
STATIC_IP_REQUIRED = True
STATIC_IP_NOTE = (
    "Kite Connect requires a registered static IP for order placement "
    "(effective 2025-04-01). Data endpoints (order book, positions, etc.) "
    "remain accessible without one."
)

# ------------------------------------------------------------------ status map
STATUS_MAP: dict[str, BrokerOrderStatus] = {
    "OPEN": BrokerOrderStatus.OPEN,
    "PENDING": BrokerOrderStatus.PENDING,
    "COMPLETE": BrokerOrderStatus.FILLED,
    "CANCELLED": BrokerOrderStatus.CANCELLED,
    "CANCEL PENDING": BrokerOrderStatus.CANCELLED,
    "REJECTED": BrokerOrderStatus.REJECTED,
    "TRIGGER PENDING": BrokerOrderStatus.PENDING,
    "AMO REQ RECEIVED": BrokerOrderStatus.PENDING,
    "PUT ORDER REQ RECEIVED": BrokerOrderStatus.PENDING,
}


def map_status(status: str | None, *, filled: int = 0, quantity: int = 0) -> BrokerOrderStatus:
    if status is None:
        return BrokerOrderStatus.UNKNOWN
    normalized = STATUS_MAP.get(status.upper(), BrokerOrderStatus.UNKNOWN)
    if normalized == BrokerOrderStatus.OPEN and quantity > 0 and 0 < filled < quantity:
        return BrokerOrderStatus.PARTIALLY_FILLED
    return normalized


# ------------------------------------------------------------------ order type
ORDER_TYPE_MAP: dict[str, str] = {
    "MARKET": "MARKET",
    "LIMIT": "LIMIT",
    "STOP": "SL",       # stop-loss market
    "STOP_LIMIT": "SL-M",  # stop-loss limit
}

PRODUCT_MAP: dict[str, str] = {
    "CNC": "CNC",
    "MIS": "MIS",
    "NRML": "NRML",
}

VALIDITY_MAP: dict[str, str] = {
    "DAY": "DAY",
    "IOC": "IOC",
    "GTC": "GTC",
}

# ------------------------------------------------------------------ error map
ERROR_TYPE_MAP: dict[str, BrokerErrorClass] = {
    "InputException": BrokerErrorClass.VALIDATION,
    "DataException": BrokerErrorClass.VALIDATION,
    "TokenException": BrokerErrorClass.AUTHENTICATION,
    "PermissionException": BrokerErrorClass.AUTHORIZATION,
    "OrderException": BrokerErrorClass.ORDER_REJECTED,
    "RateLimitException": BrokerErrorClass.RATE_LIMIT,
    "NetworkException": BrokerErrorClass.NETWORK,
    "GeneralException": BrokerErrorClass.UNKNOWN,
}


def map_error(resp: TransportResponse) -> BrokerError:
    code = resp.status_code
    body = resp.body or {}
    error_type = (body.get("error_type") or "").strip()
    message = body.get("message") or resp.text or "provider error"
    error_class = ERROR_TYPE_MAP.get(error_type, _http_error_class(code))
    return BrokerError(
        error_class=error_class,
        message=message,
        provider_code=error_type or str(code),
        provider_message=message,
    )


def _http_error_class(code: int) -> BrokerErrorClass:
    if code == 429:
        return BrokerErrorClass.RATE_LIMIT
    if code in (401,):
        return BrokerErrorClass.AUTHENTICATION
    if code in (403,):
        return BrokerErrorClass.AUTHORIZATION
    if code in (400, 422):
        return BrokerErrorClass.VALIDATION
    if code in (502, 503, 504):
        return BrokerErrorClass.PROVIDER_UNAVAILABLE
    return BrokerErrorClass.UNKNOWN


# ---------------------------------------------------------------- capabilities
def build_capabilities() -> BrokerCapabilities:
    return BrokerCapabilities(
        broker_name=BrokerName.ZERODHA,
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
