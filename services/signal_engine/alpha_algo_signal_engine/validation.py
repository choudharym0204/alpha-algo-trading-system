"""Ingestion validation + filtering for the signal engine.

Re-validates a signal at the engine boundary so that no arbitrary caller can
bypass Phase-4 validation. It checks strategy directory membership (known /
enabled / version / config-hash / code-hash / instrument subscription) plus the
cross-field payload invariants, and enforces the trading-mode and traceability
rules. It does NOT contain risk logic (that is Phase 6).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Callable

from alpha_algo_contracts import SignalAction, StrategySignal
from alpha_algo_signal_engine.directory import StrategyDirectory
from alpha_algo_signal_engine.errors import SignalRejectedError, TradingModeError
from alpha_algo_signal_engine.identity import code_hash_from, event_timestamp

_ALLOWED_MODES = frozenset({"BACKTEST", "PAPER"})


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    reason: str = ""
    code_hash: str | None = None


class SignalIngestionValidator:
    def __init__(
        self,
        directory: StrategyDirectory,
        *,
        allowed_modes: frozenset[str] = _ALLOWED_MODES,
        clock: Callable[[], datetime] | None = None,
        future_skew: timedelta = timedelta(seconds=5),
    ) -> None:
        self._directory = directory
        self._allowed_modes = allowed_modes
        self._clock = clock or (lambda: datetime.now(UTC))
        self._future_skew = future_skew

    def validate(
        self,
        signal: StrategySignal,
        trading_mode: str,
    ) -> ValidationResult:
        # Trading-mode safety (fail-closed): LIVE is never allowed here.
        mode = trading_mode.upper()
        if mode not in self._allowed_modes:
            raise TradingModeError(f"trading mode not allowed: {mode}")

        record = self._directory.lookup(signal.strategy_id)
        if record is None:
            raise SignalRejectedError("unknown_strategy")
        if not record.enabled:
            raise SignalRejectedError("disabled_strategy")
        if signal.strategy_version != record.version:
            raise SignalRejectedError("strategy_version_mismatch")
        if signal.strategy_config_hash != record.config_hash:
            raise SignalRejectedError("config_hash_mismatch")

        # Traceability: a Phase-4-enriched signal carries its event timestamp;
        # its absence means the signal did not come through the trusted boundary.
        if "event_timestamp" not in signal.metadata:
            raise SignalRejectedError("missing_traceability")

        code_hash = code_hash_from(signal)
        if record.code_hash is not None and code_hash != record.code_hash:
            raise SignalRejectedError("code_hash_mismatch")

        if record.instruments is not None and signal.instrument_id not in record.instruments:
            raise SignalRejectedError("invalid_instrument")

        # Cross-field payload invariants (defensive; pydantic already enforces).
        if not isinstance(signal.action, SignalAction):
            raise SignalRejectedError("invalid_action")
        if not (0 <= signal.confidence <= 1):
            raise SignalRejectedError("invalid_confidence")
        if signal.timestamp.utcoffset() is None:
            raise SignalRejectedError("invalid_timestamp")
        if signal.timestamp > self._clock() + self._future_skew:
            raise SignalRejectedError("future_timestamp")
        # The authoritative event timestamp must also not be in the future
        # (spoof-proof: a forged future event_timestamp would otherwise slip
        # through the presence-only traceability gate).
        if event_timestamp(signal) > self._clock() + self._future_skew:
            raise SignalRejectedError("future_timestamp")

        return ValidationResult(ok=True, code_hash=code_hash)
