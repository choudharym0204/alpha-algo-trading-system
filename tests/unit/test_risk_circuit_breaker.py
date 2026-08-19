"""Phase 6 — circuit breaker behavior (scoped, threshold-based, fail-closed)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from alpha_algo_risk_engine.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerRegistry,
    CircuitState,
)


def test_closed_allows():
    b = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3))
    assert b.allows() is True
    assert b.state == CircuitState.CLOSED


def test_opens_after_threshold_failures():
    b = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3))
    for _ in range(3):
        b.record_failure()
    assert b.state == CircuitState.OPEN
    assert b.allows() is False


def test_not_open_below_threshold():
    b = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3))
    b.record_failure()
    b.record_failure()
    assert b.state == CircuitState.CLOSED
    assert b.allows() is True


def test_half_open_after_reset_interval():
    b = CircuitBreaker(
        CircuitBreakerConfig(failure_threshold=1, reset_after=timedelta(seconds=1))
    )
    b.record_failure()
    assert b.state == CircuitState.OPEN

    # Advance the clock beyond reset_after via a fake clock.
    from datetime import UTC, datetime

    now = datetime.now(UTC) + timedelta(seconds=2)
    assert b.allows(now) is True
    assert b.state == CircuitState.HALF_OPEN


def test_half_open_probe_success_closes():
    from datetime import UTC, datetime

    base = datetime.now(UTC)
    clock_state = {"now": base}

    def clock():
        return clock_state["now"]

    b = CircuitBreaker(
        CircuitBreakerConfig(failure_threshold=1, reset_after=timedelta(seconds=1)),
        clock=clock,
    )
    b.record_failure()
    assert b.state == CircuitState.OPEN
    clock_state["now"] = base + timedelta(seconds=2)
    assert b.allows() is True  # transition to half-open, probe allowed
    b.record_success()
    assert b.state == CircuitState.CLOSED


def test_half_open_probe_failure_reopens():
    from datetime import UTC, datetime

    base = datetime.now(UTC)
    clock_state = {"now": base}

    def clock():
        return clock_state["now"]

    b = CircuitBreaker(
        CircuitBreakerConfig(failure_threshold=1, reset_after=timedelta(seconds=1)),
        clock=clock,
    )
    b.record_failure()
    clock_state["now"] = base + timedelta(seconds=2)
    assert b.allows() is True
    b.record_failure()
    assert b.state == CircuitState.OPEN


def test_failures_pruned_outside_window():
    from datetime import UTC, datetime

    base = datetime.now(UTC)
    clock_state = {"now": base}

    def clock():
        return clock_state["now"]

    b = CircuitBreaker(
        CircuitBreakerConfig(failure_threshold=2, window=timedelta(seconds=10)),
        clock=clock,
    )
    b.record_failure()
    clock_state["now"] = base + timedelta(seconds=11)  # first failure expires
    b.record_failure()
    assert b.state == CircuitState.CLOSED


def test_registry_scopes_are_independent():
    reg = CircuitBreakerRegistry(CircuitBreakerConfig(failure_threshold=1))
    reg.record_failure("strategy:abc")
    assert reg.allows("strategy:abc") is False
    assert reg.allows("instrument:xyz") is True


def test_config_validation():
    with pytest.raises(ValueError):
        CircuitBreakerConfig(failure_threshold=0)
    with pytest.raises(ValueError):
        CircuitBreakerConfig(window=timedelta(0))
    with pytest.raises(ValueError):
        CircuitBreakerConfig(reset_after=timedelta(0))
    with pytest.raises(ValueError):
        CircuitBreakerConfig(half_open_probe_limit=0)
