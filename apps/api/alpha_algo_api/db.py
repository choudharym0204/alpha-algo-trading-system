"""Database engine, session, transaction, retry, and health wiring (psycopg 3).

Phase 2 converts the schema/configuration-only foundation into a real runtime
database layer:

- lazy SQLAlchemy engine with connection pooling, connect timeout, and a
  server-side ``statement_timeout``;
- a ``sessionmaker``-based session factory + per-request ``get_db`` dependency;
- a ``session_scope`` unit-of-work context manager (COMMIT on success, ROLLBACK
  on error);
- a bounded reconnect/retry helper for transient connection failures;
- a ``ping_database`` health probe and a fail-fast ``verify_database_ready``
  startup check; and
- ``dispose_engine`` for clean shutdown.

The engine is created lazily so importing this module never opens a database
connection. Engine/factory creation and disposal are guarded by a lock so that
a shutdown disposal cannot race a concurrent lazy engine creation.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Generator, Iterator
from contextlib import contextmanager
from typing import Any, TypeVar

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from alpha_algo_api.config import get_settings
from alpha_algo_api.errors import DatabaseUnavailableError
from alpha_algo_shared.db import Base, TimestampMixin

__all__ = [
    "Base",
    "TimestampMixin",
    "get_engine",
    "get_session_factory",
    "get_db",
    "dispose_engine",
    "ping_database",
    "check_database_connection",
    "verify_database_ready",
    "session_scope",
    "run_with_retry",
    "DatabaseUnavailableError",
]

logger = logging.getLogger(__name__)

T = TypeVar("T")

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
# Reentrant: get_session_factory() calls get_engine() while holding the lock.
_lock = threading.RLock()


def _connect_args() -> dict[str, Any]:
    """Build psycopg3 connect args: connect timeout + server statement timeout."""
    settings = get_settings()
    args: dict[str, Any] = {"connect_timeout": settings.db_connect_timeout}
    if settings.db_statement_timeout_ms:
        args["options"] = f"-c statement_timeout={settings.db_statement_timeout_ms}"
    return args


def get_engine() -> Engine:
    """Return the (lazily created) SQLAlchemy engine. Does not connect on creation."""
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                settings = get_settings()
                _engine = create_engine(
                    settings.database_url,
                    pool_size=settings.db_pool_size,
                    max_overflow=settings.db_max_overflow,
                    pool_timeout=settings.db_pool_timeout,
                    pool_recycle=settings.db_pool_recycle,
                    pool_pre_ping=settings.db_pool_pre_ping,
                    echo=settings.db_echo,
                    future=True,
                    connect_args=_connect_args(),
                )
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Return the process-wide session factory."""
    global _session_factory
    if _session_factory is None:
        with _lock:
            if _session_factory is None:
                _session_factory = sessionmaker(
                    bind=get_engine(),
                    autoflush=False,
                    autocommit=False,
                    expire_on_commit=False,
                )
    return _session_factory


def dispose_engine() -> None:
    """Dispose the engine and release pooled connections (used on shutdown).

    Idempotent and safe to call more than once.
    """
    global _engine, _session_factory
    with _lock:
        if _engine is not None:
            _engine.dispose()
            _engine = None
        _session_factory = None


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a scoped session, closed on teardown.

    The session is closed (returned to the pool) in a ``finally`` block so that a
    leaked connection is never left open even if the handler raises.
    """
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Unit-of-work context manager: COMMIT on success, ROLLBACK on error.

    Usage::

        with session_scope() as session:
            session.add(order)
            session.add(event)

    If the block (or the final COMMIT) raises, the transaction is rolled back and
    the exception is re-raised; otherwise the transaction is committed. The
    session is always closed, so no connection leaks.
    """
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def run_with_retry(
    fn: Callable[..., T],
    *args: Any,
    attempts: int | None = None,
    delay_seconds: float | None = None,
    retryable: tuple[type[Exception], ...] = (OperationalError,),
    **kwargs: Any,
) -> T:
    """Run *fn* with bounded retry on transient connection errors.

    Retries ``db_retry_attempts`` times (at least once) with linear backoff
    (``delay_seconds * attempt``). Non-retryable exceptions propagate
    immediately; after the final attempt the last exception is re-raised.

    This helper is intended for idempotent, connection-level operations (health
    checks, connection establishment) — not for wrapping multi-statement
    transactions; use :func:`session_scope` for those.
    """
    settings = get_settings()
    attempts = settings.db_retry_attempts if attempts is None else attempts
    delay_seconds = settings.db_retry_delay_seconds if delay_seconds is None else delay_seconds
    attempts = max(1, attempts)

    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn(*args, **kwargs)
        except retryable as exc:  # noqa: PERF203 - deliberate retry loop
            last_exc = exc
            logger.warning(
                "database operation failed (attempt %d/%d): %s",
                attempt,
                attempts,
                exc,
            )
            if attempt < attempts:
                time.sleep(delay_seconds * attempt)
    raise last_exc  # type: ignore[misc]  # attempts >= 1 guarantees last_exc is set


def _probe(timeout_seconds: float | None = None) -> None:
    """Execute ``SELECT 1`` through a short-lived, bounded connection.

    Uses a dedicated NullPool engine with a hard ``connect_timeout`` so the probe
    never waits on the application pool and is guaranteed to return within
    ``timeout_seconds`` (or ``db_connect_timeout``).
    """
    settings = get_settings()
    connect_timeout = (
        settings.db_connect_timeout if timeout_seconds is None else timeout_seconds
    )
    probe_engine = create_engine(
        settings.database_url,
        poolclass=NullPool,
        connect_args={"connect_timeout": connect_timeout},
    )
    try:
        with probe_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    finally:
        probe_engine.dispose()


def ping_database(timeout_seconds: float | None = None) -> bool:
    """Return True when the database is reachable, False otherwise (never raises)."""
    try:
        _probe(timeout_seconds)
        return True
    except Exception as exc:  # noqa: BLE001 - health probe must never raise
        logger.warning("database ping failed: %s", exc)
        return False


def check_database_connection(timeout_seconds: float | None = None) -> None:
    """Raise ``DatabaseUnavailableError`` when the database is not reachable."""
    try:
        _probe(timeout_seconds)
    except Exception as exc:  # noqa: BLE001 - wrap in a controlled error
        raise DatabaseUnavailableError(str(exc)) from exc


def verify_database_ready() -> None:
    """Startup check: raise ``DatabaseUnavailableError`` when DB is unreachable."""
    settings = get_settings()
    check_database_connection(timeout_seconds=settings.db_startup_check_timeout_seconds)
    logger.info("database connection verified")
