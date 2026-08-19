"""Alpha Algo Strategy Runtime (Phase 4).

Converts the existing strategy contracts into a controlled, testable runtime:
registry → lifecycle → instance → context → signal generation → validated
`StrategySignal`. LIVE trading mode is blocked; no broker/risk/order access.
"""

from alpha_algo_strategy_engine.config import StrategyConfig, validate_config
from alpha_algo_strategy_engine.dispatcher import StrategyDispatcher
from alpha_algo_strategy_engine.duplicate import SignalDeduplicator, signal_dedup_key
from alpha_algo_strategy_engine.errors import (
    ConfigValidationError,
    DuplicateRegistrationError,
    LifecycleError,
    RegistryError,
    SignalValidationError,
    StrategyNotFoundError,
    StrategyRuntimeError,
    TradingModeError,
)
from alpha_algo_strategy_engine.identity import (
    StrategyIdentity,
    compute_code_hash,
    compute_config_hash,
)
from alpha_algo_strategy_engine.instance import StrategyInstance
from alpha_algo_strategy_engine.market_data_boundary import connect_market_data
from alpha_algo_strategy_engine.metrics import StrategyMetrics
from alpha_algo_strategy_engine.registry import StrategyDefinition, StrategyRegistry
from alpha_algo_strategy_engine.run_record import StrategyRunRecord
from alpha_algo_strategy_engine.signal_validation import (
    SignalValidationResult,
    SignalValidator,
)
from alpha_algo_strategy_engine.state import RunStateMachine, StrategyRunState, TradingMode
from alpha_algo_strategy_engine.runtime import StrategyRuntime
from alpha_algo_strategy_engine.strategies import SmaCrossStrategy

__all__ = [
    "ConfigValidationError",
    "DuplicateRegistrationError",
    "LifecycleError",
    "RegistryError",
    "RunStateMachine",
    "SignalDeduplicator",
    "SignalValidationError",
    "SignalValidationResult",
    "SignalValidator",
    "SmaCrossStrategy",
    "StrategyConfig",
    "StrategyDefinition",
    "StrategyDispatcher",
    "StrategyIdentity",
    "StrategyInstance",
    "StrategyMetrics",
    "StrategyNotFoundError",
    "StrategyRegistry",
    "StrategyRunRecord",
    "StrategyRuntime",
    "StrategyRuntimeError",
    "StrategyRunState",
    "TradingMode",
    "TradingModeError",
    "compute_code_hash",
    "compute_config_hash",
    "connect_market_data",
    "signal_dedup_key",
    "validate_config",
]
