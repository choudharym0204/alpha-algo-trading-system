from __future__ import annotations

from fastapi.testclient import TestClient

from alpha_algo_api import create_app


def test_create_app_exposes_system_health_endpoint() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/system/health")

    assert response.status_code == 200
    assert response.json() == {
        "service": "alpha-algo-api",
        "status": "ok",
        "live_trading": "disabled",
    }


def test_readiness_endpoint_does_not_enable_trading() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/system/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["live_trading"] == "disabled"
    assert payload["checks"]["broker"] == "disabled"

