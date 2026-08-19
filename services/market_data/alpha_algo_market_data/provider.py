"""Market-data provider abstraction.

Defines the async ``MarketDataProvider`` protocol that all providers must
implement, plus the canonical raw-event envelope and connection/historical
types. Provider-specific logic (vendor SDKs) stays isolated behind this
interface; the market-data engine consumes ``RawMarketEvent`` and never talks
to a vendor directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Awaitable, Callable, Protocol
from uuid import UUID

from alpha_algo_contracts import CandleTimeframe, MarketCandle, MarketTick


class EventKind(StrEnum):
    TICK = "tick"
    CANDLE = "candle"


class ConnectionState(StrEnum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"
    CLOSED = "closed"


@dataclass(frozen=True)
class ProviderHealth:
    provider_name: str
    state: ConnectionState
    authenticated: bool
    last_heartbeat_at: datetime | None = None
    details: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RawMarketEvent:
    """A provider-agnostic raw event handed from an adapter to the engine."""

    provider: str
    kind: EventKind
    payload: dict[str, Any]
    received_at: datetime


@dataclass(frozen=True)
class HistoricalCandlesRequest:
    instrument_id: UUID
    exchange: str
    symbol: str
    timeframe: CandleTimeframe
    start: datetime
    end: datetime
    limit: int = 10000


@dataclass(frozen=True)
class HistoricalTicksRequest:
    instrument_id: UUID
    exchange: str
    symbol: str
    start: datetime
    end: datetime
    limit: int = 10000


EventHandler = Callable[[RawMarketEvent], Awaitable[None]]


class MarketDataProvider(Protocol):
    @property
    def provider_name(self) -> str:
        raise NotImplementedError

    async def connect(self) -> None:
        raise NotImplementedError

    async def disconnect(self) -> None:
        raise NotImplementedError

    async def health(self) -> ProviderHealth:
        raise NotImplementedError

    async def subscribe(self, symbols: list[str]) -> None:
        raise NotImplementedError

    async def unsubscribe(self, symbols: list[str]) -> None:
        raise NotImplementedError

    def set_event_handler(self, handler: EventHandler) -> None:
        raise NotImplementedError

    async def fetch_historical_candles(
        self, request: HistoricalCandlesRequest
    ) -> list[MarketCandle]:
        raise NotImplementedError

    async def fetch_historical_ticks(
        self, request: HistoricalTicksRequest
    ) -> list[MarketTick]:
        raise NotImplementedError
