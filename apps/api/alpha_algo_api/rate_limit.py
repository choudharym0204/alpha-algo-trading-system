from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from threading import Lock

from fastapi import Request, Response

from alpha_algo_api.config import get_settings
from alpha_algo_api.errors import build_error_response
from alpha_algo_api.middleware import resolve_request_id
from alpha_algo_api.observability import record_rate_limit_event


class SlidingWindowRateLimiter:
    """Fixed-window sliding limiter keyed by a client string."""

    def __init__(self, *, limit: int, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()
        self._calls = 0

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            self._calls += 1
            if self._calls % 1024 == 0:
                self._sweep()

            window = self._hits[key]
            while window and now - window[0] >= self.window_seconds:
                window.popleft()
            if len(window) >= self.limit:
                return False
            window.append(now)
            return True

    def _sweep(self) -> None:
        """Drop empty windows to bound memory growth."""
        empty = [key for key, window in self._hits.items() if not window]
        for key in empty:
            del self._hits[key]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
            self._calls = 0


_limiter: SlidingWindowRateLimiter | None = None
_limiter_lock = Lock()


def _get_limiter() -> SlidingWindowRateLimiter:
    global _limiter
    if _limiter is None:
        with _limiter_lock:
            if _limiter is None:
                settings = get_settings()
                _limiter = SlidingWindowRateLimiter(
                    limit=settings.rate_limit_requests_per_minute,
                    window_seconds=60.0,
                )
    return _limiter


def reset_rate_limit_state() -> None:
    """Reset the module-level limiter (used by tests)."""
    global _limiter
    _limiter = None


def _client_key(request: Request) -> str:
    settings = get_settings()
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else "unknown"
    else:
        ip = request.client.host if request.client else "unknown"
    return f"ip:{ip}"


async def rate_limit_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    settings = get_settings()
    if not settings.rate_limit_enabled:
        return await call_next(request)

    request_id = getattr(request.state, "request_id", None)
    if request_id is None:
        request_id = resolve_request_id(request)
        request.state.request_id = request_id

    if not _get_limiter().allow(_client_key(request)):
        record_rate_limit_event()
        return build_error_response(
            code="RATE_LIMITED",
            message="Rate limit exceeded. Retry later.",
            request_id=request_id,
            status_code=429,
        )
    return await call_next(request)
