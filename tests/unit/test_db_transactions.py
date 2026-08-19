from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

import alpha_algo_api.db as db
from alpha_algo_api.config import reset_settings


@pytest.fixture(autouse=True)
def _clean():
    reset_settings()
    db._engine = None
    db._session_factory = None
    yield
    db._engine = None
    db._session_factory = None


def _sqlite_session_factory():
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)"))
    return engine, sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )


def test_session_scope_commits_on_success(monkeypatch) -> None:
    engine, factory = _sqlite_session_factory()
    monkeypatch.setattr(db, "_session_factory", factory)
    with db.session_scope() as session:
        session.execute(text("INSERT INTO t (name) VALUES ('a')"))
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM t")).scalar() == 1


def test_session_scope_rolls_back_on_error(monkeypatch) -> None:
    engine, factory = _sqlite_session_factory()
    monkeypatch.setattr(db, "_session_factory", factory)
    with pytest.raises(RuntimeError):
        with db.session_scope() as session:
            session.execute(text("INSERT INTO t (name) VALUES ('a')"))
            raise RuntimeError("boom")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM t")).scalar() == 0


def test_session_scope_rolls_back_when_commit_raises(monkeypatch) -> None:
    session = MagicMock()
    session.commit.side_effect = OperationalError("COMMIT", {}, Exception("boom"))
    factory = MagicMock(return_value=session)
    monkeypatch.setattr(db, "_session_factory", factory)
    with pytest.raises(OperationalError):
        with db.session_scope():
            pass
    session.rollback.assert_called_once()
    session.close.assert_called_once()


def test_get_db_yields_session_and_closes(monkeypatch) -> None:
    _, factory = _sqlite_session_factory()
    monkeypatch.setattr(db, "_session_factory", factory)
    gen = db.get_db()
    session = next(gen)
    assert isinstance(session, Session)
    gen.close()  # triggers the finally -> session.close()
