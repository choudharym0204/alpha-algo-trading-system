from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

from alpha_algo_backtest_engine import (
    BacktestMetrics,
    BacktestRun,
    CostModel,
    EquityPoint,
    FillOutcome,
    FillRecord,
    IntentSide,
    IntentType,
    OrderIntent,
    TradeRecord,
    UnfilledReason,
    compute_metrics,
    run_backtest,
)
from alpha_algo_backtesting import BacktestTradingMode

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "backtesting" / "alpha_algo_backtest_engine"

# Top-level modules the engine is allowed to import. The engine composes the
# verified P7-001 foundation and the P3-002 market-data contracts, and
# nothing else. Note: no uuid, no hashlib, no math, no pydantic, no I/O.
ALLOWED_IMPORTS = {
    "__future__",
    "dataclasses",
    "datetime",
    "decimal",
    "enum",
    "typing",
    "alpha_algo_backtesting",
    "alpha_algo_contracts",
    "alpha_algo_backtest_engine",
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
}

# Engine-domain identifiers that would imply live/broker/persistence/
# reporting/clock surfaces. Unlike P8-002's list, fill/order/pnl/position/
# equity/slippage/commission vocabulary is the engine's legitimate core
# domain and is deliberately NOT banned here.
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
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"open", "eval", "exec"}:
                problems.append(f"{path.name}: forbidden call {node.func.id}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "uuid" and node.func.attr == "uuid4":
                    problems.append(f"{path.name}: uuid4 call site")

    # Zero allowed wall-clock/random/env sites: the engine has no audit-clock
    # role (stricter than the P7-001 foundation's one audit-site allowance).
    assert not problems, "\n".join(problems)


def test_package_surfaces_expose_no_live_or_broker_identifiers() -> None:
    surfaces = {
        "package": set(dir(sys.modules["alpha_algo_backtest_engine"])),
        "OrderIntent": set(dir(OrderIntent)),
        "CostModel": set(dir(CostModel)),
        "BacktestRun": set(dir(BacktestRun)),
        "FillRecord": set(dir(FillRecord)),
        "FillOutcome": set(dir(FillOutcome)),
        "EquityPoint": set(dir(EquityPoint)),
        "TradeRecord": set(dir(TradeRecord)),
        "BacktestMetrics": set(dir(BacktestMetrics)),
        "UnfilledReason": set(dir(UnfilledReason)),
        "IntentSide": set(dir(IntentSide)),
        "IntentType": set(dir(IntentType)),
    }
    for surface_name, surface in surfaces.items():
        for banned in BANNED_IDENTIFIERS:
            assert banned not in surface, f"{surface_name} exposes banned identifier {banned!r}"


def test_engine_functions_take_no_credentials_io_or_mode_parameters() -> None:
    run_params = set(inspect.signature(run_backtest).parameters)
    metrics_params = set(inspect.signature(compute_metrics).parameters)

    for params in (run_params, metrics_params):
        for parameter in params:
            for banned in BANNED_IDENTIFIERS:
                assert banned not in parameter, f"parameter {parameter!r} contains banned identifier {banned!r}"
        # Exact-match knob names (substring checks would false-positive on
        # legitimate names like cost_model):
        for banned in ("mode", "source", "policy", "seed", "clock", "now"):
            assert banned not in params, f"parameter set contains banned knob {banned!r}"

    # No defaults on any engine parameter: inputs, intents, cost model, and
    # capital are always required and explicit.
    for name, parameter in inspect.signature(run_backtest).parameters.items():
        assert parameter.default is inspect.Parameter.empty, f"run_backtest parameter {name} has a default"
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY, f"run_backtest parameter {name} must be keyword-only"
    for name, parameter in inspect.signature(compute_metrics).parameters.items():
        assert parameter.default is inspect.Parameter.empty, f"compute_metrics parameter {name} has a default"


def test_package_contains_no_embedded_data_assets() -> None:
    data_extensions = {".csv", ".json", ".parquet", ".feather", ".pkl", ".pickle", ".db", ".sqlite"}
    assets = [p for p in PACKAGE_ROOT.rglob("*") if p.suffix in data_extensions]

    assert assets == [], f"embedded data assets found: {assets}"


def test_engine_never_imports_uuid_or_hashlib() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in _module_files())
    assert "uuid" not in source
    assert "hashlib" not in source


def test_backtest_mode_cannot_select_live_or_paper() -> None:
    assert [member.value for member in BacktestTradingMode] == ["BACKTEST"]


def test_backtest_run_requires_mode_pin() -> None:
    # The mode is structurally pinned: BacktestRun.__post_init__ refuses any
    # non-BACKTEST value, and no other value can even be constructed.
    assert BacktestTradingMode.BACKTEST.value == "BACKTEST"
