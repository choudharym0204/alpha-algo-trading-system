from __future__ import annotations

import pytest

from alpha_algo_api.config import Settings


def test_db_runtime_defaults_are_safe() -> None:
    s = Settings(_env_file=None)
    assert s.db_pool_size == 5
    assert s.db_max_overflow == 10
    assert s.db_pool_timeout == 30
    assert s.db_pool_recycle == 1800
    assert s.db_pool_pre_ping is True
    assert s.db_echo is False
    assert s.db_connect_timeout == 5
    assert s.db_statement_timeout_ms == 30000
    assert s.db_startup_check_enabled is True
    assert s.db_retry_attempts == 3
    assert s.db_dispose_on_shutdown is True


def test_production_rejects_placeholder_database_url() -> None:
    with pytest.raises(ValueError, match="DATABASE_URL"):
        Settings(
            _env_file=None,
            app_env="production",
            secret_key="x" * 40,
            credential_encryption_key="y" * 40,
            database_url=(
                "postgresql+psycopg://u:replace-with-local-dev-password@localhost/db"
            ),
        )


def test_production_accepts_real_database_url() -> None:
    s = Settings(
        _env_file=None,
        app_env="production",
        secret_key="x" * 40,
        credential_encryption_key="y" * 40,
        database_url="postgresql+psycopg://u:realpass@localhost/db",
    )
    assert s.database_url == "postgresql+psycopg://u:realpass@localhost/db"


def test_pool_size_must_be_positive() -> None:
    with pytest.raises(ValueError, match="db_pool_size"):
        Settings(_env_file=None, db_pool_size=0)


def test_statement_timeout_must_be_non_negative() -> None:
    with pytest.raises(ValueError, match="db_statement_timeout_ms"):
        Settings(_env_file=None, db_statement_timeout_ms=-1)


def test_retry_attempts_must_be_positive() -> None:
    with pytest.raises(ValueError, match="db_retry_attempts"):
        Settings(_env_file=None, db_retry_attempts=0)
