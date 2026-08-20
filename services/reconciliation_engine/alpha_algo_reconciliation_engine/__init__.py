"""Alpha Algo Reconciliation Engine (Phase 14).

Durable, deterministic, auditable comparison of internal authoritative state
against broker observations. Classifies matches vs. discrepancies, persists
evidence, and produces controlled recovery actions — never silently overwrites
internal financial truth. No broker SDK, LIVE fail-closed.
"""

from alpha_algo_reconciliation_engine.contracts import (
    Discrepancy,
    DiscrepancyKind,
    EntityType,
    ExecutionObservation,
    FundsObservation,
    ObservationStatus,
    OrderObservation,
    PositionObservation,
    ReconciliationInputs,
    ReconciliationRun,
    ReconciliationScope,
    RecoveryAction,
    ResolutionStatus,
    RunResult,
    RunStatus,
    Severity,
)
from alpha_algo_reconciliation_engine.engine import (
    ReconciliationEngine,
    ReconciliationRepository,
)
from alpha_algo_reconciliation_engine.errors import (
    DiscrepancyConflictError,
    DuplicateDiscrepancyError,
    ReconciliationDataError,
    ReconciliationError,
    ReconciliationModeError,
    ReconciliationPersistenceError,
    ReconciliationValidationError,
)
from alpha_algo_reconciliation_engine.identity import (
    compute_discrepancy_key,
    discrepancy_content_hash,
)
from alpha_algo_reconciliation_engine.matching import (
    MatchContext,
    reconcile_executions,
    reconcile_funds,
    reconcile_orders,
    reconcile_positions,
)
from alpha_algo_reconciliation_engine.metrics import ReconciliationMetrics
from alpha_algo_reconciliation_engine.tolerance import Tolerance, within

__all__ = [
    "Discrepancy",
    "DiscrepancyConflictError",
    "DiscrepancyKind",
    "DuplicateDiscrepancyError",
    "EntityType",
    "ExecutionObservation",
    "FundsObservation",
    "MatchContext",
    "ObservationStatus",
    "OrderObservation",
    "PositionObservation",
    "ReconciliationDataError",
    "ReconciliationEngine",
    "ReconciliationError",
    "ReconciliationInputs",
    "ReconciliationMetrics",
    "ReconciliationModeError",
    "ReconciliationPersistenceError",
    "ReconciliationRepository",
    "ReconciliationRun",
    "ReconciliationScope",
    "ReconciliationValidationError",
    "RecoveryAction",
    "ResolutionStatus",
    "RunResult",
    "RunStatus",
    "Severity",
    "Tolerance",
    "compute_discrepancy_key",
    "discrepancy_content_hash",
    "reconcile_executions",
    "reconcile_funds",
    "reconcile_orders",
    "reconcile_positions",
    "within",
]
