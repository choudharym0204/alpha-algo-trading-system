"""OMS-ready trading intent + order-intent resolution (Phase 7).

A ``TradingIntent`` is the normalization of an approved, risk-cleared signal into
the representation Phase-8 OMS consumes to create an order *without reinterpreting
the strategy signal*. It never reaches a broker here.

Quantity/account/order-type are resolved through an explicit ``OrderIntentResolver``
(pluggable) so the orchestrator never silently invents a quantity. The default
resolver fails closed (returns ``None``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from alpha_algo_contracts import StrategySignal
from alpha_algo_risk_engine.context import RiskOrderIntent


class OrderIntentResolver(Protocol):
    """Resolves the concrete order intent (quantity/account/order type) for a signal."""

    def resolve(
        self,
        signal: StrategySignal,
        trading_mode: str,
    ) -> RiskOrderIntent | None: ...


class UnavailableOrderIntentResolver:
    """Fail-closed default: no intent is resolvable (quantity stays unknown)."""

    def resolve(
        self,
        signal: StrategySignal,
        trading_mode: str,
    ) -> RiskOrderIntent | None:
        return None


@dataclass(frozen=True)
class TradingIntent:
    """Normalized, OMS-ready intent (the handoff payload for Phase 8)."""

    correlation_id: UUID
    orchestration_id: str
    account_id: UUID | None
    strategy_id: UUID
    strategy_version: str
    strategy_config_hash: str
    strategy_run_id: UUID | None
    signal_id: UUID
    signal_identity_key: str
    instrument_id: UUID
    action: str
    quantity: Decimal
    order_type: str
    limit_price: Decimal | None
    trading_mode: str
    risk_decision_id: UUID
    approval_id: UUID
    approval_expires_at: datetime
    binding_hash: str
    metadata: dict[str, object] = field(default_factory=dict)
