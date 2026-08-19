"""Cost models for the backtest simulation engine (P7-002).

Slippage and commission are pure functions of the fill anchor and the
caller-supplied :class:`CostModel`. Both components are required at
construction (no defaults): a cost-free run is the caller's explicit
``Decimal("0")``, never an implied default.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext

from alpha_algo_backtest_engine.errors import BacktestEngineError
from alpha_algo_backtest_engine.intents import IntentSide

__all__ = [
    "COMMISSION_POLICY",
    "CostModel",
    "DECIMAL_PRECISION",
    "SLIPPAGE_POLICY",
    "apply_slippage",
    "commission_for",
]

DECIMAL_PRECISION = 28

SLIPPAGE_POLICY = (
    "Slippage applies to MARKET fills only: a BUY pays anchor + anchor * "
    "slippage_bps / 10000 and a SELL receives anchor - anchor * slippage_bps "
    "/ 10000. LIMIT fills are price-capped by the limit and never slippaged: "
    "applying slippage to a limit fill could push a buy above its own limit, "
    "which is an impossible execution."
)

COMMISSION_POLICY = (
    "A flat commission_per_fill is charged on both sides of every fill, "
    "separately from price. Unfilled intents pay no commission. There is no "
    "minimum, percentage, or per-quantity commission in v1."
)


@dataclass(frozen=True)
class CostModel:
    """Explicit cost parameters for a backtest run.

    Both fields are required — there are no defaults, so a cost-free run is
    an explicit ``Decimal("0")`` from the caller. Negative values and
    slippage at or above 10000 bps (a 100%+ sell slippage would produce a
    non-positive fill price) are rejected at construction.
    """

    commission_per_fill: Decimal
    slippage_bps: Decimal

    def __post_init__(self) -> None:
        for name, value in (
            ("commission_per_fill", self.commission_per_fill),
            ("slippage_bps", self.slippage_bps),
        ):
            if not isinstance(value, Decimal):
                raise BacktestEngineError(f"{name} must be a Decimal")
            if not value.is_finite():
                raise BacktestEngineError(f"{name} must be finite")
            if value < 0:
                raise BacktestEngineError(f"{name} must be non-negative")
        if self.slippage_bps >= Decimal("10000"):
            raise BacktestEngineError(
                "slippage_bps must be below 10000 (a 100%+ sell slippage would produce a non-positive fill price)"
            )


def _require_decimal(value: object, name: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise BacktestEngineError(f"{name} must be a Decimal")
    if not value.is_finite():
        raise BacktestEngineError(f"{name} must be finite")
    return value


def apply_slippage(anchor_price: Decimal, side: IntentSide, slippage_bps: Decimal) -> Decimal:
    """Return the effective fill price after adversarial slippage.

    A BUY pays a worse (higher) price; a SELL receives a worse (lower)
    price. A zero bps value is the identity. The division is wrapped in an
    explicit ``localcontext`` so a third-party mutation of the global
    decimal context can never change results.
    """
    anchor = _require_decimal(anchor_price, "anchor_price")
    if anchor <= 0:
        raise BacktestEngineError("anchor_price must be positive")
    if not isinstance(side, IntentSide):
        raise BacktestEngineError("side must be an IntentSide member")
    bps = _require_decimal(slippage_bps, "slippage_bps")
    if bps < 0 or bps >= Decimal("10000"):
        raise BacktestEngineError("slippage_bps must be in [0, 10000)")
    if bps == 0:
        return anchor
    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION
        if side is IntentSide.BUY:
            factor = Decimal(1) + bps / Decimal("10000")
        else:
            factor = Decimal(1) - bps / Decimal("10000")
        return anchor * factor


def commission_for(commission_per_fill: Decimal) -> Decimal:
    """Return the flat commission charged for one fill (validated)."""
    value = _require_decimal(commission_per_fill, "commission_per_fill")
    if value < 0:
        raise BacktestEngineError("commission_per_fill must be non-negative")
    return value
