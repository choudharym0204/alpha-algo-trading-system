"""Raw-event and symbol validation (Phase 3 safety layer).

Validation is kept pure/synchronous and deterministic so it can be unit-tested
without any I/O. The engine maps these exceptions to rejection reasons.
"""

from __future__ import annotations

from alpha_algo_market_data.provider import EventKind, RawMarketEvent

_TICK_REQUIRED_KEYS = {
    "instrument_id",
    "exchange",
    "symbol",
    "timestamp",
    "ltp",
    "source_broker",
    "source_sequence",
}

_CANDLE_REQUIRED_KEYS = {
    "instrument_id",
    "exchange",
    "symbol",
    "timeframe",
    "candle_start",
    "open_price",
    "high_price",
    "low_price",
    "close_price",
    "source_broker",
    "generated_at",
}


class RawEventValidationError(Exception):
    """Raised when a raw event is malformed and cannot be normalized."""


class TickRejectedError(Exception):
    """Raised when a normalized tick/candle fails a safety check."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def validate_raw_event(
    event: RawMarketEvent,
    allowed_kinds: set[EventKind] | None = None,
) -> None:
    """Reject malformed raw events before normalization.

    Raises ``RawEventValidationError`` when the kind is unsupported, the payload
    is not a mapping, or required fields are missing.
    """
    allowed = allowed_kinds or {EventKind.TICK, EventKind.CANDLE}
    if event.kind not in allowed:
        raise RawEventValidationError(f"unsupported event kind: {event.kind}")
    if not isinstance(event.payload, dict):
        raise RawEventValidationError("payload must be a dict")
    required = (
        _TICK_REQUIRED_KEYS if event.kind == EventKind.TICK else _CANDLE_REQUIRED_KEYS
    )
    missing = required - set(event.payload)
    if missing:
        raise RawEventValidationError(f"missing payload keys: {sorted(missing)}")


def check_supported_symbol(symbol: str, allowed_symbols: set[str] | None) -> None:
    """Raise ``TickRejectedError`` when *symbol* is not in the allowlist."""
    if allowed_symbols is not None and symbol not in allowed_symbols:
        raise TickRejectedError("unsupported_instrument")
