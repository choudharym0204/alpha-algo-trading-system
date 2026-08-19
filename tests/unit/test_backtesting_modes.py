from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from alpha_algo_backtesting import BacktestInput, BacktestSession, BacktestTradingMode
from alpha_algo_contracts import CandleTimeframe, MarketCandle

FIXED_NOW = datetime(2026, 8, 14, 10, 0, tzinfo=UTC)
INSTRUMENT_ID = UUID("00000000-0000-0000-0000-000000000001")
STEP = timedelta(minutes=1)


def _candle(minute: int) -> MarketCandle:
    start = datetime(2026, 1, 2, 9, minute, tzinfo=UTC)
    return MarketCandle(
        instrument_id=INSTRUMENT_ID,
        exchange="TESTEX",
        symbol="TEST.NS",
        timeframe=CandleTimeframe.ONE_MINUTE,
        candle_start=start,
        open_price=Decimal("100.00"),
        high_price=Decimal("101.00"),
        low_price=Decimal("99.00"),
        close_price=Decimal("100.50"),
        volume=100,
        source_broker="test-source",
        generated_at=start,
    )


def _input() -> BacktestInput:
    return BacktestInput(
        dataset_id="ds-001",
        source="synthetic_test_fixture",
        records=(_candle(0), _candle(1), _candle(2)),
    )


def _session(**overrides: object) -> BacktestSession:
    return BacktestSession(
        inputs=_input(),
        step=STEP,
        audit_clock=lambda: FIXED_NOW,
        **overrides,  # type: ignore[arg-type]
    )


def test_backtest_mode_has_exactly_one_member() -> None:
    assert list(BacktestTradingMode) == [BacktestTradingMode.BACKTEST]


def test_session_is_mode_locked_to_backtest() -> None:
    session = _session()

    assert session.mode == BacktestTradingMode.BACKTEST
    with pytest.raises(AttributeError):
        session.mode = "LIVE"  # type: ignore[assignment]


def test_session_rejects_non_backtest_mode() -> None:
    with pytest.raises(ValueError, match="only run in BACKTEST mode"):
        BacktestSession(
            inputs=_input(),
            step=STEP,
            trading_mode="PAPER",  # type: ignore[arg-type]
        )


def test_session_is_deterministic_across_run_ids() -> None:
    first = _session(run_id=UUID("00000000-0000-0000-0000-000000000010"))
    second = _session(run_id=UUID("00000000-0000-0000-0000-000000000011"))

    assert first.manifest() == second.manifest()
    assert first.audit().run_id != second.audit().run_id


def test_session_audit_record_is_complete() -> None:
    session = _session()

    audit = session.audit()

    assert audit.mode == BacktestTradingMode.BACKTEST
    assert audit.created_at == FIXED_NOW
    assert audit.start_at == datetime(2026, 1, 2, 9, 0, tzinfo=UTC)
    assert audit.end_at == datetime(2026, 1, 2, 9, 2, tzinfo=UTC)
    assert audit.step == STEP
    assert audit.input_manifest.record_count == 3
    assert len(audit.input_manifest.content_sha256) == 64
    assert audit.caller_metadata == {}


def test_session_clock_advances_deterministically() -> None:
    session = _session()

    assert session.current_time() == datetime(2026, 1, 2, 9, 0, tzinfo=UTC)
    session.advance(2)
    assert session.current_time() == datetime(2026, 1, 2, 9, 2, tzinfo=UTC)


def test_session_replays_records_in_order() -> None:
    session = _session()

    assert session.peek_next() == _candle(0)
    assert session.next_record() == _candle(0)
    assert session.next_record() == _candle(1)
    assert session.records_consumed == 2
    assert session.is_exhausted is False
    assert session.next_record() == _candle(2)
    assert session.is_exhausted is True
    assert session.peek_next() is None
    assert session.next_record() is None


def test_session_audit_clock_must_be_timezone_aware() -> None:
    with pytest.raises(ValueError, match="audit clock must return a timezone-aware datetime"):
        BacktestSession(
            inputs=_input(),
            step=STEP,
            audit_clock=lambda: datetime(2026, 8, 14, 10, 0),
        )


def test_session_rejects_non_positive_step() -> None:
    with pytest.raises(ValueError, match="step must be positive"):
        BacktestSession(inputs=_input(), step=timedelta(0))
    with pytest.raises(ValueError, match="step must be positive"):
        BacktestSession(inputs=_input(), step=timedelta(seconds=-1))


def test_session_advance_rejects_zero() -> None:
    session = _session()

    with pytest.raises(ValueError, match="times must be a positive integer"):
        session.advance(0)


def test_session_manifest_versions_match_canonical_constants() -> None:
    from alpha_algo_backtesting import (
        CANONICAL_SERIALIZER_VERSION,
        MANIFEST_SCHEMA_VERSION,
    )

    manifest = _session().manifest()

    assert manifest.schema_version == MANIFEST_SCHEMA_VERSION
    assert manifest.serializer_version == CANONICAL_SERIALIZER_VERSION


def test_session_preserves_caller_metadata_in_audit() -> None:
    from alpha_algo_backtesting import BacktestInput

    inputs = BacktestInput(
        dataset_id="ds-001",
        source="synthetic_test_fixture",
        records=(_candle(0), _candle(1)),
        metadata={"requested_by": "unit-test", "run_label": "smoke"},
    )

    session = BacktestSession(inputs=inputs, step=STEP, audit_clock=lambda: FIXED_NOW)

    assert session.audit().caller_metadata == {"requested_by": "unit-test", "run_label": "smoke"}


def test_replay_cursor_rejects_empty_records() -> None:
    from alpha_algo_backtesting import DataReplayCursor

    with pytest.raises(ValueError, match="replay requires at least one record"):
        DataReplayCursor(())


def test_env_example_keeps_live_disabled() -> None:
    import sys
    from pathlib import Path

    env_path = Path(__file__).resolve().parents[2] / ".env.example"
    content = env_path.read_text(encoding="utf-8")

    assert "LIVE_TRADING_ENABLED=false" in content
    assert "GLOBAL_TRADING_HALT=true" in content
    assert "BROKER_CONNECTIONS_ENABLED=false" in content
    assert "EXECUTION_ENGINE_ENABLED=false" in content
    assert "DEFAULT_TRADING_MODE=PAPER" in content
