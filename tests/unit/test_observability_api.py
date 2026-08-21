"""API observability tests (Phase 20 §54–§59, §68).

Verifies request metrics, auth/permission/rate-limit counters, trace
propagation, and the read-only observability endpoint (gated by ``system:read``
and reflecting LIVE-disabled / HALT-enabled trading safety).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from alpha_algo_api import create_app
from alpha_algo_api.auth import Permissions, issue_access_token
from alpha_algo_api.config import reset_settings
from alpha_algo_api.rate_limit import reset_rate_limit_state
from alpha_algo_observability import get_metrics, get_trace_context, reset_metrics, reset_trace_context


@pytest.fixture(autouse=True)
def _reset_observability():
    reset_metrics()
    reset_trace_context()
    reset_settings()
    reset_rate_limit_state()
    yield
    reset_metrics()
    reset_trace_context()
    reset_settings()
    reset_rate_limit_state()


def _token(permissions: list[str]) -> str:
    return issue_access_token(subject="e2e-user", permissions=permissions)


def _metric_samples(metric_name: str) -> list[dict]:
    snap = get_metrics().snapshot()
    return snap.get(metric_name, {}).get("samples", [])


def test_request_records_metrics() -> None:
    client = TestClient(create_app())
    assert client.get("/api/v1/system/health").status_code == 200

    assert len(_metric_samples("api_requests_total")) >= 1
    assert len(_metric_samples("api_requests_by_status_total")) >= 1
    assert len(_metric_samples("api_request_latency_seconds")) >= 1
    # status class is bounded (2xx), never a raw path or id
    status_samples = _metric_samples("api_requests_by_status_total")
    assert any(s["labels"]["status_class"] == "2xx" for s in status_samples)


def test_auth_failure_metric_recorded() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/system/observability")
    assert response.status_code == 401

    samples = _metric_samples("api_auth_failures_total")
    assert any(s["labels"]["failure_class"] == "AUTHENTICATION_FAILURE" for s in samples)


def test_permission_failure_metric_recorded() -> None:
    client = TestClient(create_app())
    token = _token([Permissions.TRADING_VIEW])  # no system:read
    response = client.get(
        "/api/v1/system/observability",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403

    samples = _metric_samples("api_auth_failures_total")
    assert any(s["labels"]["failure_class"] == "AUTHORIZATION_FAILURE" for s in samples)


def test_observability_endpoint_gated_and_reads_safety() -> None:
    client = TestClient(create_app())
    token = _token([Permissions.SYSTEM_READ])
    response = client.get(
        "/api/v1/system/observability",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()
    # LIVE remains disabled, global halt remains true (fail-closed observation).
    assert payload["trading_safety"]["live_trading_enabled"] is False
    assert payload["trading_safety"]["global_trading_halt"] is True
    assert "metrics" in payload
    assert "health" in payload
    assert "alerts" in payload


def test_rate_limit_event_metric_recorded(monkeypatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_REQUESTS_PER_MINUTE", "2")
    reset_settings()
    reset_rate_limit_state()
    client = TestClient(create_app())

    assert client.get("/api/v1/system/health").status_code == 200
    assert client.get("/api/v1/system/health").status_code == 200
    assert client.get("/api/v1/system/health").status_code == 429

    samples = _metric_samples("api_rate_limit_events_total")
    assert len(samples) >= 1


def test_traceparent_propagates_trace_id() -> None:
    client = TestClient(create_app())
    traceparent = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    response = client.get(
        "/api/v1/system/health",
        headers={"traceparent": traceparent},
    )
    assert response.status_code == 200

    spans = get_trace_context().store.spans()
    assert spans
    assert spans[0]["trace_id"] == "4bf92f3577b34da6a3ce929d0e0e4736"
