"""Typed errors for the backtesting persistence package (P16)."""

from __future__ import annotations

__all__ = ["PersistenceError"]


class PersistenceError(ValueError):
    """Raised for malformed or conflicting persistence operations.

    The persistence layer is an optional outer concern: the core backtest
    remains a pure computation and never depends on it. Save/load integrity
    violations, duplicate identity with conflicting payloads, and corrupted
    metadata raise here rather than silently overwriting.
    """
