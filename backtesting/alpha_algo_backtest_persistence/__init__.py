"""Backtest persistence and result caching (P16) — optional outer layer.

Deterministic run identity (canonical SHA-256, wall-clock excluded) plus a
stable JSON record format and an in-memory store with duplicate/conflict
semantics. The core backtest remains a pure deterministic computation that
never depends on this package.

Safety boundaries: no database, no network, no broker, no live data, no
secret handling; serialization is plain and auditable.
"""

from alpha_algo_backtest_persistence.errors import PersistenceError
from alpha_algo_backtest_persistence.identity import (
    IDENTITY_POLICY,
    SIMULATOR_VERSION,
    BacktestRunIdentity,
    identity_sha256,
    run_id_for_identity,
)
from alpha_algo_backtest_persistence.store import (
    PERSISTENCE_POLICY,
    BacktestRecord,
    BacktestStatus,
    BacktestStore,
    InMemoryBacktestStore,
    cache_key_for_identity,
)

__all__ = [
    "IDENTITY_POLICY",
    "PERSISTENCE_POLICY",
    "SIMULATOR_VERSION",
    "BacktestRecord",
    "BacktestRunIdentity",
    "BacktestStatus",
    "BacktestStore",
    "InMemoryBacktestStore",
    "PersistenceError",
    "cache_key_for_identity",
    "identity_sha256",
    "run_id_for_identity",
]
