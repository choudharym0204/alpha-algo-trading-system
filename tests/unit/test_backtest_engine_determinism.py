from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from alpha_algo_contracts import MarketTick

from alpha_algo_backtest_engine import (
    CostModel,
    IntentSide,
    IntentType,
    OrderIntent,
    compute_metrics,
    run_backtest,
)
from alpha_algo_backtesting import BacktestInput

INSTRUMENT = UUID("00000000-0000-0000-0000-000000000001")


def utc(y: int, mo: int, d: int, h: int = 9, mi: int = 0, s: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, s, tzinfo=timezone.utc)


def tick(ts: datetime, ltp: str, bid: str | None = None, ask: str | None = None) -> MarketTick:
    return MarketTick(
        instrument_id=INSTRUMENT,
        exchange="NSE",
        symbol="TEST",
        timestamp=ts,
        ltp=Decimal(ltp),
        bid=Decimal(bid) if bid is not None else None,
        ask=Decimal(ask) if ask is not None else None,
        source_broker="unit",
        source_sequence=f"seq-{ts.isoformat()}",
        received_at=ts,
    )


def order(
    side: IntentSide,
    order_type: IntentType,
    decided_at: datetime,
    quantity: str = "10",
    limit_price: str | None = None,
) -> OrderIntent:
    return OrderIntent(
        side=side,
        order_type=order_type,
        quantity=Decimal(quantity),
        decided_at=decided_at,
        limit_price=Decimal(limit_price) if limit_price is not None else None,
    )


def scenario() -> tuple[BacktestInput, tuple[OrderIntent, ...], CostModel]:
    records = (
        tick(utc(2026, 1, 1, 9, 0), "100", "99.5", "100.5"),
        tick(utc(2026, 1, 1, 9, 1), "102", "101.5", "102.5"),
        tick(utc(2026, 1, 1, 9, 2), "104", "103.5", "104.5"),
        tick(utc(2026, 1, 1, 9, 3), "101", "100.5", "101.5"),
    )
    inputs = BacktestInput(dataset_id="ds", source="unit", records=records)
    intents = (
        order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 20)),
        order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 1, 20)),
        order(IntentSide.SELL, IntentType.MARKET, utc(2026, 1, 1, 9, 2, 20)),
    )
    cost_model = CostModel(commission_per_fill=Decimal("5"), slippage_bps=Decimal("10"))
    return inputs, intents, cost_model


class TestDeterminism:
    def test_identical_inputs_identical_run(self) -> None:
        inputs, intents, cost_model = scenario()
        run_one = run_backtest(
            inputs=inputs, intents=intents, cost_model=cost_model, initial_capital=Decimal("100000")
        )
        run_two = run_backtest(
            inputs=inputs, intents=intents, cost_model=cost_model, initial_capital=Decimal("100000")
        )
        assert run_one == run_two
        assert compute_metrics(run_one, risk_free_rate_per_period=Decimal("0")) == compute_metrics(
            run_two, risk_free_rate_per_period=Decimal("0")
        )

    def test_no_cross_run_state(self) -> None:
        inputs, intents, cost_model = scenario()
        run_a = run_backtest(
            inputs=inputs, intents=intents, cost_model=cost_model, initial_capital=Decimal("100000")
        )
        # Interleave a different scenario; the first scenario must be unchanged.
        other_input = BacktestInput(
            dataset_id="other",
            source="unit",
            records=(tick(utc(2026, 2, 1, 9, 0), "50", "49.5", "50.5"),),
        )
        run_backtest(
            inputs=other_input,
            intents=(),
            cost_model=CostModel(Decimal("0"), Decimal("0")),
            initial_capital=Decimal("5000"),
        )
        run_b = run_backtest(
            inputs=inputs, intents=intents, cost_model=cost_model, initial_capital=Decimal("100000")
        )
        assert run_a == run_b

    def test_wall_clock_and_random_are_never_consulted(self, monkeypatch) -> None:
        def boom(*args, **kwargs):
            raise AssertionError("wall clock / randomness must never be consulted")

        class NoClock(datetime):
            @classmethod
            def now(cls, *args, **kwargs):
                raise AssertionError("wall clock must never be consulted")

            @classmethod
            def utcnow(cls, *args, **kwargs):
                raise AssertionError("wall clock must never be consulted")

        monkeypatch.setattr("time.time", boom)
        monkeypatch.setattr("time.monotonic", boom)
        monkeypatch.setattr("time.perf_counter", boom)
        monkeypatch.setattr("random.random", boom)
        for module in (
            "alpha_algo_backtest_engine.engine",
            "alpha_algo_backtest_engine.fills",
            "alpha_algo_backtest_engine.intents",
        ):
            monkeypatch.setattr(f"{module}.datetime", NoClock)

        inputs, intents, cost_model = scenario()
        run_obj = run_backtest(
            inputs=inputs, intents=intents, cost_model=cost_model, initial_capital=Decimal("100000")
        )
        metrics = compute_metrics(run_obj, risk_free_rate_per_period=Decimal("0"))
        assert len(run_obj.fills) == 3
        assert metrics.trade_count == 1

    def test_input_metadata_does_not_affect_result(self) -> None:
        inputs, intents, cost_model = scenario()
        with_meta = BacktestInput(
            dataset_id=inputs.dataset_id,
            source=inputs.source,
            records=inputs.records,
            metadata={"anything": "goes"},
        )
        run_plain = run_backtest(
            inputs=inputs, intents=intents, cost_model=cost_model, initial_capital=Decimal("100000")
        )
        run_meta = run_backtest(
            inputs=with_meta, intents=intents, cost_model=cost_model, initial_capital=Decimal("100000")
        )
        assert run_plain == run_meta

    def test_policy_constants_are_fixed_and_auditable(self) -> None:
        from alpha_algo_backtest_engine import (
            CANDLE_FILL_POLICY,
            CANDLE_LIMIT_NO_IMPROVEMENT,
            COMMISSION_POLICY,
            COST_ATTRIBUTION_POLICY,
            EQUITY_MARK_POLICY,
            FILL_TIMING_POLICY,
            SLIPPAGE_POLICY,
            TICK_LIMIT_FILL_POLICY,
            TICK_MARKET_FILL_POLICY,
        )

        for constant in (
            FILL_TIMING_POLICY,
            TICK_MARKET_FILL_POLICY,
            TICK_LIMIT_FILL_POLICY,
            CANDLE_FILL_POLICY,
            CANDLE_LIMIT_NO_IMPROVEMENT,
            SLIPPAGE_POLICY,
            COMMISSION_POLICY,
            EQUITY_MARK_POLICY,
            COST_ATTRIBUTION_POLICY,
        ):
            assert isinstance(constant, str) and len(constant) > 40

    def test_full_engine_suite_passes_under_different_hash_seeds(self) -> None:
        # Subprocess proof: the entire engine suite must pass under multiple
        # PYTHONHASHSEED values (commitment: hash randomization never changes
        # results). The determinism file itself is excluded from the child
        # invocation to avoid unbounded recursion.
        import os
        import subprocess
        import sys

        repo_root = Path(__file__).resolve().parents[2]
        engine_tests = [
            "tests/unit/test_backtest_engine_validation.py",
            "tests/unit/test_backtest_engine_fills.py",
            "tests/unit/test_backtest_engine_costs.py",
            "tests/unit/test_backtest_engine_ledger.py",
            "tests/unit/test_backtest_engine_metrics.py",
            "tests/unit/test_backtest_engine_no_live_access.py",
        ]
        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        for seed in ("1", "999"):
            env["PYTHONHASHSEED"] = seed
            completed = subprocess.run(
                [sys.executable, "-m", "pytest", *engine_tests, "-p", "no:cacheprovider", "-q"],
                cwd=repo_root,
                env=env,
                capture_output=True,
                text=True,
                timeout=180,
            )
            assert completed.returncode == 0, (
                f"engine suite failed under PYTHONHASHSEED={seed}:\n"
                f"{completed.stdout[-2000:]}\n{completed.stderr[-2000:]}"
            )
