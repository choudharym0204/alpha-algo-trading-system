from __future__ import annotations

import pytest

from alpha_algo_strategy_engine import (
    DuplicateRegistrationError,
    StrategyNotFoundError,
)
from strategy_test_support import RecordingStrategy, make_definition, make_identity


def test_register_and_lookup() -> None:
    from alpha_algo_strategy_engine import StrategyRegistry

    registry = StrategyRegistry()
    identity = make_identity(code="sma")
    registry.register(make_definition(identity=identity))
    definition = registry.get(identity.strategy_id)
    assert definition.identity.code == "sma"
    assert registry.get_by_code("sma").identity.strategy_id == identity.strategy_id


def test_duplicate_registration_rejected() -> None:
    from alpha_algo_strategy_engine import StrategyRegistry

    registry = StrategyRegistry()
    identity = make_identity(code="sma")
    registry.register(make_definition(identity=identity))
    with pytest.raises(DuplicateRegistrationError):
        registry.register(make_definition(identity=identity))
    # same code, different id
    other = make_identity(code="sma")
    with pytest.raises(DuplicateRegistrationError):
        registry.register(make_definition(identity=other))


def test_unregister_and_lookup_missing() -> None:
    from alpha_algo_strategy_engine import StrategyRegistry

    registry = StrategyRegistry()
    identity = make_identity(code="sma")
    registry.register(make_definition(identity=identity))
    registry.unregister(identity.strategy_id)
    with pytest.raises(StrategyNotFoundError):
        registry.get(identity.strategy_id)


def test_load_instantiates_strategy() -> None:
    from alpha_algo_strategy_engine import StrategyRegistry

    registry = StrategyRegistry()
    identity = make_identity(code="sma")
    registry.register(make_definition(identity=identity, factory=RecordingStrategy))
    strategy = registry.load(identity.strategy_id)
    assert isinstance(strategy, RecordingStrategy)


def test_enable_disable_and_status() -> None:
    from alpha_algo_strategy_engine import StrategyRegistry

    registry = StrategyRegistry()
    identity = make_identity(code="sma")
    registry.register(make_definition(identity=identity))
    assert registry.status(identity.strategy_id)["enabled"] is True
    registry.disable(identity.strategy_id)
    assert registry.status(identity.strategy_id)["enabled"] is False
    registry.enable(identity.strategy_id)
    assert registry.status(identity.strategy_id)["enabled"] is True


def test_clear() -> None:
    from alpha_algo_strategy_engine import StrategyRegistry

    registry = StrategyRegistry()
    identity = make_identity(code="sma")
    registry.register(make_definition(identity=identity))
    assert len(registry) == 1
    registry.clear()
    assert len(registry) == 0
