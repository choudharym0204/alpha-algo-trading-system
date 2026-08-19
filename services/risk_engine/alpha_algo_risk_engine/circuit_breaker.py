"""Circuit breaker (Phase 6) — scoped, threshold-based, fail-closed.

A breaker opens after ``failure_threshold`` failures within ``window``, rejects
everything while open, moves to HALF_OPEN after ``reset_after``, allows a bounded
number of probe evaluations, and closes again on a probe success. Open state is
fail-closed: ``allows()`` returns False and the risk service rejects immediately.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Callable


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True)
class CircuitBreakerConfig:
    failure_threshold: int = 5
    window: timedelta = timedelta(seconds=60)
    reset_after: timedelta = timedelta(seconds=30)
    half_open_probe_limit: int = 1

    def __post_init__(self) -> None:
        if self.failure_threshold <= 0:
            raise ValueError("failure_threshold must be positive")
        if self.window <= timedelta(0):
            raise ValueError("window must be positive")
        if self.reset_after <= timedelta(0):
            raise ValueError("reset_after must be positive")
        if self.half_open_probe_limit <= 0:
            raise ValueError("half_open_probe_limit must be positive")


class CircuitBreaker:
    """A single scoped breaker (closed → open → half-open → closed)."""

    def __init__(
        self,
        config: CircuitBreakerConfig | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.config = config or CircuitBreakerConfig()
        self._clock = clock or (lambda: datetime.now(tz=UTC))
        self.state = CircuitState.CLOSED
        self._failures: list[datetime] = []
        self._opened_at: datetime | None = None
        self._half_open_probes: int = 0

    def allows(self, now: datetime | None = None) -> bool:
        now = now or self._clock()
        self._prune(now)
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if self._opened_at is not None and now - self._opened_at >= self.config.reset_after:
                self.state = CircuitState.HALF_OPEN
                self._half_open_probes = 0
                return True
            return False
        # HALF_OPEN: allow a bounded number of probes.
        return self._half_open_probes < self.config.half_open_probe_limit

    def record_failure(self, now: datetime | None = None) -> None:
        now = now or self._clock()
        self._prune(now)
        self._failures.append(now)
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            self._opened_at = now
            self._half_open_probes = 0
            return
        if self.state == CircuitState.CLOSED and len(self._failures) >= self.config.failure_threshold:
            self.state = CircuitState.OPEN
            self._opened_at = now

    def record_success(self, now: datetime | None = None) -> None:
        now = now or self._clock()
        self._prune(now)
        if self.state == CircuitState.HALF_OPEN:
            self._half_open_probes += 1
            if self._half_open_probes >= self.config.half_open_probe_limit:
                self.state = CircuitState.CLOSED
                self._failures.clear()
                self._opened_at = None
        elif self.state == CircuitState.CLOSED:
            self._failures.clear()

    def _prune(self, now: datetime) -> None:
        cutoff = now - self.config.window
        self._failures = [t for t in self._failures if t > cutoff]


class CircuitBreakerRegistry:
    """Named-scope breakers (global / strategy:<id> / instrument:<id> / account:<id>)."""

    def __init__(
        self,
        config: CircuitBreakerConfig | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = config or CircuitBreakerConfig()
        self._clock = clock or (lambda: datetime.now(tz=UTC))
        self._breakers: dict[str, CircuitBreaker] = {}

    def _breaker(self, scope_key: str) -> CircuitBreaker:
        breaker = self._breakers.get(scope_key)
        if breaker is None:
            breaker = CircuitBreaker(self._config, clock=self._clock)
            self._breakers[scope_key] = breaker
        return breaker

    def allows(self, scope_key: str, now: datetime | None = None) -> bool:
        return self._breaker(scope_key).allows(now)

    def record_failure(self, scope_key: str, now: datetime | None = None) -> None:
        self._breaker(scope_key).record_failure(now)

    def record_success(self, scope_key: str, now: datetime | None = None) -> None:
        self._breaker(scope_key).record_success(now)
