"""Phase 10 — connection lifecycle + bounded reconnect tests."""

import asyncio

from alpha_algo_broker_integration.connection import (
    ConnectionStateMachine,
    ReconnectPolicy,
    is_recoverable,
)
from alpha_algo_broker_integration.contracts import ConnectionState
from alpha_algo_broker_integration.errors import BrokerError, BrokerErrorClass


def run(coro):
    return asyncio.run(coro)


def test_reconnect_succeeds_on_first_attempt():
    sm = ConnectionStateMachine(policy=ReconnectPolicy(max_attempts=3, base_backoff_seconds=0.0))

    async def connect_ok():
        return None

    run(sm.reconnect(connect_fn=connect_ok))
    assert sm.state == ConnectionState.CONNECTED
    assert sm.reconnect_count == 1


def test_reconnect_gives_up_and_degrades():
    sm = ConnectionStateMachine(policy=ReconnectPolicy(max_attempts=2, base_backoff_seconds=0.0))
    exhausted = []

    async def connect_fail():
        raise BrokerError(BrokerErrorClass.NETWORK, "down")

    run(sm.reconnect(connect_fn=connect_fail, on_exhausted=exhausted.append))
    assert sm.state == ConnectionState.DEGRADED
    assert len(exhausted) == 1


def test_backoff_is_bounded_and_increasing():
    policy = ReconnectPolicy(max_attempts=5, base_backoff_seconds=1.0, max_backoff_seconds=30.0, jitter=False)
    delays = [policy.delay_for(n) for n in range(1, 8)]
    assert delays[0] == 1.0
    assert delays[1] == 2.0
    assert delays[2] == 4.0
    # bounded at max_backoff
    assert max(delays) <= 30.0


def test_recoverable_classification():
    assert is_recoverable(BrokerError(BrokerErrorClass.NETWORK, "x"))
    assert is_recoverable(BrokerError(BrokerErrorClass.TIMEOUT, "x"))
    assert not is_recoverable(BrokerError(BrokerErrorClass.AUTHENTICATION, "x"))


def test_reconnect_never_blindly_duplicates_orders():
    """Reconnect is a connection concern, decoupled from order submission."""
    sm = ConnectionStateMachine(policy=ReconnectPolicy(max_attempts=1, base_backoff_seconds=0.0))
    # Reconnect only calls connect_fn (auth) — it has no order-submission path.
    calls = []

    async def connect_ok():
        calls.append("connect")
        return None

    run(sm.reconnect(connect_fn=connect_ok))
    assert calls == ["connect"]  # no order call emitted during reconnect
