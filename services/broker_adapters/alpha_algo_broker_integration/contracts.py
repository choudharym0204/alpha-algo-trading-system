"""Universal broker contract (Phase 10).

Provider-neutral types the whole system speaks. Concrete broker adapters are
the *translation and isolation boundary*: they map provider-specific concepts
into these types and never let provider-specific fields leak upward into
Strategy / Signal / Risk / OMS / Execution Core.

Nothing in this module contains, prints, or persists credential *values*.
Credentials are represented only as opaque ``secret_ref`` strings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol
from uuid import UUID


# --------------------------------------------------------------------------- enums
class BrokerName(StrEnum):
    ZERODHA = "ZERODHA"
    UPSTOX = "UPSTOX"
    ANGEL_ONE = "ANGEL_ONE"


class ConnectionState(StrEnum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    DEGRADED = "DEGRADED"
    RECONNECTING = "RECONNECTING"


class TradingMode(StrEnum):
    BACKTEST = "BACKTEST"
    PAPER = "PAPER"
    LIVE = "LIVE"


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class UniversalOrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class UniversalProductType(StrEnum):
    CNC = "CNC"
    MIS = "MIS"
    NRML = "NRML"


class BrokerOrderStatus(StrEnum):
    """Normalized execution/order status (broker-agnostic)."""

    SUBMISSION_REQUESTED = "SUBMISSION_REQUESTED"
    BROKER_ACKNOWLEDGED = "BROKER_ACKNOWLEDGED"
    OPEN = "OPEN"
    PENDING = "PENDING"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


class OrderValidity(StrEnum):
    DAY = "DAY"
    IOC = "IOC"
    GTC = "GTC"


# ------------------------------------------------------------------- capabilities
@dataclass(frozen=True)
class BrokerCapabilities:
    """Capability descriptor every adapter exposes (never guessed at runtime)."""

    broker_name: BrokerName
    supports_order_submission: bool = True
    supports_modify: bool = True
    supports_cancel: bool = True
    supports_order_stream: bool = True
    supports_trade_stream: bool = True
    supports_positions: bool = True
    supports_holdings: bool = True
    supports_funds: bool = True
    supports_margin: bool = True
    supports_market_data: bool = True
    supports_historical_data: bool = True
    supports_live_trading: bool = False
    supported_exchanges: frozenset[str] = frozenset({"NSE", "BSE"})
    supported_order_types: frozenset[str] = frozenset(
        {"MARKET", "LIMIT", "STOP", "STOP_LIMIT"}
    )
    supported_products: frozenset[str] = frozenset({"CNC", "MIS", "NRML"})
    supported_modes: frozenset[str] = frozenset({"BACKTEST", "PAPER"})
    broker_specific_constraints: frozenset[str] = frozenset()


# -------------------------------------------------------------- config + creds
@dataclass(frozen=True)
class BrokerCredentialsRef:
    """An *opaque reference* to credentials — never the credential values."""

    broker_name: BrokerName
    account_identifier: str
    secret_ref: str


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_backoff_seconds: float = 1.0
    max_backoff_seconds: float = 30.0
    jitter: bool = True


@dataclass(frozen=True)
class BrokerConnectionConfig:
    broker: BrokerName
    account_reference: str
    credential_reference: str
    environment: str = "PAPER"  # PAPER | SANDBOX | LIVE (LIVE must stay disabled)
    api_endpoint: str = ""
    websocket_endpoint: str = ""
    timeout_seconds: float = 10.0
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    static_ip_required: bool = False
    static_ip_requirement_note: str = ""
    provider_options: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class BrokerSessionState:
    broker_name: BrokerName
    account_identifier: str
    connected: bool
    authenticated: bool
    checked_at: datetime
    expires_at: datetime | None = None
    state: ConnectionState = ConnectionState.DISCONNECTED


# ----------------------------------------------------------------------- orders
@dataclass(frozen=True)
class BrokerOrderRequest:
    """Universal order request (provider-neutral)."""

    broker_account_id: UUID
    instrument_id: UUID
    client_order_id: str
    side: OrderSide
    order_type: UniversalOrderType
    product_type: UniversalProductType
    quantity: int
    trading_mode: TradingMode
    exchange: str
    symbol: str
    validity: OrderValidity = OrderValidity.DAY
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    risk_approval_id: str = ""
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class BrokerOrderResponse:
    """Normalized broker order outcome (no raw JSON as primary contract)."""

    status: BrokerOrderStatus
    client_order_id: str
    broker_order_id: str | None
    message: str | None = None
    error_code: str | None = None
    timestamp: datetime | None = None
    correlation_id: str | None = None
    filled_quantity: Decimal = Decimal("0")
    average_price: Decimal | None = None
    raw_reference: str | None = None  # opaque audit ref, no secrets


# -------------------------------------------------------------------- account
@dataclass(frozen=True)
class BrokerPositionSnapshot:
    broker_account_id: UUID
    instrument_id: UUID
    trading_mode: TradingMode
    quantity: Decimal
    average_price: Decimal | None
    exchange: str = ""
    symbol: str = ""
    captured_at: datetime | None = None


@dataclass(frozen=True)
class BrokerHoldingSnapshot:
    broker_account_id: UUID
    instrument_id: UUID
    quantity: Decimal
    average_price: Decimal | None
    exchange: str = ""
    symbol: str = ""
    captured_at: datetime | None = None


@dataclass(frozen=True)
class BrokerFundsSnapshot:
    broker_account_id: UUID
    available_margin: Decimal | None = None
    used_margin: Decimal | None = None
    available_cash: Decimal | None = None
    currency: str = "INR"
    captured_at: datetime | None = None


# ------------------------------------------------------------------ the contract
class BrokerAdapter(Protocol):
    """Universal async broker contract (Phase 10)."""

    @property
    def capabilities(self) -> BrokerCapabilities: ...

    # authentication
    async def authenticate(self, creds: BrokerCredentialsRef) -> BrokerSessionState: ...

    async def validate_session(self) -> BrokerSessionState: ...

    async def logout(self) -> None: ...

    # connectivity
    async def connect(self, creds: BrokerCredentialsRef) -> BrokerSessionState: ...

    async def disconnect(self) -> None: ...

    async def health(self) -> bool: ...

    async def reconnect(self) -> BrokerSessionState: ...

    @property
    def connection_state(self) -> ConnectionState: ...

    # orders
    async def submit_order(self, request: BrokerOrderRequest) -> BrokerOrderResponse: ...

    async def modify_order(
        self, request: BrokerOrderRequest, broker_order_id: str
    ) -> BrokerOrderResponse: ...

    async def cancel_order(self, broker_order_id: str) -> BrokerOrderResponse: ...

    async def get_order(self, broker_order_id: str) -> BrokerOrderResponse: ...

    async def get_orders(self) -> list[BrokerOrderResponse]: ...

    async def get_trades(self) -> list[BrokerOrderResponse]: ...

    # account
    async def get_positions(self) -> list[BrokerPositionSnapshot]: ...

    async def get_holdings(self) -> list[BrokerHoldingSnapshot]: ...

    async def get_funds(self) -> BrokerFundsSnapshot: ...
