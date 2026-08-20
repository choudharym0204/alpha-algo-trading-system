"""Provider-specific rate limiting (Phase 10).

Each adapter models its own provider limits. A token-bucket limiter provides
bounded, non-blocking throttling with per-adapter limits; ``retry-after`` hints
from the provider are surfaced through the ``RateLimited`` signal so callers can
back off rather than hammering the provider.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import StrEnum


class RateLimitScope(StrEnum):
    ORDERS = "ORDERS"
    QUOTES = "QUOTES"
    ACCOUNT = "ACCOUNT"
    AUTH = "AUTH"


@dataclass(frozen=True)
class RateLimitPolicy:
    """A single scope's limit (requests-per-second)."""

    scope: RateLimitScope
    requests_per_second: float
    burst: int = 1


class TokenBucket:
    """Simple token-bucket limiter (async, non-blocking)."""

    def __init__(self, rate_per_second: float, burst: int) -> None:
        self._rate = rate_per_second
        self._burst = max(1, burst)
        self._tokens = float(self._burst)
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        async with self._lock:
            now = time.monotonic()
            self._tokens = min(
                self._burst, self._tokens + (now - self._last) * self._rate
            )
            self._last = now
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            return False


@dataclass
class RateLimiter:
    """Collection of per-scope token buckets."""

    policies: dict[RateLimitScope, RateLimitPolicy] = field(default_factory=dict)
    _buckets: dict[RateLimitScope, TokenBucket] = field(default_factory=dict, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    def add(self, policy: RateLimitPolicy) -> None:
        self.policies[policy.scope] = policy
        self._buckets[policy.scope] = TokenBucket(
            policy.requests_per_second, policy.burst
        )

    async def check(self, scope: RateLimitScope) -> bool:
        bucket = self._buckets.get(scope)
        if bucket is None:
            return True  # no policy -> no limit
        return await bucket.acquire()

    async def throttle(self, scope: RateLimitScope) -> None:
        """Block until a token is available for ``scope``."""
        bucket = self._buckets.get(scope)
        if bucket is None:
            return
        while not await bucket.acquire():
            await asyncio.sleep(0.05)
