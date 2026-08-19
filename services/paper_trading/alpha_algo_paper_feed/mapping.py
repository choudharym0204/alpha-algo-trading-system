"""Pure conversion of market-data records into paper reference snapshots.

This is a PAPER-only bridge (P8-002): it converts one caller-supplied,
already-validated ``MarketTick`` into a caller-owned
``alpha_algo_paper_trading.types.PaperReferencePrice`` snapshot that the paper
simulator consumes to decide fills (ADR-0007 boundary preserved).

The feed never fetches, never subscribes, never streams, never embeds sample
data, never reads the wall clock, and never invents quote legs. It is a pure,
stateless function of its single argument: the same tick always yields the
same snapshot (ADR-0006/0007). Duplicate and out-of-order ticks are outside
the pure conversion by design; callers dedup on the provenance key
``(source_broker, source_sequence)`` (P3-003 convention), and a stateful
facade with an injected clock is a later task, not v1.

v1 accepts ``MarketTick`` only. ``MarketCandle`` is rejected with a typed
error: candles carry no executable bid/ask legs (every LIMIT order would
silently reject) and ``close_price`` is an interval aggregate, not a
point-in-time last price. Candle support, if ever added, must be a separate
function with a fixed documented policy (see v2 decision memo in
``outputs/alpha-algo-trading-system/ARCHITECTURE_DECISIONS.md``, ADR-0008).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from alpha_algo_contracts import MarketTick
from alpha_algo_paper_trading.types import PaperReferencePrice

from alpha_algo_paper_feed.errors import PaperFeedError

#: Fixed, auditable v1 mapping policy. Changing this constant is a breaking
#: contract change, not an implementation detail (mirrors ADR-0006 manifest
#: conventions: explicit, documented, owned by the repository).
TICK_REFERENCE_POLICY = (
    "v1: instrument_id->instrument_id, ltp->last, bid->bid|None, ask->ask|None, "
    "timestamp->reference_at; legs never synthesized; identity by instrument_id; "
    "reject non-Decimal, non-finite, non-positive, naive-timestamp, bid>ask, "
    "last-outside-spread input"
)

__all__ = ["TICK_REFERENCE_POLICY", "tick_to_reference"]


def _require_finite(value: Decimal, field_name: str) -> None:
    if not value.is_finite():
        raise PaperFeedError(f"{field_name} must be finite, got {value!r}")


def _require_decimal(value: object, field_name: str) -> None:
    if not isinstance(value, Decimal):
        raise PaperFeedError(
            f"{field_name} must be Decimal, got {type(value).__name__}"
        )


def tick_to_reference(tick: MarketTick) -> PaperReferencePrice:
    """Convert one validated ``MarketTick`` into a ``PaperReferencePrice``.

    Mapping (fixed, v1): ``instrument_id -> instrument_id``, ``ltp -> last``,
    ``bid -> bid`` (or ``None``), ``ask -> ask`` (or ``None``),
    ``timestamp -> reference_at``. ``volume`` / ``bid_quantity`` /
    ``ask_quantity`` / ``exchange`` / ``symbol`` / ``source_broker`` /
    ``source_sequence`` / ``received_at`` are deliberately not mapped into the
    snapshot; see ``alpha_algo_paper_feed.provenance.provenance_of`` for the
    audit trail.

    Raises ``PaperFeedError`` (never repairs, never degrades) when the input
    is not a ``MarketTick`` (including ``MarketCandle`` — unsupported in v1),
    any price is not ``Decimal``, not finite, or not positive, the timestamp
    is naive, or the quote is incoherent (``bid > ask``; ``last`` outside
    ``[bid, ask]`` when both legs are present). Quote legs are never
    synthesized from ``last``.

    Pure and stateless: no clock, no randomness, no I/O, no state across
    calls; identical input yields identical output (ADR-0006/0007).
    """
    if not isinstance(tick, MarketTick):
        raise PaperFeedError(
            "paper market-data feed v1 accepts MarketTick only; "
            "MarketCandle is unsupported (candles carry no executable bid/ask "
            "legs and close_price is an interval aggregate, not a tradable "
            "last price)"
        )

    _require_decimal(tick.ltp, "ltp")
    if tick.bid is not None:
        _require_decimal(tick.bid, "bid")
    if tick.ask is not None:
        _require_decimal(tick.ask, "ask")

    _require_finite(tick.ltp, "ltp")
    if tick.bid is not None:
        _require_finite(tick.bid, "bid")
    if tick.ask is not None:
        _require_finite(tick.ask, "ask")

    if tick.ltp <= Decimal("0"):
        raise PaperFeedError("ltp must be positive")
    if tick.bid is not None and tick.bid <= Decimal("0"):
        raise PaperFeedError("bid must be positive")
    if tick.ask is not None and tick.ask <= Decimal("0"):
        raise PaperFeedError("ask must be positive")

    if not isinstance(tick.timestamp, datetime):
        raise PaperFeedError(
            f"timestamp must be datetime, got {type(tick.timestamp).__name__}"
        )
    if tick.timestamp.tzinfo is None or tick.timestamp.utcoffset() is None:
        raise PaperFeedError("timestamp must be timezone-aware")

    if not isinstance(tick.instrument_id, UUID):
        raise PaperFeedError(
            f"instrument_id must be UUID, got {type(tick.instrument_id).__name__}"
        )

    if tick.bid is not None and tick.ask is not None and tick.bid > tick.ask:
        raise PaperFeedError("bid cannot exceed ask")
    if (
        tick.bid is not None
        and tick.ask is not None
        and not (tick.bid <= tick.ltp <= tick.ask)
    ):
        raise PaperFeedError("last must lie within the bid/ask spread when both legs are present")

    return PaperReferencePrice(
        instrument_id=tick.instrument_id,
        last=tick.ltp,
        bid=tick.bid,
        ask=tick.ask,
        reference_at=tick.timestamp,
    )
