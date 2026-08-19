from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from alpha_algo_api import create_app
from alpha_algo_api.auth import issue_access_token, issue_refresh_token
from alpha_algo_api.config import get_settings
from alpha_algo_api.db import get_db
from alpha_algo_api.security.password import hash_password
from alpha_algo_api.security.tokens import decode_token


class _FakeUser:
    def __init__(self, user_id, email, password_hash, is_active=True):
        self.id = user_id
        self.email = email
        self.password_hash = password_hash
        self.is_active = is_active


def _client_with_user(email="a@b.com", password="secret-password", perms=None, is_active=True):
    user_id = uuid4()
    user = _FakeUser(user_id, email, hash_password(password), is_active)
    session = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = user
    session.execute.return_value.scalars.return_value.all.return_value = perms or ["system:read"]

    app = create_app()

    def fake_get_db():
        yield session

    app.dependency_overrides[get_db] = fake_get_db
    return TestClient(app), user_id


def test_login_success_returns_valid_tokens() -> None:
    client, user_id = _client_with_user(perms=["system:read", "trading:view"])

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "a@b.com", "password": "secret-password"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0

    settings = get_settings()
    access = decode_token(
        body["access_token"],
        secret=settings.secret_key,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        expected_type="access",
    )
    assert access.subject == str(user_id)
    assert access.permissions == frozenset({"system:read", "trading:view"})

    decode_token(
        body["refresh_token"],
        secret=settings.secret_key,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        expected_type="refresh",
    )


def test_login_wrong_password_rejected() -> None:
    client, _ = _client_with_user(password="correct-password")

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "a@b.com", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_INVALID_CREDENTIALS"


def test_login_unknown_email_rejected() -> None:
    session = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = None
    app = create_app()

    def fake_get_db():
        yield session

    app.dependency_overrides[get_db] = fake_get_db
    client = TestClient(app)

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@b.com", "password": "whatever"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_INVALID_CREDENTIALS"


def test_login_disabled_account_rejected() -> None:
    client, _ = _client_with_user(is_active=False)

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "a@b.com", "password": "secret-password"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AUTH_DISABLED"


def test_refresh_issues_new_tokens() -> None:
    refresh_token = issue_refresh_token("user-9", ["system:read"])
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    settings = get_settings()
    access = decode_token(
        body["access_token"],
        secret=settings.secret_key,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        expected_type="access",
    )
    assert access.subject == "user-9"
    assert access.permissions == frozenset({"system:read"})


def test_refresh_rejects_access_token() -> None:
    access_token = issue_access_token("user-9", ["system:read"])
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": access_token},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_INVALID"
