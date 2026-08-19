from __future__ import annotations

"""Pure, deterministic fill policy for the paper trading foundation.

``decide_fill`` is a pure function: it takes a broker order request and an
injected reference price and returns a :class:`FillDecision`. It has no clock,
no randomness, no I/O, and no wall-clock dependence — the same inputs always
produce the same decision (ADR-0007).

Fill policy (v1, documented and fixed):

- MARKET BUY fills at ``reference.last``; MARKET SELL fills at ``reference.last``.
- LIMIT BUY fills at ``reference.ask`` iff ``limit_price >= ask``.
- LIMIT SELL fills at ``reference.bid`` iff ``limit_price <= bid``.
- A LIMIT order whose required quote leg (bid for sells, ask for buys) is
  missing from the injected reference is *not executable* and rejects — the
  policy never falls back to ``last`` for limit execution.
- STOP and STOP_LIMIT are unsupported in v1 and raise
  :class:`UnsupportedOrderTypeError`; the broker-facing surface converts that
  into a REJECTED response plus a REJECTED event.
"""

from decimal import Decimal

from alpha_algo_broker_adapters import BrokerOrderRequest, OrderSide, OrderType

from alpha_algo_paper_trading.errors import UnsupportedOrderTypeError
from alpha_algo_paper_trading.types import FillDecision, PaperReferencePrice

__all__ = ["decide_fill"]


def decide_fill(
    request: BrokerOrderRequest, reference: PaperReferencePrice
) -> FillDecision:
    """Decide whether the order fills against the injected reference price.

    Raises ``UnsupportedOrderTypeError`` for STOP / STOP_LIMIT. All other
    outcomes are returned as a :class:`FillDecision` — never raised — so the
    broker-facing surface can turn non-executability into a REJECTED response
    plus a REJECTED event.
    """
    if request.order_type in {OrderType.STOP, OrderType.STOP_LIMIT}:
        raise UnsupportedOrderTypeError(
            f"unsupported order type in paper mode: {request.order_type.value}"
        )

    if request.side is OrderSide.BUY:
        return _decide_buy(request, reference)
    if request.side is OrderSide.SELL:
        return _decide_sell(request, reference)
    raise ValueError(f"unsupported order side: {request.side}")


def _full_quantity_decision(request: BrokerOrderRequest, fill_price: Decimal) -> FillDecision:
    """A v1 paper fill always completes the full order quantity."""
    return FillDecision(
        fills=True,
        fill_price=fill_price,
        fill_quantity=Decimal(request.quantity),
    )


def _decide_buy(
    request: BrokerOrderRequest, reference: PaperReferencePrice
) -> FillDecision:
    if request.order_type is OrderType.MARKET:
        return _full_quantity_decision(request, reference.last)

    # LIMIT BUY: executable only against an explicit ask leg.
    if reference.ask is None:
        return FillDecision(
            fills=False,
            fill_price=None,
            fill_quantity=Decimal("0"),
            reason="no executable quote: injected reference has no ask",
        )
    if request.limit_price is None or request.limit_price < reference.ask:
        return FillDecision(
            fills=False,
            fill_price=None,
            fill_quantity=Decimal("0"),
            reason="limit price not executable against injected ask",
        )
    return _full_quantity_decision(request, reference.ask)


def _decide_sell(
    request: BrokerOrderRequest, reference: PaperReferencePrice
) -> FillDecision:
    if request.order_type is OrderType.MARKET:
        return _full_quantity_decision(request, reference.last)

    # LIMIT SELL: executable only against an explicit bid leg.
    if reference.bid is None:
        return FillDecision(
            fills=False,
            fill_price=None,
            fill_quantity=Decimal("0"),
            reason="no executable quote: injected reference has no bid",
        )
    if request.limit_price is None or request.limit_price > reference.bid:
        return FillDecision(
            fills=False,
            fill_price=None,
            fill_quantity=Decimal("0"),
            reason="limit price not executable against injected bid",
        )
    return _full_quantity_decision(request, reference.bid)
