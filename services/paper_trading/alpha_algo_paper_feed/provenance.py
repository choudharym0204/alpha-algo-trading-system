"""Source identity and audit trail for converted market-data records.

The snapshot type produced by ``alpha_algo_paper_feed.mapping``
(``PaperReferencePrice``) deliberately carries no broker-origin fields:
provenance is a feed concern, not a simulator-input concern (ADR-0007
defines ``PaperReferencePrice`` as "caller-owned simulation input").
``provenance_of`` exposes the source identity separately so the audit trail
and the P3-003 dedup key ``(source_broker, source_sequence)`` survive the
conversion without altering the P8-001 surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from alpha_algo_contracts import MarketTick

from alpha_algo_paper_feed.errors import PaperFeedError

__all__ = ["TickProvenance", "provenance_of"]


def _require_timezone(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True)
class TickProvenance:
    """Audit trail for one converted tick (source identity + dedup key).

    ``(source_broker, source_sequence)`` is the P3-003 dedup key: a caller
    side dedup keys identically to ``alpha_algo_market_data``. All timestamps
    are timezone-aware (contract guarantee; enforced here defensively for
    ``model_construct`` bypasses).
    """

    instrument_id: UUID
    exchange: str
    symbol: str
    source_broker: str
    source_sequence: str
    timestamp: datetime
    received_at: datetime

    def __post_init__(self) -> None:
        for field_name in ("exchange", "symbol", "source_broker", "source_sequence"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        _require_timezone(self.timestamp, "timestamp")
        _require_timezone(self.received_at, "received_at")


def provenance_of(tick: MarketTick) -> TickProvenance:
    """Expose a tick's source identity for audit and reconciliation.

    The dedup key is ``(source_broker, source_sequence)``, matching
    ``alpha_algo_market_data.DuplicateTickDetector``, so caller-side dedup
    keys identically to P3-003. Pure and stateless: identical input yields
    identical provenance.
    """
    if not isinstance(tick, MarketTick):
        raise PaperFeedError(
            "paper market-data feed v1 accepts MarketTick only; "
            "MarketCandle is unsupported and non-tick input is rejected"
        )
    return TickProvenance(
        instrument_id=tick.instrument_id,
        exchange=tick.exchange,
        symbol=tick.symbol,
        source_broker=tick.source_broker,
        source_sequence=tick.source_sequence,
        timestamp=tick.timestamp,
        received_at=tick.received_at,
    )
