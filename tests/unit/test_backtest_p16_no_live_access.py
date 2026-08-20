from __future__ import annotations

import ast
from pathlib import Path

# Top-level modules the Phase 16 packages are allowed to import.
ALLOWED_IMPORTS = {
    "__future__",
    "dataclasses",
    "datetime",
    "decimal",
    "enum",
    "hashlib",
    "itertools",
    "json",
    "typing",
    "uuid",
    "alpha_algo_backtesting",
    "alpha_algo_backtest_engine",
    "alpha_algo_backtest_reports",
    "alpha_algo_contracts",
    "alpha_algo_backtest_analytics",
    "alpha_algo_backtest_quality",
    "alpha_algo_backtest_optimize",
    "alpha_algo_backtest_persistence",
    "alpha_algo_backtest_portfolio",
    "alpha_algo_backtest_latency",
}

BANNED_IMPORTS = {
    "alpha_algo_broker_adapters",
    "alpha_algo_execution_engine",
    "alpha_algo_risk_engine",
    "alpha_algo_strategies",
    "alpha_algo_oms",
    "alpha_algo_position_engine",
    "alpha_algo_portfolio_engine",
    "alpha_algo_pnl_engine",
    "alpha_algo_reconciliation_engine",
    "alpha_algo_paper_trading",
    "alpha_algo_paper_runtime",
    "requests",
    "httpx",
    "urllib",
    "socket",
    "os",
    "time",
    "random",
    "asyncio",
    "subprocess",
    "sqlalchemy",
    "pydantic",
    "numpy",
    "pandas",
}

BANNED_IDENTIFIERS = {
    "broker",
    "credential",
    "secret",
    "token",
    "live",
    "paper",
    "place_order",
    "submit_order",
}

PACKAGES = (
    "alpha_algo_backtest_analytics",
    "alpha_algo_backtest_quality",
    "alpha_algo_backtest_optimize",
    "alpha_algo_backtest_persistence",
    "alpha_algo_backtest_portfolio",
    "alpha_algo_backtest_latency",
)

BACKTESTING_ROOT = Path(__file__).resolve().parents[2] / "backtesting"


def _package_files() -> list[Path]:
    files: list[Path] = []
    for package in PACKAGES:
        directory = BACKTESTING_ROOT / package
        files.extend(sorted(directory.glob("*.py")))
    return files


def test_imports_are_allowlisted_and_no_banned() -> None:
    problems: list[str] = []
    for path in _package_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top not in ALLOWED_IMPORTS:
                        problems.append(f"{path.name}: banned import {alias.name!r}")
            elif isinstance(node, ast.ImportFrom):
                if node.module is None:
                    continue
                top = node.module.split(".")[0]
                if top not in ALLOWED_IMPORTS:
                    problems.append(f"{path.name}: banned from-import {node.module!r}")

    assert not problems, "\n".join(problems)


def test_no_wall_clock_or_random_usage() -> None:
    problems: list[str] = []
    for path in _package_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                if node.value.id == "datetime" and node.attr == "now":
                    problems.append(f"{path.name}: wall-clock datetime.now")
                if node.value.id == "time" and node.attr in {"time", "monotonic", "perf_counter", "sleep"}:
                    problems.append(f"{path.name}: time.{node.attr}")
                if node.value.id == "os" and node.attr in {"environ", "getenv", "system"}:
                    problems.append(f"{path.name}: os.{node.attr}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"open", "eval", "exec"}:
                problems.append(f"{path.name}: forbidden call {node.func.id}")

    assert not problems, "\n".join(problems)


def test_package_surfaces_have_no_live_or_broker_identifiers() -> None:
    import alpha_algo_backtest_analytics
    import alpha_algo_backtest_latency
    import alpha_algo_backtest_optimize
    import alpha_algo_backtest_persistence
    import alpha_algo_backtest_portfolio
    import alpha_algo_backtest_quality

    modules = (
        alpha_algo_backtest_analytics,
        alpha_algo_backtest_quality,
        alpha_algo_backtest_optimize,
        alpha_algo_backtest_persistence,
        alpha_algo_backtest_portfolio,
        alpha_algo_backtest_latency,
    )
    for module in modules:
        names = set(dir(module))
        for banned in BANNED_IDENTIFIERS:
            assert banned not in names, f"{module.__name__} exposes banned identifier {banned!r}"


def test_portfolio_mode_is_backtest_only() -> None:
    from alpha_algo_backtesting import BacktestTradingMode

    assert "LIVE" not in [member.value for member in BacktestTradingMode]
    assert "PAPER" not in [member.value for member in BacktestTradingMode]


def test_portfolio_result_pins_backtest_mode() -> None:
    import pytest
    from datetime import datetime, timezone
    from decimal import Decimal
    from alpha_algo_backtest_engine import CostModel
    from alpha_algo_backtest_portfolio import PortfolioEquityPoint, PortfolioResult

    with pytest.raises(Exception):
        PortfolioResult(
            mode="LIVE",  # type: ignore[arg-type]
            input_sha256="a" * 64,
            dataset_id="d",
            source="s",
            initial_capital=Decimal("100"),
            reserved_cash=Decimal("0"),
            cost_model=CostModel(Decimal("0"), Decimal("0")),
            symbols=("A",),
            intents=(),
            outcomes=(),
            trades=(),
            equity_curve=(
                PortfolioEquityPoint(
                    timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    equity=Decimal("100"),
                ),
            ),
        )
