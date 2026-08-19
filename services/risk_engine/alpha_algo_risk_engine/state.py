"""Runtime risk-state provider protocol + fail-closed default (Phase 6).

The risk engine must read financial state from authoritative runtime sources.
Where no authoritative source is wired (positions/portfolio/P&L are Phase 11+
and a live DB is not present in this environment), the default provider reports
state as UNAVAILABLE so every critical rule fails closed (REJECT) rather than
substituting fabricated values.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from alpha_algo_risk_engine.snapshot import RiskSnapshot


class RiskStateError(Exception):
    """Base error for risk-state acquisition failures."""


class RiskStateUnavailable(RiskStateError):
    """Authoritative risk state could not be acquired (fail closed)."""


class RiskStateProvider(Protocol):
    def get_snapshot(
        self,
        *,
        account_id: UUID | None = None,
        instrument_id: UUID | None = None,
        strategy_id: UUID | None = None,
    ) -> RiskSnapshot: ...


class UnavailableRiskStateProvider:
    """Fail-closed provider used when no authoritative state source is wired."""

    def __init__(self, *, reason: str = "no authoritative risk-state source wired") -> None:
        self._reason = reason

    def get_snapshot(
        self,
        *,
        account_id: UUID | None = None,
        instrument_id: UUID | None = None,
        strategy_id: UUID | None = None,
    ) -> RiskSnapshot:
        return RiskSnapshot(
            source="unavailable",
            state_available=False,
            metadata={"reason": self._reason},
        )
