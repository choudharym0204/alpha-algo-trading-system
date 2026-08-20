from __future__ import annotations

"""Paper account model (Phase 15).

An explicit, PAPER-labeled account runtime record. Paper accounts never share
financial state with LIVE accounts and never reuse a real broker account id.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from alpha_algo_broker_adapters import TradingMode


class PaperAccountStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    RESET = "RESET"


def _require_timezone(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True)
class PaperAccount:
    """Immutable PAPER account record.

    ``starting_capital`` is explicit and required — the simulator never silently
    defaults to an arbitrary capital. ``trading_mode`` is structurally pinned to
    ``TradingMode.PAPER`` so a paper account can never represent a LIVE account.
    """

    account_id: UUID
    paper_run_id: UUID
    trading_mode: TradingMode
    starting_capital: Decimal
    status: PaperAccountStatus
    created_at: datetime
    reset_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.trading_mode is not TradingMode.PAPER:
            raise ValueError(
                f"paper accounts must use TradingMode.PAPER, got {self.trading_mode}"
            )
        if self.starting_capital <= Decimal("0"):
            raise ValueError("starting_capital must be positive")
        _require_timezone(self.created_at, "created_at")
        if self.reset_at is not None:
            _require_timezone(self.reset_at, "reset_at")

    @property
    def is_active(self) -> bool:
        return self.status is PaperAccountStatus.ACTIVE
