"""Market-data service — the composition root for Phase 3.

Wires a provider, a connection manager (reconnect/heartbeat/watchdog), and the
streaming engine together so the pipeline can actually run:

    provider → set_event_handler → service._on_event → engine.enqueue
    engine.run → validate/normalize/dedupe/freshness → consumers → TimescaleDB

A ``MarketDataService`` owns the lifecycle (``start``/``stop``) and a heartbeat
watchdog that reconnects a silently-dead provider.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import timedelta

from alpha_algo_market_data.connection import ProviderConnectionManager
from alpha_algo_market_data.engine import MarketDataEngine
from alpha_algo_market_data.fake_provider import FakeMarketDataProvider
from alpha_algo_market_data.metrics import MarketDataMetrics
from alpha_algo_market_data.provider import MarketDataProvider, RawMarketEvent
from alpha_algo_market_data.repository import MarketDataRepository

logger = logging.getLogger(__name__)


@dataclass
class MarketDataServiceConfig:
    provider_name: str = "fake"
    symbols: list[str] = field(default_factory=list)
    queue_size: int = 10000
    drop_policy: str = "drop_newest"
    max_age_seconds: float = 5.0
    reconnect_max_attempts: int = 10
    reconnect_base_delay: float = 0.5
    reconnect_max_delay: float = 30.0
    heartbeat_timeout_seconds: float = 45.0
    connect_timeout_seconds: float = 10.0
    dedupe_maxsize: int = 100_000


def _build_provider(provider_name: str) -> MarketDataProvider:
    if provider_name == "fake":
        return FakeMarketDataProvider()
    raise ValueError(f"unknown market-data provider: {provider_name!r}")


def build_market_data_service(
    config: MarketDataServiceConfig,
    *,
    repository: MarketDataRepository | None = None,
    metrics: MarketDataMetrics | None = None,
) -> "MarketDataService":
    provider = _build_provider(config.provider_name)
    metrics = metrics or MarketDataMetrics()
    engine = MarketDataEngine(
        repository=repository,
        metrics=metrics,
        max_age=timedelta(seconds=config.max_age_seconds),
        queue_size=config.queue_size,
        drop_policy=config.drop_policy,
        dedupe_maxsize=config.dedupe_maxsize,
    )
    connection = ProviderConnectionManager(
        provider,
        metrics=metrics,
        reconnect_max_attempts=config.reconnect_max_attempts,
        reconnect_base_delay=config.reconnect_base_delay,
        reconnect_max_delay=config.reconnect_max_delay,
        heartbeat_timeout_seconds=config.heartbeat_timeout_seconds,
        connect_timeout_seconds=config.connect_timeout_seconds,
    )
    return MarketDataService(provider, engine, connection, config.symbols)


class MarketDataService:
    def __init__(
        self,
        provider: MarketDataProvider,
        engine: MarketDataEngine,
        connection: ProviderConnectionManager,
        symbols: list[str],
    ) -> None:
        self._provider = provider
        self._engine = engine
        self._connection = connection
        self._symbols = list(symbols)
        self._engine_task: asyncio.Task | None = None
        self._monitor_task: asyncio.Task | None = None

    @property
    def engine(self) -> MarketDataEngine:
        return self._engine

    @property
    def metrics(self) -> MarketDataMetrics:
        return self._engine.metrics

    async def start(self) -> None:
        await self._connection.connect()
        self._provider.set_event_handler(self._on_event)
        if self._symbols:
            await self._provider.subscribe(self._symbols)
        self._engine_task = asyncio.create_task(self._engine.run())
        self._monitor_task = asyncio.create_task(self._connection.run_monitor())
        logger.info("market-data service started (provider=%s)", self._provider.provider_name)

    async def _on_event(self, event: RawMarketEvent) -> None:
        # Any inbound data proves the connection is alive.
        self._connection.record_heartbeat()
        await self._engine.enqueue(event)

    async def stop(self) -> None:
        await self._engine.stop()
        self._connection.stop_monitor()
        tasks = [t for t in (self._engine_task, self._monitor_task) if t is not None]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await self._connection.disconnect()
        logger.info("market-data service stopped")
