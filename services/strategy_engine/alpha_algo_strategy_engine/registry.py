"""Strategy registry: register/unregister/discover/load/validate/enable/disable."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable, Mapping
from uuid import UUID

from alpha_algo_contracts import CandleTimeframe
from alpha_algo_strategy_engine.errors import (
    DuplicateRegistrationError,
    StrategyNotFoundError,
)
from alpha_algo_strategy_engine.identity import StrategyIdentity
from alpha_algo_strategies import StrategyLifecycle


@dataclass(frozen=True)
class StrategyDefinition:
    """A registered strategy: stable identity + how to instantiate it + routing."""

    identity: StrategyIdentity
    factory: Callable[[], StrategyLifecycle]
    enabled: bool = True
    instruments: frozenset[UUID] = frozenset()  # empty = all instruments
    timeframes: frozenset[CandleTimeframe] = frozenset()  # empty = all timeframes
    config: Mapping[str, object] = field(default_factory=dict)
    metadata: Mapping[str, object] = field(default_factory=dict)


class StrategyRegistry:
    def __init__(self) -> None:
        self._by_id: dict[UUID, StrategyDefinition] = {}
        self._by_code: dict[str, UUID] = {}

    def register(self, definition: StrategyDefinition) -> None:
        identity = definition.identity
        if identity.strategy_id in self._by_id:
            raise DuplicateRegistrationError(
                f"strategy_id already registered: {identity.strategy_id}"
            )
        if identity.code in self._by_code:
            raise DuplicateRegistrationError(
                f"strategy code already registered: {identity.code!r}"
            )
        self._by_id[identity.strategy_id] = definition
        self._by_code[identity.code] = identity.strategy_id

    def unregister(self, strategy_id: UUID) -> None:
        definition = self._by_id.pop(strategy_id, None)
        if definition is None:
            raise StrategyNotFoundError(f"strategy not registered: {strategy_id}")
        self._by_code.pop(definition.identity.code, None)

    def get(self, strategy_id: UUID) -> StrategyDefinition:
        try:
            return self._by_id[strategy_id]
        except KeyError:
            raise StrategyNotFoundError(f"strategy not registered: {strategy_id}") from None

    def get_by_code(self, code: str) -> StrategyDefinition:
        strategy_id = self._by_code.get(code)
        if strategy_id is None:
            raise StrategyNotFoundError(f"strategy not registered: {code!r}")
        return self._by_id[strategy_id]

    def all(self) -> list[StrategyDefinition]:
        return list(self._by_id.values())

    def load(self, strategy_id: UUID) -> StrategyLifecycle:
        """Instantiate a fresh strategy implementation via its factory.

        Validates that the factory actually returns a `StrategyLifecycle` so a
        mis-wired factory fails fast at load time rather than at first dispatch.
        """
        definition = self.get(strategy_id)
        impl = definition.factory()
        if not isinstance(impl, StrategyLifecycle):
            raise TypeError(
                f"factory for {definition.identity.code!r} did not return a StrategyLifecycle"
            )
        return impl

    def enable(self, strategy_id: UUID) -> None:
        self._set_enabled(strategy_id, True)

    def disable(self, strategy_id: UUID) -> None:
        self._set_enabled(strategy_id, False)

    def _set_enabled(self, strategy_id: UUID, enabled: bool) -> None:
        definition = self.get(strategy_id)
        self._by_id[strategy_id] = replace(definition, enabled=enabled)

    def status(self, strategy_id: UUID) -> dict[str, object]:
        definition = self.get(strategy_id)
        return {
            "strategy_id": str(definition.identity.strategy_id),
            "code": definition.identity.code,
            "name": definition.identity.name,
            "version": definition.identity.version,
            "config_hash": definition.identity.config_hash,
            "code_hash": definition.identity.code_hash,
            "enabled": definition.enabled,
        }

    def clear(self) -> None:
        """Lifecycle-safe cleanup (registry teardown)."""
        self._by_id.clear()
        self._by_code.clear()

    def __len__(self) -> int:
        return len(self._by_id)
