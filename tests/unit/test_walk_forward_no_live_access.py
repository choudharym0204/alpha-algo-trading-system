from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

from alpha_algo_walk_forward import (
    DEGRADATION_THRESHOLD,
    DEPENDENCY_CV_THRESHOLD,
    LOW_TRADE_COUNT_THRESHOLD,
    MAX_RETURN_SANITY_BOUND,
    MIN_PERIODS_FOR_ASSESSMENT,
    OverfittingAssessment,
    OverfittingFlag,
    OverfittingRisk,
    WalkForwardAggregate,
    WalkForwardConfig,
    WalkForwardError,
    WalkForwardResult,
    WalkForwardWindow,
    WindowBacktestResult,
    aggregate_periods,
    assess_overfitting,
    build_windows,
    run_walk_forward,
)

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "backtesting" / "alpha_algo_walk_forward"

# Top-level modules the harness is allowed to import. It composes the verified
# P7-001 foundation and the P7-002 engine plus the P3-002 market-data
# contracts, and nothing else. Note: no math, no statistics, no uuid, no
# hashlib, no pydantic, no I/O, no randomness.
ALLOWED_IMPORTS = {
    "__future__",
    "dataclasses",
    "datetime",
    "decimal",
    "enum",
    "typing",
    "alpha_algo_backtesting",
    "alpha_algo_backtest_engine",
    "alpha_algo_contracts",
    "alpha_algo_walk_forward",
}

BANNED_IMPORTS = {
    "alpha_algo_broker_adapters",
    "alpha_algo_execution_engine",
    "alpha_algo_strategies",
    "alpha_algo_risk_engine",
    "alpha_algo_market_data",
    "alpha_algo_paper_trading",
    "alpha_algo_paper_feed",
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
    "pathlib",
    "json",
    "csv",
    "math",
    "statistics",
}

# Harness-domain identifiers that would imply live/broker/persistence/
# reporting/clock/optimization/strategy surfaces. The walk-forward core
# vocabulary (window, train, validation, test, period, aggregate, degradation,
# overfit, risk, flag, threshold, runner, coverage) is legitimate and is
# deliberately NOT banned. "reject" is banned so no-auto-reject is
# structurally enforced; "optimiz" preserves the P7-002 precedent.
BANNED_IDENTIFIERS = {
    "live",
    "paper",
    "broker",
    "credential",
    "secret",
    "token",
    "password",
    "fetch",
    "subscribe",
    "stream",
    "cache",
    "session",
    "connect",
    "network",
    "request",
    "optimiz",
    "report",
    "persist",
    "save",
    "load",
    "clock",
    "now",
    "env",
    "path",
    "db",
    "submit",
    "strategy",
    "signal",
    "indicator",
    "monte",
    "deploy",
    "execute",
    "promote",
    "reject",
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


def test_package_has_no_wall_clock_random_or_environment_usage() -> None:
    problems: list[str] = []
    for path in _module_files():
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                if node.value.id == "datetime" and node.attr in {"now", "utcnow"}:
                    problems.append(f"{path.name}: wall-clock site datetime.{node.attr}")
                if node.value.id == "time" and node.attr in {"time", "monotonic", "perf_counter", "sleep"}:
                    problems.append(f"{path.name}: time usage time.{node.attr}")
                if node.value.id == "random" and node.attr in {"random", "uniform", "randint", "choice", "shuffle", "sample"}:
                    problems.append(f"{path.name}: randomness random.{node.attr}")
                if node.value.id == "os" and node.attr in {"environ", "getenv", "system"}:
                    problems.append(f"{path.name}: environment access os.{node.attr}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"open", "eval", "exec", "input", "breakpoint"}:
                problems.append(f"{path.name}: forbidden call {node.func.id}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "uuid" and node.func.attr == "uuid4":
                    problems.append(f"{path.name}: uuid4 call site")

    assert not problems, "\n".join(problems)


def test_package_surfaces_expose_no_live_or_broker_identifiers() -> None:
    surfaces = {
        "package": set(dir(sys.modules["alpha_algo_walk_forward"])),
        "WalkForwardConfig": set(dir(WalkForwardConfig)),
        "WalkForwardWindow": set(dir(WalkForwardWindow)),
        "WindowBacktestResult": set(dir(WindowBacktestResult)),
        "WalkForwardResult": set(dir(WalkForwardResult)),
        "WalkForwardAggregate": set(dir(WalkForwardAggregate)),
        "OverfittingAssessment": set(dir(OverfittingAssessment)),
        "OverfittingFlag": set(dir(OverfittingFlag)),
        "OverfittingRisk": set(dir(OverfittingRisk)),
        "WalkForwardError": set(dir(WalkForwardError)),
    }
    for surface_name, surface in surfaces.items():
        for banned in BANNED_IDENTIFIERS:
            assert banned not in surface, f"{surface_name} exposes banned identifier {banned!r}"


def test_harness_functions_take_no_credentials_io_or_mode_parameters() -> None:
    functions = (build_windows, run_walk_forward, aggregate_periods, assess_overfitting)
    for function in functions:
        params = set(inspect.signature(function).parameters)
        for parameter in params:
            for banned in BANNED_IDENTIFIERS:
                assert banned not in parameter, f"{function.__name__} parameter {parameter!r} contains banned identifier {banned!r}"
        for banned in ("mode", "policy", "seed", "clock", "now"):
            assert banned not in params, f"{function.__name__} parameter set contains banned knob {banned!r}"
        for name, parameter in inspect.signature(function).parameters.items():
            assert parameter.default is inspect.Parameter.empty, f"{function.__name__} parameter {name} has a default"
            assert parameter.kind is inspect.Parameter.KEYWORD_ONLY, f"{function.__name__} parameter {name} must be keyword-only"


def test_package_contains_no_embedded_data_assets() -> None:
    data_extensions = {".csv", ".json", ".parquet", ".feather", ".pkl", ".pickle", ".db", ".sqlite", ".npz", ".npy"}
    assets = [p for p in PACKAGE_ROOT.rglob("*") if p.suffix in data_extensions]

    assert assets == [], f"embedded data assets found: {assets}"


def test_package_never_imports_uuid_or_hashlib() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in _module_files())
    assert "uuid" not in source
    assert "hashlib" not in source


def test_no_strategy_or_executor_surface() -> None:
    for banned in (
        "alpha_algo_strategies",
        "alpha_algo_execution_engine",
        "alpha_algo_broker_adapters",
        "alpha_algo_paper_trading",
        "alpha_algo_paper_feed",
        "alpha_algo_market_data",
        "alpha_algo_risk_engine",
    ):
        for path in _module_files():
            assert banned not in path.read_text(encoding="utf-8"), f"{path.name} references {banned}"
    # No module-level names that look like strategy/executor surfaces.
    module_names = [name for name in dir(sys.modules["alpha_algo_walk_forward"]) if not name.startswith("_")]
    for banned in ("strategy", "signal", "indicator", "executor", "optimizer"):
        assert banned not in " ".join(module_names), f"module surface contains {banned}"


def test_package_defines_no_trading_modes() -> None:
    for path in _module_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name.endswith("Mode"):
                raise AssertionError(f"{path.name} defines a Mode class {node.name!r}")


def test_docstring_hypothetical_results_framing() -> None:
    docstring = sys.modules["alpha_algo_walk_forward"].__doc__ or ""
    normalized = " ".join(docstring.split())
    assert "hypothetical" in normalized
    assert "not evidence of profitability" in normalized


def test_threshold_constants_are_fixed_and_typed() -> None:
    assert type(DEGRADATION_THRESHOLD) is type(MAX_RETURN_SANITY_BOUND) is type(DEPENDENCY_CV_THRESHOLD)
    assert type(LOW_TRADE_COUNT_THRESHOLD) is int
    assert type(MIN_PERIODS_FOR_ASSESSMENT) is int
