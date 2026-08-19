"""Alpha Algo Signal Engine (Phase 5) — public exports."""

from alpha_algo_signal_engine.boundary import (
    RuntimeStrategyDirectory,
    build_signal_engine,
    connect_strategy_runtime,
)
from alpha_algo_signal_engine.directory import StrategyDirectory, StrategyRecord
from alpha_algo_signal_engine.errors import (
    SignalConflictError,
    SignalEngineError,
    SignalPersistenceError,
    SignalRejectedError,
    TradingModeError,
)
from alpha_algo_signal_engine.idempotency import SignalIdempotency
from alpha_algo_signal_engine.identity import (
    compute_signal_content_hash,
    compute_signal_identity_key,
)
from alpha_algo_signal_engine.metrics import SignalMetrics
from alpha_algo_signal_engine.repository import (
    SignalRepository,
    to_orm_signal,
)
from alpha_algo_signal_engine.service import (
    SignalEngine,
    SignalIngestResult,
    SignalRecord,
)
from alpha_algo_signal_engine.state import SignalState, SignalStateMachine
from alpha_algo_signal_engine.validation import SignalIngestionValidator

__all__ = [
    "SignalEngine",
    "SignalIngestResult",
    "SignalRecord",
    "SignalState",
    "SignalStateMachine",
    "SignalIngestionValidator",
    "SignalIdempotency",
    "SignalRepository",
    "to_orm_signal",
    "SignalMetrics",
    "StrategyDirectory",
    "StrategyRecord",
    "RuntimeStrategyDirectory",
    "build_signal_engine",
    "connect_strategy_runtime",
    "compute_signal_identity_key",
    "compute_signal_content_hash",
    "SignalEngineError",
    "SignalRejectedError",
    "SignalConflictError",
    "SignalPersistenceError",
    "TradingModeError",
]
