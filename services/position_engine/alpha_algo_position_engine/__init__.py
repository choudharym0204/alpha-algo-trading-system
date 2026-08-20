"""Alpha Algo Position Engine (Phase 11).

Broker-independent, durable, authoritative position state built from normalized
execution/fill events. LONG-only, no short/flip, LIVE fail-closed.
"""

from alpha_algo_position_engine.arithmetic import (
    PRICE_QUANTUM,
    apply_buy,
    apply_sell,
    round_price,
    weighted_average,
)
from alpha_algo_position_engine.contracts import (
    PositionApplyStatus,
    PositionEventType,
    PositionFill,
    PositionIdentity,
    PositionResult,
    PositionSide,
    PositionSnapshot,
    PositionState,
    PositionStatus,
)
from alpha_algo_position_engine.engine import (
    PositionApplyPlan,
    PositionEngine,
    PositionEventData,
    PositionRepository,
)
from alpha_algo_position_engine.errors import (
    DuplicateApplyError,
    PositionConflictError,
    PositionError,
    PositionIdentityError,
    PositionModeError,
    PositionNotFoundError,
    PositionOverCloseError,
    PositionPersistenceError,
    PositionUnsupportedError,
    PositionValidationError,
)
from alpha_algo_position_engine.identity import (
    build_position_identity,
    compute_position_key,
    fill_content_hash,
    normalize_fill,
)
from alpha_algo_position_engine.metrics import PositionMetrics

__all__ = [
    "PRICE_QUANTUM",
    "PositionApplyPlan",
    "PositionApplyStatus",
    "PositionConflictError",
    "PositionEngine",
    "PositionError",
    "PositionEventData",
    "PositionEventType",
    "PositionFill",
    "PositionIdentity",
    "PositionIdentityError",
    "PositionMetrics",
    "PositionModeError",
    "PositionNotFoundError",
    "PositionOverCloseError",
    "PositionPersistenceError",
    "PositionRepository",
    "PositionResult",
    "PositionSide",
    "PositionSnapshot",
    "PositionState",
    "PositionStatus",
    "PositionUnsupportedError",
    "PositionValidationError",
    "DuplicateApplyError",
    "apply_buy",
    "apply_sell",
    "build_position_identity",
    "compute_position_key",
    "fill_content_hash",
    "normalize_fill",
    "round_price",
    "weighted_average",
]
