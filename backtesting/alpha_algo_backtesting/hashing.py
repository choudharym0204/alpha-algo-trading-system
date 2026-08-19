from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from alpha_algo_contracts import CandleTimeframe, MarketCandle, MarketTick

MANIFEST_SCHEMA_VERSION = "1"
CANONICAL_SERIALIZER_VERSION = "1"

_CANDLE_FIELDS = (
    "instrument_id",
    "exchange",
    "symbol",
    "timeframe",
    "candle_start",
    "open_price",
    "high_price",
    "low_price",
    "close_price",
    "volume",
    "source_broker",
    "generated_at",
)

_TICK_FIELDS = (
    "instrument_id",
    "exchange",
    "symbol",
    "timestamp",
    "ltp",
    "volume",
    "bid",
    "ask",
    "bid_quantity",
    "ask_quantity",
    "source_broker",
    "source_sequence",
    "received_at",
)


def _canonical_value(value: object) -> str:
    """Canonical string form of one record field value.

    Note: ``Decimal`` values are rendered with ``str()``, which preserves
    the exponent representation. Numerically equal prices with different
    trailing-zero representations (``Decimal("100.50")`` vs
    ``Decimal("100.5")``) therefore serialize differently and produce
    different digests: content identity is representation-precise by
    design (the manifest promises exactly the history that was given).
    Producers that need cross-loader stable hashes must normalize price
    representation at the producer boundary.
    """
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat(timespec="microseconds")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, CandleTimeframe):
        return str(value.value)
    if value is None:
        return "None"
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value)
    raise TypeError(f"unsupported canonical value type: {type(value).__name__}")


def canonical_serialize(record: MarketCandle | MarketTick) -> str:
    """Serialize one market record into a canonical, platform-stable string.

    The serialization is owned by this repository (explicit field order,
    Decimal -> str, UTC-normalized ISO-8601 timestamps, explicit ``None``)
    and must never be replaced with ``model_dump()``, ``str(dict)`` or
    ``hash()``: those are version- and hash-seed-sensitive and would silently
    invalidate archived manifests.
    """
    if isinstance(record, MarketCandle):
        fields = _CANDLE_FIELDS
    elif isinstance(record, MarketTick):
        fields = _TICK_FIELDS
    else:
        raise TypeError(f"unsupported record type: {type(record).__name__}")
    return "|".join(_canonical_value(getattr(record, field)) for field in fields)


def canonical_bytes(records: tuple[MarketCandle | MarketTick, ...]) -> bytes:
    """Canonical UTF-8 byte serialization of an ordered record sequence."""
    return "\n".join(canonical_serialize(record) for record in records).encode("utf-8")


def content_sha256(records: tuple[MarketCandle | MarketTick, ...]) -> str:
    """Deterministic content digest (sha256 hex) over explicit historical inputs.

    The digest covers the record payloads only: run identifiers, audit
    timestamps, and caller metadata are deliberately excluded so the same
    history always hashes identically across runs and platforms. Digest
    identity is representation-precise for Decimal prices (see
    ``_canonical_value``).
    """
    return hashlib.sha256(canonical_bytes(records)).hexdigest()
