"""Connection lifecycle: bounded reconnect (exponential backoff), heartbeat
monitor, and a provider connection manager that ties state + reconnect +
heartbeat + a watchdog loop together.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Awaitable, Callable

from alpha_algo_market_data.metrics import MarketDataMetrics
from alpha_algo_market_data.provider import ConnectionState, MarketDataProvider

logger = logging.getLogger(__name__)


def backoff_delay(attempt: int, base: float, max_delay: float) -> float:
    """Exponential backoff capped at ``max_delay`` (attempt is 1-based)."""
    if attempt < 1:
        raise ValueError("attempt must be >= 1")
    if base <= 0:
        raise ValueError("base must be > 0")
    if max_delay < base:
        raise ValueError("max_delay must be >= base")
    return min(base * (2 ** (attempt - 1)), max_delay)


@dataclass(frozen=True)
class ReconnectResult:
    attempts_used: int
    succeeded: bool
    last_error: BaseException | None = None


class Reconnector:
    """Runs an async connect callback with bounded exponential-backoff retries."""

    def __init__(self, *, max_attempts: int, base_delay: float, max_delay: float) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self._max_attempts = max_attempts
        self._base_delay = base_delay
        self._max_delay = max_delay

    async def connect(
        self, connect_fn: Callable[[], Awaitable[None]]
    ) -> ReconnectResult:
        last_error: BaseException | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                await connect_fn()
                return ReconnectResult(attempts_used=attempt, succeeded=True)
            except Exception as exc:  # noqa: BLE001 - retry loop
                last_error = exc
                logger.warning(
                    "connect attempt %d/%d failed: %s",
                    attempt,
                    self._max_attempts,
                    exc,
                )
                if attempt < self._max_attempts:
                    await asyncio.sleep(
                        backoff_delay(attempt, self._base_delay, self._max_delay)
                    )
        return ReconnectResult(
            attempts_used=self._max_attempts, succeeded=False, last_error=last_error
        )


class HeartbeatMonitor:
    """Flags a dead connection when no activity has arrived within a timeout.

    A connection is "armed" the first time ``record_heartbeat`` is called (or
    on connect). If no heartbeat/data arrives for ``timeout_seconds`` the
    connection is considered dead.
    """

    def __init__(self, timeout_seconds: float) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        self._timeout = timeout_seconds
        self._last_activity: datetime | None = None

    @property
    def last_heartbeat(self) -> datetime | None:
        return self._last_activity

    def record_heartbeat(self, now: datetime) -> None:
        self._last_activity = now

    def is_alive(self, now: datetime) -> bool:
        if self._last_activity is None:
            return True  # not yet armed
        return (now - self._last_activity) <= timedelta(seconds=self._timeout)

    def reset(self) -> None:
        self._last_activity = None


class ProviderConnectionManager:
    """Orchestrates connect/disconnect/reconnect state, heartbeat, and timeouts."""

    def __init__(
        self,
        provider: MarketDataProvider,
        *,
        metrics: MarketDataMetrics,
        reconnect_max_attempts: int = 10,
        reconnect_base_delay: float = 0.5,
        reconnect_max_delay: float = 30.0,
        heartbeat_timeout_seconds: float = 45.0,
        connect_timeout_seconds: float = 10.0,
    ) -> None:
        self._provider = provider
        self._metrics = metrics
        self._reconnector = Reconnector(
            max_attempts=max(1, reconnect_max_attempts),
            base_delay=reconnect_base_delay,
            max_delay=reconnect_max_delay,
        )
        self._heartbeat = HeartbeatMonitor(heartbeat_timeout_seconds)
        self._connect_timeout = connect_timeout_seconds
        self._state = ConnectionState.DISCONNECTED
        self._monitoring = False

    @property
    def state(self) -> ConnectionState:
        return self._state

    async def connect(self) -> None:
        self._state = ConnectionState.CONNECTING
        try:
            await asyncio.wait_for(
                self._provider.connect(), timeout=self._connect_timeout
            )
        except Exception:
            self._state = ConnectionState.FAILED
            self._metrics.connect_failures += 1
            raise
        self._state = ConnectionState.CONNECTED
        self._metrics.connected += 1
        self._heartbeat.record_heartbeat(datetime.now(UTC))

    async def disconnect(self) -> None:
        await self._provider.disconnect()
        self._state = ConnectionState.CLOSED
        self._metrics.disconnected += 1

    async def _connect_with_timeout(self) -> None:
        await asyncio.wait_for(self._provider.connect(), timeout=self._connect_timeout)

    async def reconnect(self) -> bool:
        self._state = ConnectionState.RECONNECTING
        self._metrics.reconnects += 1
        # Best-effort teardown of any stale/partial connection first.
        try:
            await self._provider.disconnect()
        except Exception:  # noqa: BLE001 - best-effort cleanup
            logger.debug("best-effort disconnect before reconnect failed", exc_info=True)
        result = await self._reconnector.connect(self._connect_with_timeout)
        if result.succeeded:
            self._state = ConnectionState.CONNECTED
            self._heartbeat.record_heartbeat(datetime.now(UTC))
            return True
        self._state = ConnectionState.FAILED
        self._metrics.reconnect_failures += 1
        return False

    def record_heartbeat(self, now: datetime | None = None) -> None:
        self._heartbeat.record_heartbeat(now or datetime.now(UTC))

    def is_alive(self, now: datetime | None = None) -> bool:
        return self._state == ConnectionState.CONNECTED and self._heartbeat.is_alive(
            now or datetime.now(UTC)
        )

    async def run_monitor(self, interval_seconds: float = 1.0) -> None:
        """Watchdog: poll liveness and reconnect when the connection goes dead."""
        self._monitoring = True
        while self._monitoring:
            await asyncio.sleep(interval_seconds)
            if self._state == ConnectionState.CONNECTED and not self._heartbeat.is_alive(
                datetime.now(UTC)
            ):
                self._metrics.heartbeat_failures += 1
                logger.warning("provider heartbeat timeout — reconnecting")
                await self.reconnect()

    def stop_monitor(self) -> None:
        self._monitoring = False
