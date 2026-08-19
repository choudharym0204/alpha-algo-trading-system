"""Signal Engine errors."""

from __future__ import annotations


class SignalEngineError(Exception):
    """Base error for the signal engine."""


class SignalRejectedError(SignalEngineError):
    """A signal failed ingestion validation/filtering.

    ``reason`` is a stable machine-readable code (e.g. ``unknown_strategy``,
    ``config_hash_mismatch``) usable for filtering and metrics.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class TradingModeError(SignalEngineError):
    """A signal carries a disallowed trading mode (LIVE)."""


class SignalConflictError(SignalEngineError):
    """Same deterministic identity but different content — rejected, never overwritten."""


class SignalPersistenceError(SignalEngineError):
    """A signal could not be committed (DB failure) — no false SUCCESS."""
