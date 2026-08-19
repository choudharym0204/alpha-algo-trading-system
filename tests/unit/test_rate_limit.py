from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from alpha_algo_api import create_app
from alpha_algo_api.config import reset_settings
from alpha_algo_api.rate_limit import SlidingWindowRateLimiter, reset_rate_limit_state


@pytest.fixture(autouse=True)
def _reset_settings(monkeypatch):
    reset_settings()
    reset_rate_limit_state()
    yield
    reset_settings()
    reset_rate_limit_state()


def test_limiter_allows_up_to_limit() -> None:
    limiter = SlidingWindowRateLimiter(limit=3)
    assert limiter.allow("ip:1") is True
    assert limiter.allow("ip:1") is True
    assert limiter.allow("ip:1") is True
    assert limiter.allow("ip:1") is False


def test_limiter_keys_are_isolated() -> None:
    limiter = SlidingWindowRateLimiter(limit=1)
    assert limiter.allow("ip:1") is True
    assert limiter.allow("ip:2") is True
    assert limiter.allow("ip:1") is False


def test_rate_limit_disabled_is_noop(monkeypatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    reset_settings()
    reset_rate_limit_state()
    client = TestClient(create_app())
    for _ in range(5):
        assert client.get("/api/v1/system/health").status_code == 200


def test_rate_limit_returns_429_after_limit(monkeypatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_REQUESTS_PER_MINUTE", "2")
    reset_settings()
    reset_rate_limit_state()
    client = TestClient(create_app())

    assert client.get("/api/v1/system/health").status_code == 200
    assert client.get("/api/v1/system/health").status_code == 200
    response = client.get("/api/v1/system/health")

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMITED"
    assert response.headers["x-request-id"]
