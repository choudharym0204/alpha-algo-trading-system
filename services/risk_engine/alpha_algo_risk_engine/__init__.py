"""Alpha Algo Risk Engine (Phase 6) — public exports."""

from alpha_algo_risk_engine.approval import (
    approval_is_usable,
    compute_approval_binding,
    compute_risk_identity_key,
)
from alpha_algo_risk_engine.boundary import build_risk_service, connect_signal_engine
from alpha_algo_risk_engine.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerRegistry,
    CircuitState,
)
from alpha_algo_risk_engine.context import (
    RiskContextBuilder,
    RiskContextError,
    RiskContextUnavailable,
    RiskContextValidator,
    RiskOrderIntent,
)
from alpha_algo_risk_engine.engine import (
    AccountLimitRule,
    BrokerHealthRule,
    DailyLossLimitRule,
    DuplicateOrderProtectionRule,
    ExecutionTimeoutRule,
    ExposureLimitRule,
    GlobalHaltRule,
    InstrumentRestrictionRule,
    LiveModeRule,
    MarginAvailabilityRule,
    MarketDataFreshnessRule,
    MarketSessionRule,
    MaximumDrawdownRule,
    MaximumOpenPositionsRule,
    OrderFrequencyRule,
    PositionLimitRule,
    PriceDeviationRule,
    QuantityLimitRule,
    RetrySafetyRule,
    RiskEvaluationContext,
    RiskRule,
    RiskRuleEngine,
    RiskTradingMode,
    RuleEvaluation,
    StrategyLossLimitRule,
    default_risk_rules,
)
from alpha_algo_risk_engine.gates import (
    GlobalHaltController,
    GlobalHaltState,
    LiveReleaseController,
    LiveReleaseDecision,
    LiveReleaseStage,
    LiveSafetyGate,
    LiveSafetyGateDecision,
    LiveSafetyGateEvaluator,
    LiveSafetyGateSnapshot,
)
from alpha_algo_risk_engine.metrics import RiskMetrics
from alpha_algo_risk_engine.repository import RiskEventRepository, to_orm_risk_event
from alpha_algo_risk_engine.service import RiskEvaluationOutcome, RiskService
from alpha_algo_risk_engine.snapshot import (
    AccountSnapshot,
    LimitsSnapshot,
    MarketSnapshot,
    OrderFrequencySnapshot,
    PositionSnapshot,
    RiskSnapshot,
)
from alpha_algo_risk_engine.state import (
    RiskStateError,
    RiskStateProvider,
    RiskStateUnavailable,
    UnavailableRiskStateProvider,
)

__all__ = [
    # contracts (re-exported via engine/context)
    "RiskEvaluationContext",
    "RiskRuleEngine",
    "RiskTradingMode",
    "RuleEvaluation",
    "RiskRule",
    "default_risk_rules",
    "GlobalHaltRule",
    "LiveModeRule",
    "BrokerHealthRule",
    "MarketDataFreshnessRule",
    "MarketSessionRule",
    "InstrumentRestrictionRule",
    "QuantityLimitRule",
    "PositionLimitRule",
    "ExposureLimitRule",
    "DailyLossLimitRule",
    "StrategyLossLimitRule",
    "MarginAvailabilityRule",
    "DuplicateOrderProtectionRule",
    "MaximumOpenPositionsRule",
    "AccountLimitRule",
    "MaximumDrawdownRule",
    "PriceDeviationRule",
    "OrderFrequencyRule",
    "ExecutionTimeoutRule",
    "RetrySafetyRule",
    # gates
    "GlobalHaltController",
    "GlobalHaltState",
    "LiveReleaseController",
    "LiveReleaseDecision",
    "LiveReleaseStage",
    "LiveSafetyGate",
    "LiveSafetyGateDecision",
    "LiveSafetyGateEvaluator",
    "LiveSafetyGateSnapshot",
    # snapshot
    "RiskSnapshot",
    "AccountSnapshot",
    "MarketSnapshot",
    "PositionSnapshot",
    "LimitsSnapshot",
    "OrderFrequencySnapshot",
    # state
    "RiskStateProvider",
    "RiskStateError",
    "RiskStateUnavailable",
    "UnavailableRiskStateProvider",
    # circuit breaker
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerRegistry",
    "CircuitState",
    # context
    "RiskOrderIntent",
    "RiskContextBuilder",
    "RiskContextValidator",
    "RiskContextError",
    "RiskContextUnavailable",
    # approval
    "compute_approval_binding",
    "compute_risk_identity_key",
    "approval_is_usable",
    # repository
    "RiskEventRepository",
    "to_orm_risk_event",
    # metrics
    "RiskMetrics",
    # service + boundary
    "RiskService",
    "RiskEvaluationOutcome",
    "build_risk_service",
    "connect_signal_engine",
]
