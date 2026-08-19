from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from alpha_algo_market_data import BoundedQueue, EventKind, MarketDataEngine, RawMarketEvent


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


def test_bounded_queue_accepts_up_to_maxsize() -> None:
    q: BoundedQueue[int] = BoundedQueue(maxsize=3)
    assert q.put_nowait(1) is True
    assert q.put_nowait(2) is True
    assert q.put_nowait(3) is True
    assert q.full() is True


def test_bounded_queue_drop_newest() -> None:
    q: BoundedQueue[int] = BoundedQueue(maxsize=2, drop_policy="drop_newest")
    assert q.put_nowait(1) is True
    assert q.put_nowait(2) is True
    assert q.put_nowait(3) is False  # dropped
    assert q.dropped_count == 1
    assert q.qsize == 2


def test_bounded_queue_drop_oldest() -> None:
    q: BoundedQueue[int] = BoundedQueue(maxsize=2, drop_policy="drop_oldest")
    assert q.put_nowait(1) is True
    assert q.put_nowait(2) is True
    assert q.put_nowait(3) is True  # oldest dropped, 3 accepted
    assert q.dropped_count == 1
    assert q.qsize == 2


def test_bounded_queue_requires_positive_maxsize() -> None:
    import pytest

    with pytest.raises(ValueError):
        BoundedQueue(maxsize=0)


def test_engine_run_consumes_normal_flow() -> None:
    async def main() -> None:
        engine = MarketDataEngine(
            queue_size=5,
            clock=lambda: datetime.now(UTC),
            max_age=timedelta(seconds=5),
        )
        task = asyncio.create_task(engine.run())
        now = datetime.now(UTC)
        for i in range(3):
            await engine.enqueue(make_tick_event(f"seq-{i}", now - timedelta(seconds=1)))
        await asyncio.sleep(0.25)
        await engine.stop()
        await task
        assert engine.metrics.ticks_received == 3

    asyncio.run(main())


def test_engine_backpressure_drops_when_full() -> None:
    async def main() -> None:
        engine = MarketDataEngine(queue_size=2, drop_policy="drop_newest")
        now = datetime.now(UTC)
        assert await engine.enqueue(make_tick_event("s1", now)) is True
        assert await engine.enqueue(make_tick_event("s2", now)) is True
        assert await engine.enqueue(make_tick_event("s3", now)) is False
        assert engine.metrics.dropped_events == 1
        assert engine.queue_size == 2

    asyncio.run(main())


def test_engine_burst_traffic_within_capacity_has_no_loss() -> None:
    async def main() -> None:
        engine = MarketDataEngine(
            queue_size=100,
            clock=lambda: datetime.now(UTC),
            max_age=timedelta(seconds=5),
        )
        task = asyncio.create_task(engine.run())
        now = datetime.now(UTC)
        for i in range(50):
            await engine.enqueue(make_tick_event(f"seq-{i}", now - timedelta(seconds=1)))
        # wait for all to be consumed
        for _ in range(50):
            if engine.metrics.ticks_received >= 50:
                break
            await asyncio.sleep(0.02)
        await engine.stop()
        await task
        assert engine.metrics.ticks_received == 50
        assert engine.metrics.dropped_events == 0

    asyncio.run(main())
