"""API observability wiring (Phase 20).

Thin, provider-neutral instrumentation for the FastAPI surface: request
metrics, latency histograms, auth/permission/rate-limit counters, active
connection gauges, and trading-safety health. All metrics use **bounded**
labels (method, status class, failure class) — never raw paths, user ids,
order ids, or timestamps (Phase 20 §13, §37).

This module never changes trading behavior; it only records.
"""

from __future__ import annotations

from alpha_algo_observability import (
    FailureClass,
    get_health_registry,
    get_metrics,
)

_SERVICE = "alpha-algo-api"


def api_metrics():
    m = get_metrics()
    return {
        "requests_total": m.counter(
            "api_requests_total", "HTTP requests received", labels=("method",)
        ),
        "requests_by_status": m.counter(
            "api_requests_by_status_total", "HTTP responses by status class",
            labels=("status_class",),
        ),
        "request_latency": m.histogram(
            "api_request_latency_seconds", "HTTP request latency (seconds)"
        ),
        "auth_failures": m.counter(
            "api_auth_failures_total", "Authentication/authorization failures",
            labels=("failure_class",),
        ),
        "rate_limit_events": m.counter(
            "api_rate_limit_events_total", "Rate-limit rejections"
        ),
        "active_http": m.gauge("api_active_http_connections", "In-flight HTTP requests"),
        "active_ws": m.gauge("api_active_ws_connections", "Open WebSocket connections"),
    }


def _status_class(status_code: int) -> str:
    return f"{status_code // 100}xx"


def record_http_request(method: str, status_code: int, duration_s: float) -> None:
    m = api_metrics()
    m["requests_total"].inc(labels={"method": method})
    m["requests_by_status"].inc(labels={"status_class": _status_class(status_code)})
    m["request_latency"].observe(duration_s)


def record_auth_failure(failure_class: FailureClass) -> None:
    api_metrics()["auth_failures"].inc(labels={"failure_class": failure_class.value})


def record_permission_failure() -> None:
    record_auth_failure(FailureClass.AUTHORIZATION_FAILURE)


def record_rate_limit_event() -> None:
    api_metrics()["rate_limit_events"].inc()


def record_http_start() -> None:
    api_metrics()["active_http"].inc()


def record_http_end() -> None:
    api_metrics()["active_http"].dec()


def record_ws_connect() -> None:
    api_metrics()["active_ws"].inc()


def record_ws_disconnect() -> None:
    api_metrics()["active_ws"].dec()


def register_trading_safety_health(*, live_enabled: bool, global_halt: bool) -> None:
    """Expose read-only trading-safety facts (never mutates trading state)."""
    get_health_registry().set_trading_safety(
        LIVE_TRADING_ENABLED=live_enabled,
        GLOBAL_TRADING_HALT=global_halt,
    )
