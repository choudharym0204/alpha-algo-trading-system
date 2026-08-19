from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol
from uuid import UUID


class TradingMode(StrEnum):
    BACKTEST = "BACKTEST"
    PAPER = "PAPER"
    LIVE = "LIVE"


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class BrokerOrderStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class BrokerCapabilities:
    broker_name: str
    supports_market_data: bool
    supports_order_submission: bool
    supports_order_cancel: bool
    supports_positions: bool
    supports_live_trading: bool = False


@dataclass(frozen=True)
class BrokerCredentialsRef:
    broker_name: str
    account_identifier: str
    secret_ref: str


@dataclass(frozen=True)
class BrokerSessionState:
    broker_name: str
    account_identifier: str
    connected: bool
    authenticated: bool
    checked_at: datetime
    expires_at: datetime | None = None


@dataclass(frozen=True)
class BrokerQuote:
    instrument_id: UUID
    exchange: str
    symbol: str
    timestamp: datetime
    ltp: Decimal
    source_broker: str
    received_at: datetime
    volume: int | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None
    bid_quantity: int | None = None
    ask_quantity: int | None = None
    source_sequence: str | None = None


@dataclass(frozen=True)
class BrokerOrderRequest:
    broker_account_id: UUID
    instrument_id: UUID
    trading_mode: TradingMode
    client_order_id: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    risk_approval_id: str
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class BrokerOrderResponse:
    status: BrokerOrderStatus
    client_order_id: str
    broker_order_id: str | None
    accepted_at: datetime
    reason: str | None = None
    raw_payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class BrokerPositionSnapshot:
    broker_account_id: UUID
    instrument_id: UUID
    trading_mode: TradingMode
    quantity: Decimal
    average_price: Decimal | None
    captured_at: datetime
    raw_payload: dict[str, object] = field(default_factory=dict)


class BrokerAdapter(Protocol):
    @property
    def capabilities(self) -> BrokerCapabilities:
        raise NotImplementedError

    async def connect(self, credentials_ref: BrokerCredentialsRef) -> BrokerSessionState:
        raise NotImplementedError

    async def disconnect(self) -> None:
        raise NotImplementedError

    async def get_quote(self, instrument_id: UUID) -> BrokerQuote:
        raise NotImplementedError

    async def submit_order(self, request: BrokerOrderRequest) -> BrokerOrderResponse:
        raise NotImplementedError

    async def cancel_order(self, broker_order_id: str) -> BrokerOrderResponse:
        raise NotImplementedError

    async def get_positions(self) -> list[BrokerPositionSnapshot]:
        raise NotImplementedError

