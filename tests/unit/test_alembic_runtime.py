from __future__ import annotations

from pathlib import Path

from alpha_algo_shared.db import Base
from migrations.runtime import DEFAULT_SQLALCHEMY_URL, build_sqlalchemy_url, target_metadata


def test_alembic_runtime_uses_shared_metadata() -> None:
    assert target_metadata is Base.metadata


def test_alembic_runtime_prefers_explicit_and_env_urls(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://env-user@localhost/db")

    assert build_sqlalchemy_url("postgresql+psycopg://explicit@localhost/db") == "postgresql+psycopg://explicit@localhost/db"
    assert build_sqlalchemy_url() == "postgresql+psycopg://env-user@localhost/db"

    monkeypatch.delenv("DATABASE_URL")
    assert build_sqlalchemy_url() == DEFAULT_SQLALCHEMY_URL


def test_alembic_ini_exists() -> None:
    assert Path("alembic.ini").exists()

