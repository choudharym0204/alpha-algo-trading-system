from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from alpha_algo_market_data import (
    FakeMarketDataProvider,
    HeartbeatMonitor,
    MarketDataMetrics,
    ProviderAuthenticationError,
    ProviderConnectionManager,
    Reconnector,
    backoff_delay,
)


def test_backoff_delay_is_exponential_and_capped() -> None:
    assert backoff_delay(1, 0.5, 30.0) == 0.5
    assert backoff_delay(2, 0.5, 30.0) == 1.0
    assert backoff_delay(3, 0.5, 30.0) == 2.0
    assert backoff_delay(10, 0.5, 30.0) == 30.0  # capped


def test_fake_provider_connect_disconnect_and_health() -> None:
    async def main() -> None:
        provider = FakeMarketDataProvider()
        await provider.connect()
        assert provider.is_connected is True
        health = await provider.health()
        assert health.authenticated is True
        assert health.state.value == "connected"
        await provider.disconnect()
        assert provider.is_connected is False

    asyncio.run(main())


def test_fake_provider_authentication_failure() -> None:
    async def main() -> None:
        provider = FakeMarketDataProvider()
        provider.fail_authenticate = True
        with pytest.raises(ProviderAuthenticationError):
            await provider.connect()

    asyncio.run(main())


def test_fake_provider_connect_failure() -> None:
    async def main() -> None:
        provider = FakeMarketDataProvider()
        provider.fail_connect = True
        with pytest.raises(ConnectionError):
            await provider.connect()
        assert provider.is_connected is False

    asyncio.run(main())


def test_reconnector_succeeds_first_try() -> None:
    async def main() -> None:
        reconnector = Reconnector(max_attempts=3, base_delay=0.01, max_delay=0.1)
        calls = {"n": 0}

        async def connect() -> None:
            calls["n"] += 1

        result = await reconnector.connect(connect)
        assert result.succeeded is True
        assert result.attempts_used == 1
        assert calls["n"] == 1

    asyncio.run(main())


def test_reconnector_retries_then_fails() -> None:
    async def main() -> None:
        reconnector = Reconnector(max_attempts=3, base_delay=0.01, max_delay=0.1)
        calls = {"n": 0}

        async def connect() -> None:
            calls["n"] += 1
            raise ConnectionError("refused")

        result = await reconnector.connect(connect)
        assert result.succeeded is False
        assert result.attempts_used == 3
        assert calls["n"] == 3

    asyncio.run(main())


def test_reconnector_recovers_after_transient_failure() -> None:
    async def main() -> None:
        reconnector = Reconnector(max_attempts=5, base_delay=0.01, max_delay=0.1)
        calls = {"n": 0}

        async def connect() -> None:
            calls["n"] += 1
            if calls["n"] < 3:
                raise ConnectionError("refused")

        result = await reconnector.connect(connect)
        assert result.succeeded is True
        assert result.attempts_used == 3

    asyncio.run(main())


def test_heartbeat_monitor_flags_dead_connection() -> None:
    monitor = HeartbeatMonitor(timeout_seconds=5)
    now = datetime.now(UTC)
    assert monitor.is_alive(now) is True  # not yet armed
    monitor.record_heartbeat(now)  # arm the deadline
    assert monitor.is_alive(now) is True
    assert monitor.is_alive(now + timedelta(seconds=6)) is False
    monitor.record_heartbeat(now + timedelta(seconds=6))  # refresh
    assert monitor.is_alive(now + timedelta(seconds=6)) is True


def test_connection_manager_connect_failure_then_reconnect() -> None:
    async def main() -> None:
        provider = FakeMarketDataProvider()
        provider.fail_connect = True
        metrics = MarketDataMetrics()
        manager = ProviderConnectionManager(
            provider,
            metrics=metrics,
            reconnect_max_attempts=2,
            reconnect_base_delay=0.01,
            reconnect_max_delay=0.1,
            heartbeat_timeout_seconds=5,
            connect_timeout_seconds=5,
        )
        with pytest.raises(ConnectionError):
            await manager.connect()
        assert manager.state.value == "failed"
        assert metrics.connect_failures == 1
        assert metrics.reconnect_failures == 0  # initial connect is not a reconnect

        provider.fail_connect = False
        ok = await manager.reconnect()
        assert ok is True
        assert manager.state.value == "connected"
        assert metrics.reconnects == 1

    asyncio.run(main())


def test_reconnect_wraps_connect_in_timeout() -> None:
    async def main() -> None:
        provider = FakeMarketDataProvider()

        async def hang() -> None:
            await asyncio.sleep(10)

        provider.connect = hang  # type: ignore[method-assign]
        metrics = MarketDataMetrics()
        manager = ProviderConnectionManager(
            provider,
            metrics=metrics,
            reconnect_max_attempts=1,
            reconnect_base_delay=0.01,
            reconnect_max_delay=0.1,
            heartbeat_timeout_seconds=5,
            connect_timeout_seconds=0.05,
        )
        ok = await manager.reconnect()
        assert ok is False
        assert manager.state.value == "failed"
        assert metrics.reconnect_failures == 1

    asyncio.run(main())


def test_connection_manager_watchdog_reconnects_dead_connection() -> None:
    async def main() -> None:
        provider = FakeMarketDataProvider()
        metrics = MarketDataMetrics()
        manager = ProviderConnectionManager(
            provider,
            metrics=metrics,
            reconnect_max_attempts=1,
            reconnect_base_delay=0.01,
            reconnect_max_delay=0.1,
            heartbeat_timeout_seconds=0.05,
            connect_timeout_seconds=5,
        )
        await manager.connect()
        assert manager.state.value == "connected"

        monitor_task = asyncio.create_task(manager.run_monitor(interval_seconds=0.02))
        for _ in range(100):
            if metrics.heartbeat_failures >= 1 and metrics.reconnects >= 1:
                break
            await asyncio.sleep(0.01)

        manager.stop_monitor()
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass

        assert metrics.heartbeat_failures >= 1
        assert metrics.reconnects >= 1
        assert manager.state.value == "connected"

    asyncio.run(main())
