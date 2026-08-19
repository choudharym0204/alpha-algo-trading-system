"""Historical market-data retrieval: bounded fetch, page-based pagination,
retry, and validation over a provider's historical methods.

The client never invents provider capabilities — it only calls the provider's
``fetch_historical_*`` methods and layers pagination/retry/validation on top.
Pagination is cursor-based (advancing ``start`` past the last returned item) so
each request is bounded by ``page_size`` and the total is bounded by
``max_candles``. Only transient errors (connection/timeout) are retried;
invalid input raises immediately.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Awaitable, Callable, TypeVar

from alpha_algo_contracts import MarketCandle, MarketTick
from alpha_algo_market_data.provider import (
    HistoricalCandlesRequest,
    HistoricalTicksRequest,
    MarketDataProvider,
)

logger = logging.getLogger(__name__)

# Errors considered transient and safe to retry.
_RETRYABLE = (ConnectionError, TimeoutError, OSError)

T = TypeVar("T")


class HistoricalDataError(Exception):
    """Raised when historical retrieval fails after retries."""


async def _retry_awaitable(
    awaitable_factory: Callable[[], Awaitable[T]],
    *,
    attempts: int,
    base_delay: float,
    retryable: tuple[type[Exception], ...] = _RETRYABLE,
) -> T:
    last_error: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await awaitable_factory()
        except retryable as exc:  # noqa: BLE001 - retry loop
            last_error = exc
            if attempt < attempts:
                await asyncio.sleep(base_delay * attempt)
    raise HistoricalDataError(
        f"historical fetch failed after {attempts} attempts"
    ) from last_error


class HistoricalDataClient:
    def __init__(
        self,
        provider: MarketDataProvider,
        *,
        max_candles: int = 10000,
        page_size: int = 1000,
        retry_attempts: int = 3,
        retry_base_delay: float = 0.5,
    ) -> None:
        self._provider = provider
        self._max_candles = max_candles
        self._page_size = page_size
        self._retry_attempts = max(1, retry_attempts)
        self._retry_base_delay = retry_base_delay

    async def fetch_candles(
        self,
        instrument_id,
        exchange: str,
        symbol: str,
        timeframe,
        start: datetime,
        end: datetime,
    ) -> list[MarketCandle]:
        """Fetch candles bounded by ``max_candles``, paging with a time cursor."""
        if end <= start:
            raise ValueError("end must be after start")

        candles: list[MarketCandle] = []
        cursor = start
        while len(candles) < self._max_candles:
            request = HistoricalCandlesRequest(
                instrument_id=instrument_id,
                exchange=exchange,
                symbol=symbol,
                timeframe=timeframe,
                start=cursor,
                end=end,
                limit=self._page_size,
            )
            batch = await _retry_awaitable(
                lambda r=request: self._provider.fetch_historical_candles(r),
                attempts=self._retry_attempts,
                base_delay=self._retry_base_delay,
            )
            if not batch:
                break
            batch = sorted(batch, key=lambda c: c.candle_start)
            candles.extend(batch)
            last_start = batch[-1].candle_start
            if last_start <= cursor:
                break  # no forward progress
            cursor = last_start
        return candles[: self._max_candles]

    async def fetch_ticks(
        self,
        instrument_id,
        exchange: str,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> list[MarketTick]:
        if end <= start:
            raise ValueError("end must be after start")

        ticks: list[MarketTick] = []
        cursor = start
        while len(ticks) < self._max_candles:
            request = HistoricalTicksRequest(
                instrument_id=instrument_id,
                exchange=exchange,
                symbol=symbol,
                start=cursor,
                end=end,
                limit=self._page_size,
            )
            batch = await _retry_awaitable(
                lambda r=request: self._provider.fetch_historical_ticks(r),
                attempts=self._retry_attempts,
                base_delay=self._retry_base_delay,
            )
            if not batch:
                break
            batch = sorted(batch, key=lambda t: t.timestamp)
            ticks.extend(batch)
            last_ts = batch[-1].timestamp
            if last_ts <= cursor:
                break
            cursor = last_ts
        return ticks[: self._max_candles]
