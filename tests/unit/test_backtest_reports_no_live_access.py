from __future__ import annotations

import ast
import inspect
from pathlib import Path

import alpha_algo_backtest_reports as reports

from alpha_algo_backtest_reports import (
    BacktestReport,
    BacktestReportError,
    BacktestReportMetricsError,
    DrawdownPoint,
    PeriodBucket,
    PeriodGranularity,
    ReturnPoint,
    RiskMetrics,
    TradeReconstruction,
    TradeStatistics,
    build_report,
    bucket_performance,
    build_trade_reconstructions,
    compute_calmar_ratio,
    compute_downside_deviation,
    compute_drawdown_series,
    compute_period_returns,
    compute_risk_metrics,
    compute_sortino_ratio,
    compute_trade_statistics,
)

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "backtesting" / "alpha_algo_backtest_reports"

# The report package is allowed to import the stdlib primitives plus the
# P7-001 foundation, the P7-002 engine, and itself. No uuid/hashlib/math/
# statistics/pydantic/os/pathlib/json/csv/I-O. Note: the package's own
# `statistics.py` shadows the stdlib name within the package namespace; the
# stdlib `statistics` module is NOT in this allowlist.
ALLOWED_IMPORTS = {
    "__future__",
    "dataclasses",
    "datetime",
    "decimal",
    "enum",
    "typing",
    "alpha_algo_backtesting",
    "alpha_algo_backtest_engine",
    "alpha_algo_backtest_reports",
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

# "report" is deliberately NOT banned: it is this package's own core domain
# (report.py, BacktestReport, build_report) — the inverse of P7-003, which
# banned it for the walk-forward harness where reports were foreign. "order"
# is also NOT banned: it is legitimate backtest vocabulary (OrderIntent) and
# the structural guarantee against order-execution is the import allowlist.
BANNED_IDENTIFIERS = {
    "strategy", "signal", "indicator", "monte", "deploy", "execute",
    "promote", "reject", "optimiz",
    "persist", "save", "load", "dump", "db", "sql", "sqlalchemy", "psycopg",
    "postgres", "sqlite", "live", "paper", "broker", "credential", "secret",
    "token", "password", "api_key",
    "fetch", "subscribe", "stream", "cache", "session", "connect", "network",
    "request", "clock", "now", "env", "environ", "path", "submit",
}

EXACT_KNOBS = {"mode", "source", "policy", "seed", "clock", "now"}


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


def test_no_wall_clock_random_or_environment_usage() -> None:
    problems: list[str] = []
    for path in _module_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                if node.value.id == "datetime" and node.attr in {"now", "utcnow", "today"}:
                    problems.append(f"{path.name}: wall-clock datetime.{node.attr}")
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


def _surface_names(obj: object) -> set[str]:
    names = set(dir(obj))
    annotations = getattr(obj, "__annotations__", None)
    if isinstance(annotations, dict):
        names.update(annotations.keys())
    return names


def test_surfaces_expose_no_live_or_broker_identifiers() -> None:
    surfaces = {
        "package": set(dir(reports)),
        "BacktestReport": _surface_names(BacktestReport),
        "TradeReconstruction": _surface_names(TradeReconstruction),
        "TradeStatistics": _surface_names(TradeStatistics),
        "RiskMetrics": _surface_names(RiskMetrics),
        "DrawdownPoint": _surface_names(DrawdownPoint),
        "PeriodBucket": _surface_names(PeriodBucket),
        "ReturnPoint": _surface_names(ReturnPoint),
        "PeriodGranularity": _surface_names(PeriodGranularity),
        "BacktestReportError": _surface_names(BacktestReportError),
        "BacktestReportMetricsError": _surface_names(BacktestReportMetricsError),
    }
    for surface_name, surface in surfaces.items():
        for banned in BANNED_IDENTIFIERS:
            assert banned not in surface, f"{surface_name} exposes banned identifier {banned!r}"


def test_functions_take_no_credentials_io_or_mode_parameters() -> None:
    funcs = (
        build_report,
        build_trade_reconstructions,
        compute_trade_statistics,
        compute_risk_metrics,
        compute_sortino_ratio,
        compute_calmar_ratio,
        compute_period_returns,
        compute_drawdown_series,
        compute_downside_deviation,
        bucket_performance,
    )
    for func in funcs:
        for name in inspect.signature(func).parameters:
            for banned in BANNED_IDENTIFIERS:
                assert banned not in name, f"{func.__name__} parameter {name!r} contains banned identifier {banned!r}"
            for knob in EXACT_KNOBS:
                assert knob != name, f"{func.__name__} parameter uses banned knob {knob!r}"

    rf_param = inspect.signature(build_report).parameters["risk_free_rate_per_period"]
    assert rf_param.kind is inspect.Parameter.KEYWORD_ONLY


def test_package_contains_no_embedded_data_assets() -> None:
    data_extensions = {".csv", ".json", ".parquet", ".feather", ".pkl", ".pickle", ".db", ".sqlite", ".npz", ".npy"}
    assets = [p for p in PACKAGE_ROOT.rglob("*") if p.suffix in data_extensions]
    assert assets == [], f"embedded data assets found: {assets}"


def test_package_never_imports_uuid_or_hashlib() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in _module_files())
    assert "uuid" not in source
    assert "hashlib" not in source


def test_no_live_persistence_or_strategy_surface() -> None:
    # Defense-in-depth on top of the import allowlist: no full live/strategy/
    # persistence service package name may appear anywhere in the source.
    source = "\n".join(path.read_text(encoding="utf-8") for path in _module_files())
    for token in (
        "alpha_algo_broker_adapters",
        "alpha_algo_execution_engine",
        "alpha_algo_strategies",
        "alpha_algo_risk_engine",
        "alpha_algo_market_data",
        "alpha_algo_paper_trading",
        "alpha_algo_paper_feed",
    ):
        assert token not in source, f"live/persistence service token {token!r} appears in source"


def test_package_defines_no_trading_modes() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in _module_files())
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name.endswith("Mode"):
            raise AssertionError(f"report package must not define a trading mode class ({node.name})")


def test_public_docstrings_hypothetical_framing() -> None:
    problems: list[str] = []
    for path in _module_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        nodes: list = []
        if ast.get_docstring(tree) is not None:
            nodes.append(("module", path.name, ast.get_docstring(tree)))
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("_"):
                    continue
                doc = ast.get_docstring(node)
                if doc is not None:
                    nodes.append((node.name, path.name, doc))
        for name, file, doc in nodes:
            normalized = " ".join(doc.split())
            if "hypothetical" not in normalized:
                problems.append(f"{file}:{name} docstring missing 'hypothetical'")
            if "not evidence of profitability" not in normalized:
                problems.append(f"{file}:{name} docstring missing 'not evidence of profitability'")
    assert not problems, "\n".join(problems)
