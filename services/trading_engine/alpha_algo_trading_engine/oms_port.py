"""OMS handoff port (Phase 7) — the explicit boundary between the orchestrator
and the future Phase-8 OMS. It is NOT a broker: it only notifies the OMS that a
durable, OMS-ready intent exists for consumption.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from alpha_algo_trading_engine.intent import TradingIntent


@dataclass(frozen=True)
class HandoffResult:
    delivered: bool
    reason: str = ""


class OmsPort(Protocol):
    def handoff(self, intent: TradingIntent) -> HandoffResult: ...


class NoOpOmsPort:
    """Default port: accepts the handoff without performing any external action."""

    def handoff(self, intent: TradingIntent) -> HandoffResult:
        return HandoffResult(delivered=True)
