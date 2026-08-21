"""Structured logging with secret redaction (Phase 20 §6, §7, §38).

A thin wrapper over :mod:`logging` that emits a stable set of structured fields
(``extra``) so downstream backends can index them. It never logs credentials or
other sensitive values; ``redact`` strips/overwrites known-sensitive keys and
values before a record is emitted.
"""

from __future__ import annotations

import logging
from typing import Any

__all__ = [
    "StructuredLogger",
    "redact",
    "SENSITIVE_KEY_PARTS",
    "get_structured_logger",
    "reset_structured_loggers",
]

# Case-insensitive key fragments that are always treated as sensitive.
SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "private_key",
    "refresh",
    "cookie",
    "session_id",
)

_REDACTED = "[REDACTED]"


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def redact(value: Any, *, key: str | None = None) -> Any:
    """Return a safe copy of ``value`` for logging.

    * If ``key`` looks sensitive, the whole value is redacted.
    * Dictionaries and lists are walked recursively so nested secrets are caught.
    * Long strings are not truncated here (cardinality is a separate concern).
    """
    if key is not None and _is_sensitive_key(key):
        return _REDACTED
    if isinstance(value, dict):
        return {k: redact(v, key=k) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    return value


def _sanitize_fields(fields: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in fields.items():
        if _is_sensitive_key(key):
            out[key] = _REDACTED
        else:
            out[key] = redact(value)
    return out


class StructuredLogger:
    """Logger that emits structured, redacted records via stdlib ``extra``."""

    def __init__(self, logger: logging.Logger, *, service: str = "", default_fields: dict[str, Any] | None = None) -> None:
        self._logger = logger
        self.service = service
        self.default_fields = default_fields or {}

    def _emit(self, level: int, event: str, message: str, **fields: Any) -> None:
        payload: dict[str, Any] = dict(self.default_fields)
        payload.update(fields)
        if self.service:
            payload.setdefault("service", self.service)
        payload["event"] = event
        payload = _sanitize_fields(payload)
        self._logger.log(level, message, extra={"structured": payload})

    def debug(self, event: str, message: str = "", **fields: Any) -> None:
        self._emit(logging.DEBUG, event, message, **fields)

    def info(self, event: str, message: str = "", **fields: Any) -> None:
        self._emit(logging.INFO, event, message, **fields)

    def warning(self, event: str, message: str = "", **fields: Any) -> None:
        self._emit(logging.WARNING, event, message, **fields)

    def error(self, event: str, message: str = "", **fields: Any) -> None:
        self._emit(logging.ERROR, event, message, **fields)

    def critical(self, event: str, message: str = "", **fields: Any) -> None:
        self._emit(logging.CRITICAL, event, message, **fields)


_LOGGER_CACHE: dict[str, StructuredLogger] = {}


def get_structured_logger(name: str, *, service: str = "", default_fields: dict[str, Any] | None = None) -> StructuredLogger:
    """Return (and cache) a structured logger for ``name``."""
    if name in _LOGGER_CACHE:
        return _LOGGER_CACHE[name]
    structured = StructuredLogger(logging.getLogger(name), service=service, default_fields=default_fields)
    _LOGGER_CACHE[name] = structured
    return structured


def reset_structured_loggers() -> None:
    _LOGGER_CACHE.clear()
