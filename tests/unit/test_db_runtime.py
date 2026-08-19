from __future__ import annotations

import pytest

import alpha_algo_api.db as db
from alpha_algo_api.config import Settings, reset_settings


@pytest.fixture(autouse=True)
def _clean():
    reset_settings()
    db._engine = None
    db._session_factory = None
    yield
    db._engine = None
    db._session_factory = None


def test_engine_is_lazy_and_configured(monkeypatch) -> None:
    captured: dict = {}

    def fake_create_engine(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(db, "create_engine", fake_create_engine)
    engine = db.get_engine()
    assert engine is not None
    assert captured["pool_size"] == 5
    assert captured["max_overflow"] == 10
    assert captured["pool_timeout"] == 30
    assert captured["pool_recycle"] == 1800
    assert captured["pool_pre_ping"] is True
    assert captured["echo"] is False
    assert captured["future"] is True
    assert captured["connect_args"]["connect_timeout"] == 5
    assert "statement_timeout=30000" in captured["connect_args"]["options"]


def test_engine_is_singleton(monkeypatch) -> None:
    monkeypatch.setattr(db, "create_engine", lambda *a, **k: object())
    assert db.get_engine() is db.get_engine()


def test_dispose_engine_releases_and_resets(monkeypatch) -> None:
    calls = {"disposed": 0}

    class FakeEngine:
        def dispose(self) -> None:
            calls["disposed"] += 1

    db._engine = FakeEngine()
    db._session_factory = object()
    db.dispose_engine()
    assert calls["disposed"] == 1
    assert db._engine is None
    assert db._session_factory is None


def test_statement_timeout_omitted_when_zero(monkeypatch) -> None:
    monkeypatch.setattr(
        db,
        "get_settings",
        lambda: Settings(_env_file=None, db_statement_timeout_ms=0),
    )
    captured: dict = {}
    monkeypatch.setattr(db, "create_engine", lambda url, **kw: captured.update(kw) or object())
    db.get_engine()
    assert "options" not in captured["connect_args"]
