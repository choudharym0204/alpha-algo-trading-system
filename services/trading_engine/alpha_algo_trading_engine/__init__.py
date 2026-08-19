"""Alpha Algo Trading Orchestrator (Phase 7) — public exports."""

from alpha_algo_trading_engine.boundary import (
    build_trading_orchestrator,
    connect_signal_engine,
)
from alpha_algo_trading_engine.identity import compute_orchestration_identity_key
from alpha_algo_trading_engine.intent import (
    OrderIntentResolver,
    TradingIntent,
    UnavailableOrderIntentResolver,
)
from alpha_algo_trading_engine.metrics import OrchestrationMetrics
from alpha_algo_trading_engine.oms_port import HandoffResult, NoOpOmsPort, OmsPort
from alpha_algo_trading_engine.repository import (
    TradingIntentRepository,
    to_orm_rejection,
    to_orm_trading_intent,
)
from alpha_algo_trading_engine.service import (
    OrchestrationResult,
    TradingOrchestrator,
)
from alpha_algo_trading_engine.state import (
    OrchestrationState,
    OrchestrationStateError,
    OrchestrationStateMachine,
    TERMINAL_STATES,
)

__all__ = [
    # state
    "OrchestrationState",
    "OrchestrationStateError",
    "OrchestrationStateMachine",
    "TERMINAL_STATES",
    # identity
    "compute_orchestration_identity_key",
    # intent
    "TradingIntent",
    "OrderIntentResolver",
    "UnavailableOrderIntentResolver",
    # oms port
    "OmsPort",
    "NoOpOmsPort",
    "HandoffResult",
    # metrics
    "OrchestrationMetrics",
    # repository
    "TradingIntentRepository",
    "to_orm_trading_intent",
    "to_orm_rejection",
    # service
    "TradingOrchestrator",
    "OrchestrationResult",
    # boundary
    "build_trading_orchestrator",
    "connect_signal_engine",
]
