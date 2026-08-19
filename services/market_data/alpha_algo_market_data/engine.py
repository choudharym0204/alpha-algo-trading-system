"""Market Data Engine — the streaming pipeline orchestration.

``ingest_raw`` runs the deterministic pipeline:

    validate → normalize → duplicate-detect → freshness → fan-out → persist

An async bounded queue + consumer loop provide backpressure. The consumer loop
offloads ``ingest_raw`` (including persistence) to a worker thread so a slow
synchronous DB commit never blocks the event loop (heartbeat/reconnect/stop
stay responsive). Consumers and the repository are injected so the engine stays
decoupled from the Strategy Engine (Phase 4) and any specific DB wiring.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Callable

from alpha_algo_contracts import MarketCandle, MarketTick
from alpha_algo_market_data.backpressure import BoundedQueue
from alpha_algo_market_data.metrics import MarketDataMetrics
from alpha_algo_market_data.normalization import normalize
from alpha_algo_market_data.provider import RawMarketEvent
from alpha_algo_market_data.repository import MarketDataRepository
from alpha_algo_market_data.safety import DuplicateTickDetector, evaluate_staleness
from alpha_algo_market_data.validation import (
    RawEventValidationError,
    TickRejectedError,
    check_supported_symbol,
    validate_raw_event,
)

logger = logging.getLogger(__name__)

TickConsumer = Callable[[MarketTick], None]
CandleConsumer = Callable[[MarketCandle], None]


class IngestStatus(StrEnum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    STALE = "stale"
    FUTURE = "future_timestamp"
    REJECTED = "rejected"


@dataclass(frozen=True)
class IngestResult:
    status: IngestStatus
    reason: str
    tick: MarketTick | None = None
    candle: MarketCandle | None = None


class MarketDataEngine:
    def __init__(
        self,
        *,
        repository: MarketDataRepository | None = None,
        metrics: MarketDataMetrics | None = None,
        allowed_symbols: set[str] | None = None,
        max_age: timedelta | None = None,
        queue_size: int = 10000,
        drop_policy: str = "drop_newest",
        persist_enabled: bool = True,
        clock: Callable[[], datetime] | None = None,
        duplicate_detector: DuplicateTickDetector | None = None,
        dedupe_maxsize: int = 100_000,
    ) -> None:
        self._repository = repository
        self._metrics = metrics or MarketDataMetrics()
        self._allowed_symbols = allowed_symbols
        self._max_age = max_age if max_age is not None else timedelta(seconds=5)
        self._persist_enabled = persist_enabled
        self._clock = clock or (lambda: datetime.now(UTC))
        self._duplicate_detector = duplicate_detector or DuplicateTickDetector(
            maxsize=dedupe_maxsize
        )
        self._queue: BoundedQueue[RawMarketEvent] = BoundedQueue(
            queue_size, drop_policy=drop_policy
        )
        self._tick_consumers: list[TickConsumer] = []
        self._candle_consumers: list[CandleConsumer] = []
        self._running = False

    @property
    def metrics(self) -> MarketDataMetrics:
        return self._metrics

    @property
    def queue_size(self) -> int:
        return self._queue.qsize

    def add_tick_consumer(self, consumer: TickConsumer) -> None:
        self._tick_consumers.append(consumer)

    def add_candle_consumer(self, consumer: CandleConsumer) -> None:
        self._candle_consumers.append(consumer)

    def ingest_raw(self, event: RawMarketEvent) -> IngestResult:
        """Run the full pipeline for one raw event (synchronous, deterministic)."""
        try:
            validate_raw_event(event)
        except RawEventValidationError as exc:
            self._metrics.rejected_events += 1
            return IngestResult(IngestStatus.REJECTED, f"malformed: {exc}")

        try:
            normalized = normalize(event)
        except (RawEventValidationError, KeyError, TypeError, ValueError) as exc:
            self._metrics.normalization_failures += 1
            self._metrics.rejected_events += 1
            return IngestResult(IngestStatus.REJECTED, f"normalization: {exc}")

        try:
            check_supported_symbol(normalized.symbol, self._allowed_symbols)
        except TickRejectedError as exc:
            self._metrics.rejected_events += 1
            return IngestResult(IngestStatus.REJECTED, exc.reason)

        if isinstance(normalized, MarketTick):
            self._metrics.record_tick()
            return self._ingest_tick(normalized)
        self._metrics.record_candle()
        return self._ingest_candle(normalized)

    def _ingest_tick(self, tick: MarketTick) -> IngestResult:
        if self._duplicate_detector.is_duplicate(tick):
            self._metrics.duplicates += 1
            return IngestResult(IngestStatus.DUPLICATE, "duplicate")

        decision = evaluate_staleness(tick, now=self._clock(), max_age=self._max_age)
        if decision.is_stale:
            if decision.reason == "tick_timestamp_in_future":
                self._metrics.future_timestamps += 1
                return IngestResult(IngestStatus.FUTURE, "future_timestamp")
            self._metrics.stale_events += 1
            return IngestResult(IngestStatus.STALE, "stale")

        self._fan_out_tick(tick)
        self._persist_tick(tick)
        return IngestResult(IngestStatus.ACCEPTED, "accepted", tick=tick)

    def _ingest_candle(self, candle: MarketCandle) -> IngestResult:
        self._fan_out_candle(candle)
        self._persist_candle(candle)
        return IngestResult(IngestStatus.ACCEPTED, "accepted", candle=candle)

    def _fan_out_tick(self, tick: MarketTick) -> None:
        for consumer in self._tick_consumers:
            self._safe_dispatch(consumer, tick)

    def _fan_out_candle(self, candle: MarketCandle) -> None:
        for consumer in self._candle_consumers:
            self._safe_dispatch(consumer, candle)

    def _safe_dispatch(self, consumer: Callable, value) -> None:
        # A raising consumer must not take down ingestion for other consumers.
        try:
            consumer(value)
        except Exception as exc:  # noqa: BLE001 - isolate consumer faults
            self._metrics.consumer_failures += 1
            logger.warning("market-data consumer failed: %s", exc)

    def _persist_tick(self, tick: MarketTick) -> None:
        if self._repository is None or not self._persist_enabled:
            return
        try:
            self._repository.persist_tick(tick)
            self._metrics.persisted_ticks += 1
        except Exception as exc:  # noqa: BLE001 - fail-safe persistence
            self._metrics.persistence_failures += 1
            logger.warning("failed to persist tick: %s", exc)

    def _persist_candle(self, candle: MarketCandle) -> None:
        if self._repository is None or not self._persist_enabled:
            return
        try:
            self._repository.persist_candle(candle)
            self._metrics.persisted_candles += 1
        except Exception as exc:  # noqa: BLE001 - fail-safe persistence
            self._metrics.persistence_failures += 1
            logger.warning("failed to persist candle: %s", exc)

    async def enqueue(self, event: RawMarketEvent) -> bool:
        """Enqueue a raw event; returns False when the event was dropped."""
        accepted = self._queue.put_nowait(event)
        if not accepted:
            self._metrics.dropped_events += 1
            logger.warning(
                "market-data queue full (policy=%s): dropping event from %s",
                self._queue.drop_policy,
                event.provider,
            )
        return accepted

    async def run(self) -> None:
        """Consume the queue and run the pipeline until :meth:`stop` is called."""
        self._running = True
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                continue
            try:
                # Offload the (synchronous) pipeline + persistence to a thread so
                # slow DB commits never block the event loop.
                await asyncio.to_thread(self.ingest_raw, event)
            finally:
                self._queue.task_done()

    async def stop(self) -> None:
        self._running = False
