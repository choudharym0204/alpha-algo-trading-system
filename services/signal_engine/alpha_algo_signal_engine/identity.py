"""Deterministic signal identity + content hashing.

Identity is NOT derived from the random ``signal_id`` — it is a SHA-256 over
immutable attributes so the system can distinguish a true new signal from a
duplicate, a replay, a retried delivery, and a conflicting signal with the same
apparent identity.

``identity_key`` (determines "same logical signal"):
    strategy_id | strategy_version | strategy_config_hash | instrument_id |
    action | event_timestamp

``content_hash`` (determines "same content", for conflict detection):
    confidence | reason | event_timestamp | metadata (canonical JSON)

The event timestamp is read from ``metadata["event_timestamp"]`` (attached by the
Phase-4 runtime's enrichment step) and falls back to ``signal.timestamp`` when a
signal is ingested without that marker. This keeps Phase-5 identity consistent
with Phase-4's in-memory dedup key.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from alpha_algo_contracts import StrategySignal

_EVENT_TS_KEY = "event_timestamp"
_CODE_HASH_KEY = "strategy_code_hash"
_RUN_ID_KEY = "strategy_run_id"


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def event_timestamp(signal: StrategySignal) -> datetime:
    raw = signal.metadata.get(_EVENT_TS_KEY)
    if raw is None:
        return signal.timestamp
    if isinstance(raw, datetime):
        return raw
    return datetime.fromisoformat(str(raw))


def compute_signal_identity_key(signal: StrategySignal) -> str:
    raw = "|".join(
        [
            str(signal.strategy_id),
            signal.strategy_version,
            signal.strategy_config_hash,
            str(signal.instrument_id),
            signal.action.value,
            event_timestamp(signal).isoformat(),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def compute_signal_content_hash(signal: StrategySignal) -> str:
    payload = {
        "confidence": str(signal.confidence),
        "reason": signal.reason,
        "timestamp": event_timestamp(signal).isoformat(),
        "metadata": canonical_json(signal.metadata),
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def code_hash_from(signal: StrategySignal) -> str | None:
    value = signal.metadata.get(_CODE_HASH_KEY)
    return str(value) if value is not None else None


def run_id_from(signal: StrategySignal) -> str | None:
    value = signal.metadata.get(_RUN_ID_KEY)
    return str(value) if value is not None else None
