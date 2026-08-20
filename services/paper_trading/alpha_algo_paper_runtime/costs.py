from __future__ import annotations

"""Paper cost model (Phase 15): explicit, deterministic slippage + commission.

The default is **zero slippage** and **zero commission** — nothing is applied
silently. A configurable deterministic model (fixed basis-point slippage and a
fixed per-trade commission) is available, and is always persisted in the run
configuration so replay is reproducible.

No tax formulas are invented. Commission/slippage are a cash-flow concern of the
paper service, not of the broker's raw fill price (which stays at the reference
price for determinism).
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN
from enum import StrEnum

PRICE_QUANTUM = Decimal("0.0001")
MONEY_QUANTUM = Decimal("0.01")


class SlippageModel(StrEnum):
    ZERO = "ZERO"
    FIXED_BPS = "FIXED_BPS"


class CommissionModel(StrEnum):
    ZERO = "ZERO"
    FIXED_PER_TRADE = "FIXED_PER_TRADE"


@dataclass(frozen=True)
class PaperCostModel:
    slippage: SlippageModel = SlippageModel.ZERO
    slippage_bps: Decimal = Decimal("0")
    commission: CommissionModel = CommissionModel.ZERO
    commission_per_trade: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if self.slippage_bps < Decimal("0"):
            raise ValueError("slippage_bps cannot be negative")
        if self.commission_per_trade < Decimal("0"):
            raise ValueError("commission_per_trade cannot be negative")
        if self.slippage is SlippageModel.ZERO and self.slippage_bps != Decimal("0"):
            raise ValueError("ZERO slippage model cannot carry a non-zero bps")
        if self.commission is CommissionModel.ZERO and self.commission_per_trade != Decimal("0"):
            raise ValueError("ZERO commission model cannot carry a non-zero per-trade fee")

    def as_config(self) -> dict[str, str]:
        """Deterministic replay fingerprint of the cost model."""
        return {
            "slippage": self.slippage.value,
            "slippage_bps": str(self.slippage_bps),
            "commission": self.commission.value,
            "commission_per_trade": str(self.commission_per_trade),
        }


def apply_slippage(price: Decimal, side: str, model: PaperCostModel) -> Decimal:
    """Effective execution price after deterministic slippage.

    BUY pays ``price * (1 + bps/10_000)``; SELL receives
    ``price * (1 - bps/10_000)``. ZERO slippage returns ``price`` unchanged.
    """
    if model.slippage is SlippageModel.ZERO:
        return price
    factor = Decimal("1") + (model.slippage_bps / Decimal("10000"))
    if side == "SELL":
        factor = Decimal("1") - (model.slippage_bps / Decimal("10000"))
    return (price * factor).quantize(PRICE_QUANTUM, rounding=ROUND_HALF_EVEN)


def commission_amount(notional: Decimal, model: PaperCostModel) -> Decimal:
    """Deterministic commission for one trade. ZERO commission returns 0."""
    if model.commission is CommissionModel.ZERO:
        return Decimal("0")
    return model.commission_per_trade.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_EVEN)
