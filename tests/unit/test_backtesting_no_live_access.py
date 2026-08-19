from __future__ import annotations

import ast
import sys
from pathlib import Path

from alpha_algo_backtesting import (
    BacktestInput,
    BacktestSession,
    BacktestTradingMode,
    DataReplayCursor,
    SimulationClock,
)

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "backtesting" / "alpha_algo_backtesting"

# Top-level modules the backtesting package is allowed to import.
ALLOWED_IMPORTS = {
    "__future__",
    "dataclasses",
    "datetime",
    "decimal",
    "enum",
    "hashlib",
    "typing",
    "uuid",
    "alpha_algo_backtesting",
    "alpha_algo_contracts",
}

BANNED_IMPORTS = {
    "alpha_algo_broker_adapters",
    "alpha_algo_execution_engine",
    "alpha_algo_strategies",
    "alpha_algo_risk_engine",
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
}

# Identifiers that would imply trading semantics or live/broker access.
BANNED_IDENTIFIERS = {
    "fill",
    "order",
    "pnl",
    "position",
    "execute",
    "simulate",
    "broker",
    "credential",
    "live",
    "paper",
    "place_order",
    "submit_order",
}


def _module_files() -> list[Path]:
    return sorted(PACKAGE_ROOT.glob("*.py"))


def test_package_imports_are_allowlisted() -> None:
    problems: list[str] = []
    for path in _module_files():
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


def test_package_has_no_wall_clock_or_banned_stdlib_usage() -> None:
    problems: list[str] = []
    wall_clock_sites: list[str] = []
    for path in _module_files():
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                if node.value.id == "datetime" and node.attr == "now":
                    # The audit-clock default in session.py is the one
                    # documented exception; it never feeds simulation math.
                    wall_clock_sites.append(f"{path.name}:{node.lineno}")
                if node.value.id == "time" and node.attr in {"time", "monotonic", "perf_counter", "sleep"}:
                    problems.append(f"{path.name}: wall-clock/time usage {node.value.id}.{node.attr}")
                if node.value.id == "os" and node.attr in {"environ", "getenv", "system"}:
                    problems.append(f"{path.name}: environment access os.{node.attr}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"open", "eval", "exec"}:
                problems.append(f"{path.name}: forbidden call {node.func.id}")

    # At most one wall-clock site (the audit-clock default) is allowed, and
    # it must live in session.py.
    assert len(wall_clock_sites) <= 1, f"wall-clock sites: {wall_clock_sites}"
    if wall_clock_sites:
        assert wall_clock_sites[0].startswith("session.py"), wall_clock_sites

    assert not problems, "\n".join(problems)


def test_session_exposes_no_trading_or_broker_surface() -> None:
    session_names = set(dir(BacktestSession))
    input_names = set(dir(BacktestInput))
    cursor_names = set(dir(DataReplayCursor))
    clock_names = set(dir(SimulationClock))
    package_names = set(dir(sys.modules["alpha_algo_backtesting"]))

    for surface_name, surface in (
        ("BacktestSession", session_names),
        ("BacktestInput", input_names),
        ("DataReplayCursor", cursor_names),
        ("SimulationClock", clock_names),
        ("package", package_names),
    ):
        for banned in BANNED_IDENTIFIERS:
            assert banned not in surface, f"{surface_name} exposes banned identifier {banned!r}"


def test_session_constructor_takes_no_credentials_or_io() -> None:
    import inspect

    signature = inspect.signature(BacktestSession.__init__)

    for parameter in signature.parameters:
        assert "credential" not in parameter
        assert "secret" not in parameter
        assert "token" not in parameter
        assert "env" not in parameter
        assert "broker" not in parameter
        assert "path" not in parameter
        assert "session" not in parameter


def test_package_contains_no_embedded_data_assets() -> None:
    data_extensions = {".csv", ".json", ".parquet", ".feather", ".pkl", ".pickle", ".db", ".sqlite"}
    assets = [p for p in PACKAGE_ROOT.rglob("*") if p.suffix in data_extensions]

    assert assets == [], f"embedded data assets found: {assets}"


def test_backtest_mode_cannot_select_live_or_paper() -> None:
    assert "PAPER" not in [member.value for member in BacktestTradingMode]
    assert "LIVE" not in [member.value for member in BacktestTradingMode]
