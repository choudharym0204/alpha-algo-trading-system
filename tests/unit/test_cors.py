from __future__ import annotations

from fastapi.testclient import TestClient

from alpha_algo_api import create_app


def test_cors_allows_configured_origin() -> None:
    client = TestClient(create_app())

    response = client.get(
        "/api/v1/system/health",
        headers={"origin": "http://localhost:3000"},
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_cors_rejects_unconfigured_origin() -> None:
    client = TestClient(create_app())

    response = client.get(
        "/api/v1/system/health",
        headers={"origin": "http://evil.example.com"},
    )

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_cors_headers_present_on_preflight() -> None:
    client = TestClient(create_app())

    response = client.options(
        "/api/v1/system/health",
        headers={
            "origin": "http://localhost:3000",
            "access-control-request-method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
