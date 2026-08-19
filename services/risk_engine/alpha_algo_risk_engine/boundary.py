"""Phase 5 → Phase 6 boundary + risk-service composition root."""

from __future__ import annotations

from typing import TYPE_CHECKING

from alpha_algo_risk_engine.repository import RiskEventRepository
from alpha_algo_risk_engine.service import RiskService

if TYPE_CHECKING:
    from alpha_algo_signal_engine.service import SignalEngine


def build_risk_service(
    *,
    provider=None,
    session_factory=None,
    **service_kwargs,
) -> RiskService:
    """Composition root: build a risk service (optionally DB-backed)."""
    repository = RiskEventRepository(session_factory) if session_factory is not None else None
    return RiskService(provider=provider, repository=repository, **service_kwargs)


def connect_signal_engine(
    signal_engine: "SignalEngine",
    risk_service: RiskService,
    *,
    trading_mode: str = "PAPER",
) -> RiskService:
    """Wire a signal engine's persisted-signal fan-out into the risk service.

    Phase 5 only fans out PERSISTED signals (LIVE is already blocked there), so
    the risk service receives only BACKTEST/PAPER signals; the identity_key is
    passed through so risk duplicate detection reuses Phase 5 identity.
    """
    signal_engine.add_consumer(
        lambda record: risk_service.evaluate(
            record.signal,
            trading_mode=trading_mode,
        )
    )
    return risk_service
