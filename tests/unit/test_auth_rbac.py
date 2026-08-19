from __future__ import annotations

from fastapi.testclient import TestClient

from alpha_algo_api import create_app
from alpha_algo_api.auth import Permissions, issue_access_token


def _token(permissions: list[str]) -> str:
    return issue_access_token("test-user", permissions)


def test_auth_me_fails_closed_without_token() -> None:
    client = TestClient(create_app())

    response = client.get(
        "/api/v1/auth/me",
        headers={"x-request-id": "req_auth_missing"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "AUTH_REQUIRED",
            "message": "Authentication required.",
            "request_id": "req_auth_missing",
            "details": {},
        },
    }


def test_auth_me_rejects_invalid_token() -> None:
    client = TestClient(create_app())

    response = client.get(
        "/api/v1/auth/me",
        headers={
            "authorization": "Bearer bogus.token.value",
            "x-request-id": "req_auth_invalid",
        },
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_INVALID"
    assert response.json()["error"]["request_id"] == "req_auth_invalid"


def test_auth_me_rejects_tampered_token() -> None:
    client = TestClient(create_app())

    token = _token([Permissions.SYSTEM_READ])
    head, _payload, _sig = token.split(".")
    tampered = f"{head}.{'A' * 40}.{'B' * 43}"

    response = client.get(
        "/api/v1/auth/me",
        headers={"authorization": f"Bearer {tampered}"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_INVALID"


def test_auth_me_returns_permissions_from_token() -> None:
    client = TestClient(create_app())

    token = _token([Permissions.SYSTEM_READ, Permissions.TRADING_VIEW])
    response = client.get(
        "/api/v1/auth/me",
        headers={
            "authorization": f"Bearer {token}",
            "x-request-id": "req_auth_ok",
        },
    )

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req_auth_ok"
    assert response.json() == {
        "subject": "test-user",
        "permissions": ["system:read", "trading:view"],
    }


def test_require_permission_enforces_rbac() -> None:
    client = TestClient(create_app())

    # Token lacks SYSTEM_READ, which /auth/me requires.
    token = _token([Permissions.TRADING_VIEW])
    response = client.get(
        "/api/v1/auth/me",
        headers={"authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
