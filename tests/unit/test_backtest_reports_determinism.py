from __future__ import annotations

import os
import random
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from alpha_algo_contracts import MarketTick

from alpha_algo_backtest_engine import (
    CostModel,
    IntentSide,
    IntentType,
    OrderIntent,
    run_backtest,
)
from alpha_algo_backtesting import BacktestInput

from alpha_algo_backtest_reports import build_report

INSTRUMENT = UUID("00000000-0000-0000-0000-000000000001")


def utc(y: int, mo: int, d: int, h: int = 9, mi: int = 0, s: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, s, tzinfo=timezone.utc)


def tick(ts: datetime, ltp: str) -> MarketTick:
    return MarketTick(
        instrument_id=INSTRUMENT,
        exchange="NSE",
        symbol="TEST",
        timestamp=ts,
        ltp=Decimal(ltp),
        source_broker="unit",
        source_sequence=f"seq-{ts.isoformat()}",
        received_at=ts,
    )


def order(side: IntentSide, decided_at: datetime) -> OrderIntent:
    return OrderIntent(side=side, order_type=IntentType.MARKET, quantity=Decimal("10"), decided_at=decided_at)


def fixture_a() -> object:
    records = (
        tick(utc(2026, 1, 1, 9, 0), "100"),
        tick(utc(2026, 1, 1, 9, 1), "100"),
        tick(utc(2026, 1, 1, 9, 2), "101"),
        tick(utc(2026, 1, 1, 9, 3), "100"),
        tick(utc(2026, 1, 1, 9, 4), "99.6"),
        tick(utc(2026, 1, 1, 9, 5), "100"),
        tick(utc(2026, 1, 1, 9, 6), "100.2"),
        tick(utc(2026, 1, 1, 9, 7), "100.2"),
    )
    intents = (
        order(IntentSide.BUY, utc(2026, 1, 1, 9, 0, 30)),
        order(IntentSide.SELL, utc(2026, 1, 1, 9, 1, 30)),
        order(IntentSide.BUY, utc(2026, 1, 1, 9, 2, 30)),
        order(IntentSide.SELL, utc(2026, 1, 1, 9, 3, 30)),
        order(IntentSide.BUY, utc(2026, 1, 1, 9, 4, 30)),
        order(IntentSide.SELL, utc(2026, 1, 1, 9, 5, 30)),
    )
    return run_backtest(
        inputs=BacktestInput(dataset_id="ds", source="unit", records=records),
        intents=intents,
        cost_model=CostModel(Decimal("0"), Decimal("0")),
        initial_capital=Decimal("100000"),
    )


def test_identical_run_identical_report() -> None:
    run = fixture_a()
    assert build_report(run, risk_free_rate_per_period=Decimal("0")) == build_report(
        run, risk_free_rate_per_period=Decimal("0")
    )


def test_no_cross_run_state() -> None:
    first = build_report(fixture_a(), risk_free_rate_per_period=Decimal("0"))
    build_report(fixture_a(), risk_free_rate_per_period=Decimal("0.01"))
    third = build_report(fixture_a(), risk_free_rate_per_period=Decimal("0"))
    assert first == third


def test_wall_clock_and_random_never_consulted(monkeypatch) -> None:
    def boom(*args, **kwargs):
        raise AssertionError("wall clock or randomness must not be consulted")

    monkeypatch.setattr(time, "time", boom)
    monkeypatch.setattr(time, "monotonic", boom)
    monkeypatch.setattr(time, "perf_counter", boom)
    monkeypatch.setattr(time, "sleep", boom)
    monkeypatch.setattr(random, "random", boom)
    monkeypatch.setattr(random, "uniform", boom)
    monkeypatch.setattr(random, "randint", boom)

    report = build_report(fixture_a(), risk_free_rate_per_period=Decimal("0"))
    assert report.metrics.trade_count == 3


def test_report_fields_are_decimal_not_float() -> None:
    report = build_report(fixture_a(), risk_free_rate_per_period=Decimal("0"))
    assert type(report.statistics.net_profit) is Decimal
    assert type(report.statistics.expectancy) is Decimal
    assert type(report.risk.calmar_ratio) is Decimal
    assert type(report.metrics.gross_profit) is Decimal
    assert type(report.statistics.max_consecutive_wins) is int
    assert isinstance(report.statistics.average_trade_duration, timedelta)


def test_report_is_frozen() -> None:
    report = build_report(fixture_a(), risk_free_rate_per_period=Decimal("0"))
    for attr in ("input_sha256", "initial_capital", "metrics"):
        with pytest.raises(Exception):
            setattr(report, attr, "x")


def test_reports_suite_passes_under_different_hash_seeds() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    files = [
        "tests/unit/test_backtest_reports_statistics.py",
        "tests/unit/test_backtest_reports_curves.py",
        "tests/unit/test_backtest_reports_risk.py",
        "tests/unit/test_backtest_reports_report.py",
        "tests/unit/test_backtest_reports_no_live_access.py",
    ]
    for seed in ("1", "999"):
        env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONDONTWRITEBYTECODE": "1"}
        result = subprocess.run(
            [sys.executable, "-m", "pytest", *files, "-p", "no:cacheprovider", "-q"],
            cwd=str(repo_root),
            env=env,
            capture_output=True,
            text=True,
            timeout=240,
        )
        assert result.returncode == 0, (
            f"seed {seed} failed\nSTDOUT:\n{result.stdout[-2000:]}\nSTDERR:\n{result.stderr[-2000:]}"
        )
