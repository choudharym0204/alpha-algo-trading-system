"""Phase 5 ingestion validation / filtering (re-validates at the engine boundary)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from signal_test_support import FakeDirectory, make_record, make_signal

from alpha_algo_contracts import SignalAction, StrategySignal
from alpha_algo_signal_engine.errors import SignalRejectedError, TradingModeError
from alpha_algo_signal_engine.validation import SignalIngestionValidator


def _validator(records=None, clock=None):
    return SignalIngestionValidator(
        FakeDirectory(records), clock=clock or (lambda: datetime.now(UTC))
    )


def _valid_signal(strategy_id, config_hash, **kwargs):
    return make_signal(strategy_id=strategy_id, config_hash=config_hash, **kwargs)


def test_valid_signal_passes() -> None:
    sid = uuid4()
    cfg = "a" * 64
    v = _validator([make_record(sid, config_hash=cfg)])
    result = v.validate(_valid_signal(sid, cfg), "PAPER")
    assert result.ok


def test_unknown_strategy_rejected() -> None:
    v = _validator([make_record(uuid4(), config_hash="a" * 64)])
    with pytest.raises(SignalRejectedError) as exc:
        v.validate(_valid_signal(uuid4(), "a" * 64), "PAPER")
    assert exc.value.reason == "unknown_strategy"


def test_disabled_strategy_rejected() -> None:
    sid = uuid4()
    cfg = "a" * 64
    v = _validator([make_record(sid, config_hash=cfg, enabled=False)])
    with pytest.raises(SignalRejectedError) as exc:
        v.validate(_valid_signal(sid, cfg), "PAPER")
    assert exc.value.reason == "disabled_strategy"


def test_wrong_version_rejected() -> None:
    sid = uuid4()
    cfg = "a" * 64
    v = _validator([make_record(sid, version="1.0.0", config_hash=cfg)])
    with pytest.raises(SignalRejectedError) as exc:
        v.validate(_valid_signal(sid, cfg, version="2.0.0"), "PAPER")
    assert exc.value.reason == "strategy_version_mismatch"


def test_wrong_config_hash_rejected() -> None:
    sid = uuid4()
    v = _validator([make_record(sid, config_hash="a" * 64)])
    with pytest.raises(SignalRejectedError) as exc:
        v.validate(_valid_signal(sid, "b" * 64), "PAPER")
    assert exc.value.reason == "config_hash_mismatch"


def test_wrong_code_hash_rejected() -> None:
    sid = uuid4()
    cfg = "a" * 64
    v = _validator([make_record(sid, config_hash=cfg, code_hash="real-code-hash")])
    with pytest.raises(SignalRejectedError) as exc:
        v.validate(_valid_signal(sid, cfg, code_hash="spoofed-code-hash"), "PAPER")
    assert exc.value.reason == "code_hash_mismatch"


def test_invalid_instrument_rejected() -> None:
    sid = uuid4()
    cfg = "a" * 64
    subscribed = uuid4()
    v = _validator([make_record(sid, config_hash=cfg, instruments=frozenset({subscribed}))])
    with pytest.raises(SignalRejectedError) as exc:
        v.validate(_valid_signal(sid, cfg, instrument_id=uuid4()), "PAPER")
    assert exc.value.reason == "invalid_instrument"


def test_missing_traceability_rejected() -> None:
    sid = uuid4()
    cfg = "a" * 64
    v = _validator([make_record(sid, config_hash=cfg)])
    signal = _valid_signal(sid, cfg).model_copy(update={"metadata": {}})
    with pytest.raises(SignalRejectedError) as exc:
        v.validate(signal, "PAPER")
    assert exc.value.reason == "missing_traceability"


def test_future_timestamp_rejected() -> None:
    sid = uuid4()
    cfg = "a" * 64
    now = datetime.now(UTC)
    v = _validator([make_record(sid, config_hash=cfg)], clock=lambda: now)
    future = now + timedelta(hours=1)
    with pytest.raises(SignalRejectedError) as exc:
        v.validate(_valid_signal(sid, cfg, timestamp=future, event_timestamp=future), "PAPER")
    assert exc.value.reason == "future_timestamp"


def test_future_event_timestamp_rejected() -> None:
    sid = uuid4()
    cfg = "a" * 64
    now = datetime.now(UTC)
    v = _validator([make_record(sid, config_hash=cfg)], clock=lambda: now)
    past = now - timedelta(hours=1)
    future = now + timedelta(hours=1)
    # signal.timestamp is valid (past), but a forged future event_timestamp is
    # the authoritative traceability time and must be rejected (spoof-proof).
    with pytest.raises(SignalRejectedError) as exc:
        v.validate(_valid_signal(sid, cfg, timestamp=past, event_timestamp=future), "PAPER")
    assert exc.value.reason == "future_timestamp"


# --- defense-in-depth (pydantic already rejects these at the contract boundary;
# the validator adds a second, spoof-proof layer via model_construct) ---------


def _construct(**overrides) -> StrategySignal:
    base = dict(
        signal_id=uuid4(),
        strategy_id=uuid4(),
        strategy_version="1.0.0",
        strategy_config_hash="a" * 64,
        instrument_id=uuid4(),
        action=SignalAction.BUY,
        timestamp=datetime.now(UTC),
        confidence=Decimal("0.8"),
        reason="test",
        metadata={"event_timestamp": datetime.now(UTC).isoformat()},
    )
    base.update(overrides)
    return StrategySignal.model_construct(**base)


def test_invalid_action_rejected_at_boundary() -> None:
    sid = uuid4()
    cfg = "a" * 64
    v = _validator([make_record(sid, config_hash=cfg)])
    signal = _construct(strategy_id=sid, strategy_config_hash=cfg, action="NOT_AN_ACTION")
    with pytest.raises(SignalRejectedError) as exc:
        v.validate(signal, "PAPER")
    assert exc.value.reason == "invalid_action"


def test_invalid_confidence_rejected_at_boundary() -> None:
    sid = uuid4()
    cfg = "a" * 64
    v = _validator([make_record(sid, config_hash=cfg)])
    signal = _construct(strategy_id=sid, strategy_config_hash=cfg, confidence=Decimal("1.5"))
    with pytest.raises(SignalRejectedError) as exc:
        v.validate(signal, "PAPER")
    assert exc.value.reason == "invalid_confidence"


def test_naive_timestamp_rejected_at_boundary() -> None:
    sid = uuid4()
    cfg = "a" * 64
    v = _validator([make_record(sid, config_hash=cfg)])
    signal = _construct(strategy_id=sid, strategy_config_hash=cfg, timestamp=datetime(2026, 1, 1))
    with pytest.raises(SignalRejectedError) as exc:
        v.validate(signal, "PAPER")
    assert exc.value.reason == "invalid_timestamp"


def test_contract_rejects_invalid_action_string() -> None:
    with pytest.raises(ValidationError):
        StrategySignal(
            strategy_id=uuid4(),
            strategy_version="1.0.0",
            strategy_config_hash="a" * 64,
            instrument_id=uuid4(),
            action="NOT_AN_ACTION",
            timestamp=datetime.now(UTC),
            confidence=Decimal("0.8"),
            reason="test",
        )


def test_contract_rejects_naive_timestamp() -> None:
    with pytest.raises(ValidationError):
        StrategySignal(
            strategy_id=uuid4(),
            strategy_version="1.0.0",
            strategy_config_hash="a" * 64,
            instrument_id=uuid4(),
            action=SignalAction.BUY,
            timestamp=datetime(2026, 1, 1),
            confidence=Decimal("0.8"),
            reason="test",
        )


def test_live_mode_rejected() -> None:
    sid = uuid4()
    cfg = "a" * 64
    v = _validator([make_record(sid, config_hash=cfg)])
    with pytest.raises(TradingModeError):
        v.validate(_valid_signal(sid, cfg), "LIVE")
