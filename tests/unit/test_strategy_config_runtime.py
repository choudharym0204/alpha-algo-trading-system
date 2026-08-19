from __future__ import annotations

import pytest

from alpha_algo_strategy_engine import (
    ConfigValidationError,
    StrategyInstance,
    StrategyRuntime,
    TradingMode,
    TradingModeError,
)
from strategy_test_support import (
    RecordingStrategy,
    make_definition,
    make_identity,
)


def test_valid_config_starts() -> None:
    identity = make_identity(config={"fast": 5, "slow": 20})
    definition = make_definition(identity=identity, config={"fast": 5, "slow": 20})
    instance = StrategyInstance(definition, RecordingStrategy())
    instance.initialize()
    instance.start()


def test_invalid_config_rejected() -> None:
    identity = make_identity(config={"fast": 5})
    definition = make_definition(identity=identity, config={"fast": object()})
    with pytest.raises(ConfigValidationError):
        StrategyInstance(definition, RecordingStrategy())


def test_config_hash_mismatch_rejected() -> None:
    identity = make_identity(config={"fast": 5})
    definition = make_definition(identity=identity, config={"fast": 6})
    with pytest.raises(ConfigValidationError, match="config hash mismatch"):
        StrategyInstance(definition, RecordingStrategy())


def test_version_mismatch_signal_rejected() -> None:
    from alpha_algo_strategy_engine import SignalValidator

    identity = make_identity(version="1.0.0")
    validator = SignalValidator()
    from strategy_test_support import make_signal

    signal = make_signal(
        strategy_id=identity.strategy_id, version="2.0.0", config_hash=identity.config_hash
    )
    assert validator.validate(signal, identity).reason == "strategy_version_mismatch"


def test_trading_mode_backtest_allowed() -> None:
    identity = make_identity()
    runtime = StrategyRuntime()
    runtime.register(make_definition(identity=identity))
    run_id = runtime.start(identity.strategy_id, TradingMode.BACKTEST)
    assert runtime.run_record(identity.strategy_id).run_id == run_id


def test_trading_mode_paper_allowed() -> None:
    identity = make_identity()
    runtime = StrategyRuntime()
    runtime.register(make_definition(identity=identity))
    runtime.start(identity.strategy_id, TradingMode.PAPER)
    assert runtime.status(identity.strategy_id)["trading_mode"] == "PAPER"


def test_trading_mode_live_blocked() -> None:
    identity = make_identity()
    runtime = StrategyRuntime()
    runtime.register(make_definition(identity=identity))
    with pytest.raises(TradingModeError, match="not allowed"):
        runtime.start(identity.strategy_id, TradingMode.LIVE)
    # live blocked as a string too
    with pytest.raises(TradingModeError):
        runtime.start(identity.strategy_id, "LIVE")
