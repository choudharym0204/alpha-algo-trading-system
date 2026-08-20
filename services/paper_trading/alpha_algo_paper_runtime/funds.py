from __future__ import annotations

"""Paper funds ledger (Phase 15).

Deterministic, immutable cash/reserve ledger for a single paper account.
Available cash is never negative unless the trading model explicitly allows it
(v1 does not). This is a cash-flow ledger only: P&L is computed by the P&L
engine (Phase 13), never here.
"""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True)
class PaperFunds:
    """Immutable funds state for one paper account.

    ``available_cash``  — cash free to trade (never negative).
    ``reserved_cash``   — cash committed to open/unfilled orders (never negative).
    """

    account_id: UUID
    available_cash: Decimal
    reserved_cash: Decimal = Decimal("0")
    currency: str = "INR"

    def __post_init__(self) -> None:
        if self.available_cash < Decimal("0"):
            raise ValueError("available_cash cannot be negative")
        if self.reserved_cash < Decimal("0"):
            raise ValueError("reserved_cash cannot be negative")

    @property
    def total_cash(self) -> Decimal:
        return self.available_cash + self.reserved_cash

    def reserve(self, amount: Decimal) -> "PaperFunds":
        """Commit cash for a pending order (available -> reserved)."""
        amount = Decimal(amount)
        if amount <= Decimal("0"):
            raise ValueError("reserve amount must be positive")
        if amount > self.available_cash:
            raise ValueError("insufficient available cash to reserve")
        return PaperFunds(
            account_id=self.account_id,
            available_cash=self.available_cash - amount,
            reserved_cash=self.reserved_cash + amount,
            currency=self.currency,
        )

    def release(self, amount: Decimal) -> "PaperFunds":
        """Return reserved cash (cancelled/rejected order) (reserved -> available)."""
        amount = Decimal(amount)
        if amount <= Decimal("0"):
            raise ValueError("release amount must be positive")
        if amount > self.reserved_cash:
            raise ValueError("release exceeds reserved cash")
        return PaperFunds(
            account_id=self.account_id,
            available_cash=self.available_cash + amount,
            reserved_cash=self.reserved_cash - amount,
            currency=self.currency,
        )

    def settle_buy(self, amount: Decimal) -> "PaperFunds":
        """Consume reserved cash into a filled buy (cash leaves the account)."""
        amount = Decimal(amount)
        if amount <= Decimal("0"):
            raise ValueError("buy settlement amount must be positive")
        if amount > self.reserved_cash:
            raise ValueError("buy settlement exceeds reserved cash")
        return PaperFunds(
            account_id=self.account_id,
            available_cash=self.available_cash,
            reserved_cash=self.reserved_cash - amount,
            currency=self.currency,
        )

    def credit_sell(self, amount: Decimal) -> "PaperFunds":
        """Credit sell proceeds into available cash (cash enters the account)."""
        amount = Decimal(amount)
        if amount <= Decimal("0"):
            raise ValueError("sell proceeds must be positive")
        return PaperFunds(
            account_id=self.account_id,
            available_cash=self.available_cash + amount,
            reserved_cash=self.reserved_cash,
            currency=self.currency,
        )
