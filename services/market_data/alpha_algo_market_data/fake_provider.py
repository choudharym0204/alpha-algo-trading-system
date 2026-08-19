"""Reference in-process market-data provider (test double and example).

Implements the full ``MarketDataProvider`` protocol without any network I/O, so
the pipeline can be exercised deterministically. Real providers follow the same
contract and read credentials from the environment (never hardcoded).
"""

from __future__ import annotations

from alpha_algo_contracts import MarketCandle, MarketTick
from alpha_algo_market_data.provider import (
    ConnectionState,
    EventHandler,
    HistoricalCandlesRequest,
    HistoricalTicksRequest,
    ProviderHealth,
    RawMarketEvent,
)


class ProviderAuthenticationError(Exception):
    """Raised by providers when authentication fails."""


class FakeMarketDataProvider:
    def __init__(self, provider_name: str = "fake") -> None:
        self._name = provider_name
        self._connected = False
        self._authenticated = False
        self._handler: EventHandler | None = None
        self._subscriptions: set[str] = set()
        self.historical_candles: list[MarketCandle] = []
        self.historical_ticks: list[MarketTick] = []
        self.connect_calls = 0
        self.fail_connect = False
        self.fail_authenticate = False

    @property
    def provider_name(self) -> str:
        return self._name

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def subscriptions(self) -> set[str]:
        return set(self._subscriptions)

    async def connect(self) -> None:
        self.connect_calls += 1
        if self.fail_connect:
            raise ConnectionError("connection refused")
        self._connected = True
        if self.fail_authenticate:
            self._authenticated = False
            raise ProviderAuthenticationError("authentication failed")
        self._authenticated = True

    async def disconnect(self) -> None:
        self._connected = False
        self._authenticated = False

    async def health(self) -> ProviderHealth:
        state = (
            ConnectionState.CONNECTED
            if self._connected
            else ConnectionState.DISCONNECTED
        )
        return ProviderHealth(
            provider_name=self._name,
            state=state,
            authenticated=self._authenticated,
        )

    async def subscribe(self, symbols: list[str]) -> None:
        self._subscriptions.update(symbols)

    async def unsubscribe(self, symbols: list[str]) -> None:
        self._subscriptions.difference_update(symbols)

    def set_event_handler(self, handler: EventHandler) -> None:
        self._handler = handler

    async def emit(self, event: RawMarketEvent) -> None:
        if self._handler is not None:
            await self._handler(event)

    async def fetch_historical_candles(
        self, request: HistoricalCandlesRequest
    ) -> list[MarketCandle]:
        # Keyset pagination: ``start`` is an exclusive cursor; ``end`` inclusive.
        matching = [
            c
            for c in self.historical_candles
            if request.start < c.candle_start <= request.end
        ]
        return sorted(matching, key=lambda c: c.candle_start)[: request.limit]

    async def fetch_historical_ticks(
        self, request: HistoricalTicksRequest
    ) -> list[MarketTick]:
        matching = [
            t for t in self.historical_ticks if request.start < t.timestamp <= request.end
        ]
        return sorted(matching, key=lambda t: t.timestamp)[: request.limit]
