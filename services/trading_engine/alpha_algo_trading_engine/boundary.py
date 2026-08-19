"""Phase 5 → Phase 7 boundary + trading-orchestrator composition root."""

from __future__ import annotations

from typing import TYPE_CHECKING

from alpha_algo_trading_engine.repository import TradingIntentRepository
from alpha_algo_trading_engine.service import TradingOrchestrator

if TYPE_CHECKING:
    from alpha_algo_signal_engine.service import SignalEngine


def build_trading_orchestrator(
    *,
    risk_service,
    session_factory=None,
    intent_resolver=None,
    oms_port=None,
    **service_kwargs,
) -> TradingOrchestrator:
    """Composition root: build a trading orchestrator (optionally DB-backed)."""
    repository = TradingIntentRepository(session_factory) if session_factory is not None else None
    return TradingOrchestrator(
        risk_service=risk_service,
        intent_resolver=intent_resolver,
        oms_port=oms_port,
        repository=repository,
        **service_kwargs,
    )


def connect_signal_engine(
    signal_engine: "SignalEngine",
    orchestrator: TradingOrchestrator,
    *,
    trading_mode: str = "PAPER",
) -> TradingOrchestrator:
    """Wire the signal engine's persisted-signal fan-out into the orchestrator.

    Phase 5 only fans out PERSISTED signals, so the orchestrator receives only
    accepted signals; it still re-verifies acceptance + identity + mode.
    """
    signal_engine.add_consumer(
        lambda record: orchestrator.process_signal(record, trading_mode=trading_mode)
    )
    return orchestrator
