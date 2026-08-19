from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from alpha_algo_api import create_app
from alpha_algo_api.config import reset_settings
from alpha_algo_api.errors import DatabaseUnavailableError


def test_ready_reports_database_ok(monkeypatch) -> None:
    monkeypatch.setattr("alpha_algo_api.routes.system.ping_database", lambda: True)
    client = TestClient(create_app())
    payload = client.get("/api/v1/system/ready").json()
    assert payload["checks"]["database"] == "ok"
    assert payload["status"] == "ready"
    assert payload["live_trading"] == "disabled"


def test_ready_reports_database_error(monkeypatch) -> None:
    monkeypatch.setattr("alpha_algo_api.routes.system.ping_database", lambda: False)
    client = TestClient(create_app())
    payload = client.get("/api/v1/system/ready").json()
    assert payload["checks"]["database"] == "error"


def test_database_unavailable_returns_503_envelope() -> None:
    app = create_app()

    @app.get("/boom-db")
    def boom_db() -> None:
        raise DatabaseUnavailableError("down with secret conn string")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/boom-db")
    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "DATABASE_UNAVAILABLE"
    assert body["error"]["message"] == "Database is unavailable."
    # connection details must never leak to the client
    assert "secret" not in response.text
    assert "conn" not in response.text


def test_lifespan_disposes_engine_on_shutdown(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DB_STARTUP_CHECK_ENABLED", "false")
    reset_settings()
    disposed = {"called": False}
    monkeypatch.setattr(
        "alpha_algo_api.main.dispose_engine",
        lambda: disposed.__setitem__("called", True),
    )
    with TestClient(create_app()):
        pass
    assert disposed["called"] is True


def test_lifespan_warns_and_continues_in_dev(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DB_STARTUP_CHECK_ENABLED", "true")
    reset_settings()

    def boom() -> None:
        raise DatabaseUnavailableError("down")

    monkeypatch.setattr("alpha_algo_api.main.verify_database_ready", boom)
    with TestClient(create_app()) as client:
        assert client.get("/api/v1/system/health").status_code == 200


def test_lifespan_fails_fast_in_production(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "a" * 40)
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", "b" * 40)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost/db")
    monkeypatch.setenv("DB_STARTUP_CHECK_ENABLED", "true")
    reset_settings()

    def boom() -> None:
        raise DatabaseUnavailableError("down")

    monkeypatch.setattr("alpha_algo_api.main.verify_database_ready", boom)
    with pytest.raises((DatabaseUnavailableError, BaseExceptionGroup)):
        with TestClient(create_app()):
            pass
