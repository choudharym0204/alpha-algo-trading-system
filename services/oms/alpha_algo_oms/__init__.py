"""Alpha Algo Order Management System (Phase 8) - public exports."""

from alpha_algo_oms.boundary import (
    ExecutionBoundary,
    ExecutionPort,
    NoOpExecutionPort,
    SubmissionHandoff,
)
from alpha_algo_oms.errors import (
    DuplicateOrderError,
    IntentConflictError,
    InvalidStateTransitionError,
    OmsError,
    OrderNotFoundError,
    OrderValidationError,
    PersistenceError,
    RiskApprovalError,
    TradingModeError,
)
from alpha_algo_oms.identity import (
    OrderIdentity,
    build_order_identity,
    compute_order_identity_key,
    make_client_order_id,
)
from alpha_algo_oms.metrics import OmsMetrics
from alpha_algo_oms.repository import (
    OUTCOME_CREATED,
    OUTCOME_DUPLICATE,
    OrderRepository,
    to_orm_event,
    to_orm_order,
)
from alpha_algo_oms.service import OmsService, OrderResult
from alpha_algo_oms.validation import (
    ALLOWED_ACTIONS,
    ALLOWED_MODES,
    ALLOWED_ORDER_TYPES,
    OrderSpec,
    validate_intent,
)

__all__ = [
    # service
    "OmsService",
    "OrderResult",
    # validation
    "OrderSpec",
    "validate_intent",
    "ALLOWED_MODES",
    "ALLOWED_ACTIONS",
    "ALLOWED_ORDER_TYPES",
    # identity
    "OrderIdentity",
    "build_order_identity",
    "compute_order_identity_key",
    "make_client_order_id",
    # repository
    "OrderRepository",
    "to_orm_order",
    "to_orm_event",
    "OUTCOME_CREATED",
    "OUTCOME_DUPLICATE",
    # boundary
    "ExecutionBoundary",
    "ExecutionPort",
    "NoOpExecutionPort",
    "SubmissionHandoff",
    # metrics
    "OmsMetrics",
    # errors
    "OmsError",
    "OrderValidationError",
    "OrderNotFoundError",
    "DuplicateOrderError",
    "IntentConflictError",
    "RiskApprovalError",
    "TradingModeError",
    "InvalidStateTransitionError",
    "PersistenceError",
]
