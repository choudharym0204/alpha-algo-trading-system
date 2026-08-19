"""Runtime signal validation — cross-field identity, instrument, and timestamp
checks on top of the pydantic `StrategySignal` contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Callable
from uuid import UUID

from alpha_algo_contracts import SignalAction, StrategySignal
from alpha_algo_strategy_engine.identity import StrategyIdentity


@dataclass(frozen=True)
class SignalValidationResult:
    valid: bool
    reason: str = ""


class SignalValidator:
    """Validates that a signal is traceable to a live strategy instance.

    The pydantic contract already enforces action ∈ SignalAction, confidence
    ∈ [0,1], non-blank reason, tz-aware timestamp, and a dict metadata. This
    validator enforces the cross-field identity + instrument + timestamp
    semantics that pydantic cannot.

    Timestamps are validated against the authoritative *event* timestamp when
    provided (backtest-safe), falling back to the injected clock otherwise.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] | None = None,
        future_skew: timedelta = timedelta(seconds=5),
        max_age: timedelta | None = None,
    ) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self._future_skew = future_skew
        self._max_age = max_age

    def validate(
        self,
        signal: StrategySignal,
        identity: StrategyIdentity,
        *,
        allowed_instruments: set[UUID] | None = None,
        event_timestamp: datetime | None = None,
    ) -> SignalValidationResult:
        if signal.strategy_id != identity.strategy_id:
            return SignalValidationResult(False, "strategy_id_mismatch")
        if signal.strategy_version != identity.version:
            return SignalValidationResult(False, "strategy_version_mismatch")
        if signal.strategy_config_hash != identity.config_hash:
            return SignalValidationResult(False, "config_hash_mismatch")
        if not isinstance(signal.action, SignalAction):
            return SignalValidationResult(False, "invalid_action")
        if not (0 <= signal.confidence <= 1):
            return SignalValidationResult(False, "confidence_out_of_range")
        if not signal.reason.strip():
            return SignalValidationResult(False, "missing_reason")
        if allowed_instruments is not None and signal.instrument_id not in allowed_instruments:
            return SignalValidationResult(False, "instrument_not_subscribed")

        # Authoritative event time when available; wall-clock otherwise.
        reference = event_timestamp if event_timestamp is not None else self._clock()
        if signal.timestamp - reference > self._future_skew:
            return SignalValidationResult(False, "future_timestamp")
        if self._max_age is not None and reference - signal.timestamp > self._max_age:
            return SignalValidationResult(False, "stale_timestamp")

        return SignalValidationResult(True, "ok")
