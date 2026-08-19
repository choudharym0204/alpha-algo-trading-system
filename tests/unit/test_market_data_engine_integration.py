from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

from alpha_algo_market_data import (
    EventKind,
    FakeMarketDataProvider,
    MarketDataEngine,
    MarketDataRepository,
    RawMarketEvent,
)


def make_tick_event(source_sequence: str, timestamp: datetime) -> RawMarketEvent:
    return RawMarketEvent(
        provider="fake",
        kind=EventKind.TICK,
        payload={
            "instrument_id": uuid4(),
            "exchange": "NSE",
            "symbol": "RELIANCE",
            "timestamp": timestamp,
            "ltp": "2450.25",
            "source_broker": "fake",
            "source_sequence": source_sequence,
        },
        received_at=timestamp,
    )


def test_provider_to_engine_to_database_pipeline() -> None:
    """End-to-end: provider → adapter → normalized tick → validation → safety → engine → db."""
    async def main() -> None:
        repository = MagicMock(spec=MarketDataRepository)
        engine = MarketDataEngine(
            repository=repository,
            clock=lambda: datetime.now(UTC),
            max_age=timedelta(seconds=5),
        )
        accepted: list = []
        engine.add_tick_consumer(accepted.append)

        provider = FakeMarketDataProvider()
        provider.set_event_handler(engine.enqueue)

        task = asyncio.create_task(engine.run())
        await provider.connect()
        assert provider.is_connected is True

        await provider.emit(
            make_tick_event("seq-1", datetime.now(UTC) - timedelta(seconds=1))
        )
        for _ in range(50):
            if accepted:
                break
            await asyncio.sleep(0.02)

        await engine.stop()
        await task

        assert len(accepted) == 1
        repository.persist_tick.assert_called_once()
        assert engine.metrics.persisted_ticks == 1

    asyncio.run(main())


def test_provider_streams_multiple_ticks_and_dedupes() -> None:
    async def main() -> None:
        engine = MarketDataEngine(clock=lambda: datetime.now(UTC), max_age=timedelta(seconds=5))
        accepted: list = []
        engine.add_tick_consumer(accepted.append)

        provider = FakeMarketDataProvider()
        provider.set_event_handler(engine.enqueue)

        task = asyncio.create_task(engine.run())
        now = datetime.now(UTC) - timedelta(seconds=1)
        # emit a duplicate (same source_sequence) and two distinct ticks
        await provider.emit(make_tick_event("seq-1", now))
        await provider.emit(make_tick_event("seq-1", now))  # duplicate
        await provider.emit(make_tick_event("seq-2", now))

        for _ in range(50):
            if len(accepted) >= 2:
                break
            await asyncio.sleep(0.02)

        await engine.stop()
        await task

        assert len(accepted) == 2
        assert engine.metrics.ticks_received == 3
        assert engine.metrics.duplicates == 1

    asyncio.run(main())
