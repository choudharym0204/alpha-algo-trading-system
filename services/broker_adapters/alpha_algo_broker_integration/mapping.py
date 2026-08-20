"""Universal mapping helpers (Phase 10).

Shared, broker-agnostic helpers for symbol/instrument mapping validation,
order-type and product-type translation, and quantity/lot validation. Concrete
adapters supply their own broker-specific translation tables and call these
helpers so that unsupported operations are rejected (never silently downgraded).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from alpha_algo_broker_integration.contracts import (
    UniversalOrderType,
    UniversalProductType,
)
from alpha_algo_broker_integration.errors import BrokerError, BrokerErrorClass


class InstrumentSecurityType(StrEnum):
    EQUITY = "EQUITY"
    FUTURE = "FUTURE"
    OPTION = "OPTION"
    INDEX = "INDEX"


@dataclass(frozen=True)
class BrokerInstrument:
    """A broker-side instrument reference for an internal instrument."""

    internal_instrument_id: UUID
    exchange: str
    symbol: str
    broker_token: str
    instrument_key: str
    security_type: InstrumentSecurityType = InstrumentSecurityType.EQUITY
    expiry: str | None = None
    strike: Decimal | None = None
    option_type: str | None = None
    lot_size: int = 1
    tick_size: Decimal = Decimal("0.05")

    def validate_contract(self, *, exchange: str, symbol: str) -> bool:
        return self.exchange == exchange and self.symbol == symbol


@dataclass(frozen=True)
class InstrumentMapping:
    """Internal instrument id -> broker instrument(s)."""

    _by_id: dict[UUID, BrokerInstrument] | None = None

    def __init__(self) -> None:
        object.__setattr__(self, "_by_id", {})

    def register(self, instrument: BrokerInstrument) -> None:
        self._by_id[instrument.internal_instrument_id] = instrument  # type: ignore[index]

    def resolve(
        self, internal_instrument_id: UUID, *, exchange: str, symbol: str
    ) -> BrokerInstrument:
        instrument = self._by_id.get(internal_instrument_id)  # type: ignore[attr-defined]
        if instrument is None:
            raise BrokerError(
                BrokerErrorClass.VALIDATION,
                f"no broker mapping for instrument {internal_instrument_id}",
            )
        if not instrument.validate_contract(exchange=exchange, symbol=symbol):
            raise BrokerError(
                BrokerErrorClass.VALIDATION,
                "instrument mapping mismatch (exchange/symbol/contract)",
            )
        return instrument

    def find_by_symbol(self, *, exchange: str, symbol: str) -> BrokerInstrument | None:
        for instrument in self._by_id.values():  # type: ignore[attr-defined]
            if instrument.exchange == exchange and instrument.symbol == symbol:
                return instrument
        return None


def validate_quantity(
    *,
    quantity: int,
    lot_size: int,
    min_quantity: int = 1,
    max_quantity: int | None = None,
) -> None:
    """Reject quantities that violate lot size / bounds. Never guesses a lot."""
    if quantity <= 0:
        raise BrokerError(BrokerErrorClass.VALIDATION, "quantity must be positive")
    if quantity % lot_size != 0:
        raise BrokerError(
            BrokerErrorClass.VALIDATION,
            f"quantity {quantity} is not a multiple of lot size {lot_size}",
        )
    if quantity < min_quantity:
        raise BrokerError(BrokerErrorClass.VALIDATION, "quantity below minimum")
    if max_quantity is not None and quantity > max_quantity:
        raise BrokerError(BrokerErrorClass.VALIDATION, "quantity above maximum")


def require_supported(
    *,
    value: str,
    supported: frozenset[str],
    what: str,
) -> None:
    """Reject an unsupported value rather than silently translating it."""
    if value not in supported:
        raise BrokerError(
            BrokerErrorClass.UNSUPPORTED,
            f"unsupported {what}: {value}",
        )


__all__ = [
    "InstrumentSecurityType",
    "BrokerInstrument",
    "InstrumentMapping",
    "validate_quantity",
    "require_supported",
    "UniversalOrderType",
    "UniversalProductType",
]
