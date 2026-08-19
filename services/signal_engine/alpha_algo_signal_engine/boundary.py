"""Phase 4 → Phase 5 boundary.

Wires the Phase-4 `StrategyRuntime` signal fan-out to a Phase-5 `SignalEngine`
through the runtime's existing consumer abstraction. A thin
`RuntimeStrategyDirectory` adapts the Phase-4 registry to the signal engine's
`StrategyDirectory` protocol so the engine can validate strategy
known/enabled/version/hash/instrument without importing strategy-engine
internals elsewhere.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from alpha_algo_signal_engine.directory import StrategyRecord
from alpha_algo_signal_engine.repository import SignalRepository

if TYPE_CHECKING:
    from alpha_algo_strategy_engine.runtime import StrategyRuntime
    from alpha_algo_signal_engine.service import SignalEngine


class RuntimeStrategyDirectory:
    """Adapts the Phase-4 `StrategyRegistry` to the signal engine directory."""

    def __init__(self, registry) -> None:
        self._registry = registry

    def lookup(self, strategy_id) -> StrategyRecord | None:
        try:
            definition = self._registry.get(strategy_id)
        except Exception:  # noqa: BLE001 - registry "not found" / unknown strategy
            return None
        identity = definition.identity
        instruments = definition.instruments or None
        return StrategyRecord(
            strategy_id=identity.strategy_id,
            version=identity.version,
            config_hash=identity.config_hash,
            code_hash=identity.code_hash,
            enabled=definition.enabled,
            instruments=frozenset(instruments) if instruments is not None else None,
        )


def _run_mode(runtime: "StrategyRuntime", signal) -> str:
    record = runtime.run_record(signal.strategy_id)
    return record.trading_mode.value if record is not None else "PAPER"


def build_signal_engine(
    runtime: "StrategyRuntime",
    session_factory,
    **engine_kwargs,
) -> "SignalEngine":
    """Composition root: build + wire a signal engine onto a strategy runtime."""
    from alpha_algo_signal_engine.service import SignalEngine

    directory = RuntimeStrategyDirectory(runtime.registry)
    engine = SignalEngine(
        directory=directory,
        repository=SignalRepository(session_factory),
        **engine_kwargs,
    )
    runtime.add_signal_consumer(
        lambda signal: engine.ingest(signal, trading_mode=_run_mode(runtime, signal))
    )
    return engine


def connect_strategy_runtime(runtime: "StrategyRuntime", engine: "SignalEngine") -> "StrategyRuntime":
    """Wire an existing engine onto a runtime and return the runtime."""
    engine.set_directory(RuntimeStrategyDirectory(runtime.registry))
    runtime.add_signal_consumer(
        lambda signal: engine.ingest(signal, trading_mode=_run_mode(runtime, signal))
    )
    return runtime
