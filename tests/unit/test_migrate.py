from __future__ import annotations

from pathlib import Path

from migrations.runtime import DEFAULT_SQLALCHEMY_URL, build_sqlalchemy_url


def test_migrate_script_exists() -> None:
    assert Path("scripts/migrate.py").exists()


def test_migrate_script_is_syntactically_valid() -> None:
    source = Path("scripts/migrate.py").read_text(encoding="utf-8")
    compile(source, "scripts/migrate.py", "exec")


def test_migrate_script_bootstraps_sys_path_and_dotenv() -> None:
    source = Path("scripts/migrate.py").read_text(encoding="utf-8")
    assert "load_dotenv" in source
    assert "alembic" in source


def test_build_sqlalchemy_url_still_works(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert build_sqlalchemy_url() == DEFAULT_SQLALCHEMY_URL
    assert (
        build_sqlalchemy_url("postgresql+psycopg://x@h/db")
        == "postgresql+psycopg://x@h/db"
    )
