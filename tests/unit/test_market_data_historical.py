from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from alpha_algo_contracts import CandleTimeframe, MarketCandle
from alpha_algo_market_data import FakeMarketDataProvider, HistoricalDataClient, HistoricalDataError

END = datetime(2026, 8, 18, 12, 0, 0, tzinfo=UTC)
START = END - timedelta(hours=1)


def make_candle(candle_start: datetime) -> MarketCandle:
    return MarketCandle(
        instrument_id=uuid4(),
        exchange="NSE",
        symbol="RELIANCE",
        timeframe=CandleTimeframe.ONE_MINUTE,
        candle_start=candle_start,
        open_price=Decimal("100"),
        high_price=Decimal("110"),
        low_price=Decimal("95"),
        close_price=Decimal("105"),
        volume=500,
        source_broker="fake",
        generated_at=candle_start,
    )


def test_historical_normal_fetch() -> None:
    async def main() -> None:
        provider = FakeMarketDataProvider()
        provider.historical_candles = [make_candle(END - timedelta(minutes=30))]
        client = HistoricalDataClient(provider, max_candles=100, page_size=1000)
        candles = await client.fetch_candles(
            uuid4(), "NSE", "RELIANCE", CandleTimeframe.ONE_MINUTE, START, END
        )
        assert len(candles) == 1

    asyncio.run(main())


def test_historical_retries_then_succeeds() -> None:
    async def main() -> None:
        provider = FakeMarketDataProvider()
        calls = {"n": 0}

        async def flaky(request):
            calls["n"] += 1
            if calls["n"] < 3:
                raise ConnectionError("refused")
            return [make_candle(END - timedelta(minutes=30))]

        provider.fetch_historical_candles = flaky
        client = HistoricalDataClient(
            provider, max_candles=1, retry_attempts=3, retry_base_delay=0.01
        )
        candles = await client.fetch_candles(
            uuid4(), "NSE", "RELIANCE", CandleTimeframe.ONE_MINUTE, START, END
        )
        assert len(candles) == 1
        assert calls["n"] == 3

    asyncio.run(main())


def test_historical_raises_after_exhaustion() -> None:
    async def main() -> None:
        provider = FakeMarketDataProvider()

        async def always_fail(request):
            raise ConnectionError("refused")

        provider.fetch_historical_candles = always_fail
        client = HistoricalDataClient(provider, retry_attempts=2, retry_base_delay=0.01)
        with pytest.raises(HistoricalDataError):
            await client.fetch_candles(
                uuid4(), "NSE", "RELIANCE", CandleTimeframe.ONE_MINUTE, START, END
            )

    asyncio.run(main())


def test_historical_paginates_with_cursor() -> None:
    async def main() -> None:
        provider = FakeMarketDataProvider()
        provider.historical_candles = [
            make_candle(END - timedelta(minutes=30)),
            make_candle(END - timedelta(minutes=20)),
            make_candle(END - timedelta(minutes=10)),
        ]
        calls = {"n": 0}
        original = provider.fetch_historical_candles

        async def counting(request):
            calls["n"] += 1
            return await original(request)

        provider.fetch_historical_candles = counting
        client = HistoricalDataClient(provider, max_candles=100, page_size=1)
        candles = await client.fetch_candles(
            uuid4(), "NSE", "RELIANCE", CandleTimeframe.ONE_MINUTE, START, END
        )
        assert len(candles) == 3
        # page_size=1 over 3 distinct candles -> 3 pages + 1 terminal empty page
        assert calls["n"] >= 3

    asyncio.run(main())


def test_historical_bounds_total_candles() -> None:
    async def main() -> None:
        provider = FakeMarketDataProvider()
        provider.historical_candles = [
            make_candle(END - timedelta(minutes=i)) for i in range(5, 0, -1)
        ]
        client = HistoricalDataClient(provider, max_candles=2, page_size=1000)
        candles = await client.fetch_candles(
            uuid4(), "NSE", "RELIANCE", CandleTimeframe.ONE_MINUTE, START, END
        )
        assert len(candles) == 2

    asyncio.run(main())


def test_historical_rejects_invalid_range() -> None:
    async def main() -> None:
        provider = FakeMarketDataProvider()
        client = HistoricalDataClient(provider)
        with pytest.raises(ValueError):
            await client.fetch_candles(
                uuid4(), "NSE", "RELIANCE", CandleTimeframe.ONE_MINUTE, END, END
            )

    asyncio.run(main())
