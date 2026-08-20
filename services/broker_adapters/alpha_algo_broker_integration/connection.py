"""Connection lifecycle + bounded reconnect (Phase 10).

Implements the DISCONNECTED → CONNECTING → CONNECTED → DEGRADED →
RECONNECTING → CONNECTED state machine with bounded, jittered backoff. Reconnect
never duplicates an order request; re-subscription is delegated to the adapter.
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Awaitable, Callable

from alpha_algo_broker_integration.contracts import ConnectionState
from alpha_algo_broker_integration.errors import BrokerError, BrokerErrorClass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReconnectPolicy:
    max_attempts: int = 5
    base_backoff_seconds: float = 1.0
    max_backoff_seconds: float = 30.0
    jitter: bool = True

    def delay_for(self, attempt_number: int) -> float:
        delay = min(
            self.base_backoff_seconds * (2 ** max(0, attempt_number - 1)),
            self.max_backoff_seconds,
        )
        if self.jitter and delay > 0:
            delay = delay * random.uniform(0.5, 1.5)
        return delay


class ConnectionStateMachine:
    """Owns the connection state and drives bounded reconnect."""

    def __init__(self, *, policy: ReconnectPolicy | None = None) -> None:
        self._policy = policy or ReconnectPolicy()
        self._state = ConnectionState.DISCONNECTED
        self._reconnects = 0
        self._last_change: datetime | None = None

    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def reconnect_count(self) -> int:
        return self._reconnects

    def transition(self, new_state: ConnectionState) -> None:
        if new_state == self._state:
            return
        self._state = new_state
        self._last_change = datetime.now(UTC)
        logger.debug("connection state -> %s", new_state.value)

    async def reconnect(
        self,
        *,
        connect_fn: Callable[[], Awaitable[None]],
        on_exhausted: Callable[[BrokerError], None] | None = None,
    ) -> None:
        """Attempt bounded reconnect; never raises out of the retry loop.

        ``connect_fn`` raises ``BrokerError`` on failure. After ``max_attempts``
        the state is left DEGRADED and ``on_exhausted`` (if provided) is called.
        """
        self._state = ConnectionState.RECONNECTING
        for attempt in range(1, self._policy.max_attempts + 1):
            try:
                await connect_fn()
                self._reconnects += 1
                self._state = ConnectionState.CONNECTED
                return
            except BrokerError as exc:
                logger.warning("reconnect attempt %d failed: %s", attempt, exc.message)
                if attempt >= self._policy.max_attempts:
                    self._state = ConnectionState.DEGRADED
                    if on_exhausted is not None:
                        on_exhausted(exc)
                    return
                await asyncio.sleep(self._policy.delay_for(attempt))
        self._state = ConnectionState.DEGRADED


def is_recoverable(error: BrokerError) -> bool:
    """True when a reconnect/retry is appropriate for this error class."""
    return error.error_class in {
        BrokerErrorClass.NETWORK,
        BrokerErrorClass.TIMEOUT,
        BrokerErrorClass.PROVIDER_UNAVAILABLE,
        BrokerErrorClass.RATE_LIMIT,
    }
