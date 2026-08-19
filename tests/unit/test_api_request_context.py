from __future__ import annotations

import logging

from fastapi.testclient import TestClient

from alpha_algo_api import create_app


def test_request_id_header_is_generated_and_exposed() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/system/request-id")

    assert response.status_code == 200
    assert response.headers["x-request-id"].startswith("req_")
    assert response.json()["request_id"] == response.headers["x-request-id"]


def test_request_id_header_is_preserved() -> None:
    client = TestClient(create_app())

    response = client.get(
        "/api/v1/system/request-id",
        headers={"x-request-id": "req_test_123"},
    )

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req_test_123"
    assert response.json()["request_id"] == "req_test_123"


def test_not_found_uses_structured_error_shape() -> None:
    client = TestClient(create_app())

    response = client.get(
        "/api/v1/system/missing",
        headers={"x-request-id": "req_missing"},
    )

    assert response.status_code == 404
    assert response.headers["x-request-id"] == "req_missing"
    assert response.json() == {
        "error": {
            "code": "HTTP_ERROR",
            "message": "Not Found",
            "request_id": "req_missing",
            "details": {},
        },
    }


def test_request_logging_includes_request_context(caplog) -> None:
    client = TestClient(create_app())

    with caplog.at_level(logging.INFO, logger="alpha_algo_api.requests"):
        response = client.get(
            "/api/v1/system/health",
            headers={"x-request-id": "req_logged"},
        )

    assert response.status_code == 200
    records = [record for record in caplog.records if record.name == "alpha_algo_api.requests"]
    assert records
    assert records[-1].event == "request_completed"
    assert records[-1].request_id == "req_logged"
    assert records[-1].path == "/api/v1/system/health"
    assert records[-1].status_code == 200

