"""Upstox API v2 — provider-specific constants + mapping tables.

Provider documentation basis:
  * Upstox Developer API v2 — https://upstox.com/developer/api-documentation/
  * WebSocket: portfolio/order update stream (V3) + market feed; V2 WS service
    discontinued 2025-08-22 per Upstox announcements.
  * Sandbox: v2 order APIs support sandbox endpoints.

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

UPSTOX_BASE_URL = "https://api.upstox.com/v2"
UPSTOX_SANDBOX_URL = "https://api.upstox.com/v2/sandbox"

STATIC_IP_REQUIRED = False
STATIC_IP_NOTE = "Upstox does not require a static IP for order placement."

# ------------------------------------------------------------------ status map
STATUS_MAP: dict[str, BrokerOrderStatus] = {
    "open": BrokerOrderStatus.OPEN,
    "complete": BrokerOrderStatus.FILLED,
    "cancelled": BrokerOrderStatus.CANCELLED,
    "rejected": BrokerOrderStatus.REJECTED,
    "pending": BrokerOrderStatus.PENDING,
    "trigger pending": BrokerOrderStatus.PENDING,
    "put order req received": BrokerOrderStatus.PENDING,
    "validation pending": BrokerOrderStatus.PENDING,
    "modify pending": BrokerOrderStatus.PENDING,
    "after market order req received": BrokerOrderStatus.PENDING,
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
    "STOP": "SL",
    "STOP_LIMIT": "SL-M",
}

PRODUCT_MAP: dict[str, str] = {
    "CNC": "D",  # delivery
    "MIS": "I",  # intraday
    # NRML is NOT supported by Upstox and is intentionally absent — it is
    # rejected (UNSUPPORTED) by the adapter rather than silently downgraded.
}

VALIDITY_MAP: dict[str, str] = {
    "DAY": "DAY",
    "IOC": "IOC",
    "GTC": "GTC",
}

# ------------------------------------------------------------------ error map
# Best-effort Upstox errorCode -> class (verify against current docs at use time).
ERROR_CODE_MAP: dict[str, BrokerErrorClass] = {
    "UDAPI100001": BrokerErrorClass.VALIDATION,
    "UDAPI100010": BrokerErrorClass.AUTHENTICATION,
    "UDAPI100011": BrokerErrorClass.AUTHORIZATION,
    "UDAPI100113": BrokerErrorClass.RATE_LIMIT,
    "UDAPI100105": BrokerErrorClass.ORDER_REJECTED,
    "UDAPI100100": BrokerErrorClass.NOT_FOUND,
}


def map_error(resp: TransportResponse) -> BrokerError:
    code = resp.status_code
    body = resp.body or {}
    errors = body.get("errors") or []
    error_code = None
    message = body.get("message") or resp.text or "provider error"
    if isinstance(errors, list) and errors:
        first = errors[0] if isinstance(errors[0], dict) else {}
        error_code = first.get("errorCode")
        if first.get("message"):
            message = first["message"]
    error_class = ERROR_CODE_MAP.get(error_code, _http_error_class(code))
    return BrokerError(
        error_class=error_class,
        message=message,
        provider_code=error_code or str(code),
        provider_message=message,
    )


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
        broker_name=BrokerName.UPSTOX,
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
        supported_exchanges=frozenset({"NSE", "BSE", "NSE_FO", "MCX"}),
        supported_order_types=frozenset({"MARKET", "LIMIT", "STOP", "STOP_LIMIT"}),
        supported_products=frozenset({"CNC", "MIS"}),
        supported_modes=frozenset({"BACKTEST", "PAPER"}),
        broker_specific_constraints=frozenset(
            {
                "Uses instrument_token (e.g. NSE_EQ|ISIN) rather than tradingsymbol.",
                "No NRML product; normalise to delivery (D).",
            }
        ),
    )
