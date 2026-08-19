from __future__ import annotations

import pytest
from sqlalchemy.exc import OperationalError

import alpha_algo_api.db as db
from alpha_algo_api.errors import DatabaseUnavailableError


def test_ping_database_true_when_reachable(monkeypatch) -> None:
    monkeypatch.setattr(db, "_probe", lambda timeout_seconds=None: None)
    assert db.ping_database() is True


def test_ping_database_false_when_unreachable(monkeypatch) -> None:
    def boom(timeout_seconds=None):
        raise OperationalError("SELECT 1", {}, Exception("down"))

    monkeypatch.setattr(db, "_probe", boom)
    assert db.ping_database() is False


def test_check_database_connection_raises(monkeypatch) -> None:
    def boom(timeout_seconds=None):
        raise OperationalError("SELECT 1", {}, Exception("down"))

    monkeypatch.setattr(db, "_probe", boom)
    with pytest.raises(DatabaseUnavailableError):
        db.check_database_connection()


def test_verify_database_ready_wraps_failure(monkeypatch) -> None:
    def boom(timeout_seconds=None):
        raise OperationalError("SELECT 1", {}, Exception("down"))

    monkeypatch.setattr(db, "_probe", boom)
    with pytest.raises(DatabaseUnavailableError):
        db.verify_database_ready()


def test_probe_uses_bounded_dedicated_engine(monkeypatch) -> None:
    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, stmt):
            return None

    made = {}

    class FakeEngine:
        def __init__(self):
            self.disposed = False

        def connect(self):
            return FakeConnection()

        def dispose(self):
            self.disposed = True

    captured: dict = {}

    def fake_create_engine(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        made["engine"] = FakeEngine()
        return made["engine"]

    monkeypatch.setattr(db, "create_engine", fake_create_engine)
    db._probe(timeout_seconds=3)
    assert captured["connect_args"]["connect_timeout"] == 3
    assert made["engine"].disposed is True
