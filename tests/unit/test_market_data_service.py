from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from alpha_algo_market_data import (
    EventKind,
    FakeMarketDataProvider,
    MarketDataEngine,
    MarketDataMetrics,
    MarketDataRepository,
    MarketDataService,
    MarketDataServiceConfig,
    ProviderConnectionManager,
    RawMarketEvent,
    build_market_data_service,
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


def test_build_market_data_service_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="unknown market-data provider"):
        build_market_data_service(MarketDataServiceConfig(provider_name="nope"))


def test_build_market_data_service_wires_fake_provider() -> None:
    service = build_market_data_service(
        MarketDataServiceConfig(provider_name="fake", symbols=["RELIANCE"])
    )
    assert service.engine is not None
    assert service.metrics is not None


def test_service_pipeline_end_to_end() -> None:
    async def main() -> None:
        provider = FakeMarketDataProvider()
        repository = MagicMock(spec=MarketDataRepository)
        metrics = MarketDataMetrics()
        engine = MarketDataEngine(
            repository=repository, metrics=metrics, max_age=timedelta(seconds=5)
        )
        connection = ProviderConnectionManager(
            provider,
            metrics=metrics,
            reconnect_max_attempts=2,
            reconnect_base_delay=0.01,
            reconnect_max_delay=0.1,
            heartbeat_timeout_seconds=5,
            connect_timeout_seconds=5,
        )
        service = MarketDataService(provider, engine, connection, symbols=["RELIANCE"])
        accepted: list = []
        engine.add_tick_consumer(accepted.append)

        await service.start()
        assert provider.is_connected is True
        assert "RELIANCE" in provider.subscriptions

        await provider.emit(
            make_tick_event("seq-1", datetime.now(UTC) - timedelta(seconds=1))
        )
        for _ in range(50):
            if accepted:
                break
            await asyncio.sleep(0.02)

        await service.stop()

        assert len(accepted) == 1
        repository.persist_tick.assert_called_once()
        assert provider.is_connected is False  # disconnected on stop

    asyncio.run(main())
