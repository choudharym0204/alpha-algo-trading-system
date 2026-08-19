from __future__ import annotations

"""Structural safety tests for the paper market-data feed.

The feed is a pure conversion bridge: it may import contracts
(``alpha_algo_contracts``) and the paper foundation types
(``alpha_algo_paper_trading``), but it must NOT import network, environment,
randomness, persistence, broker-adapter, execution-engine, risk-engine, or
pydantic machinery, and it must never expose LIVE or fake-result surface.
"""

import ast
import inspect
import sys
from pathlib import Path

from alpha_algo_paper_feed import (
    TICK_REFERENCE_POLICY,
    PaperFeedError,
    TickProvenance,
    provenance_of,
    tick_to_reference,
)

PACKAGE_ROOT = (
    Path(__file__).resolve().parents[2]
    / "services"
    / "paper_trading"
    / "alpha_algo_paper_feed"
)

# Top-level modules the feed package is allowed to import.
ALLOWED_IMPORTS = {
    "__future__",
    "dataclasses",
    "datetime",
    "decimal",
    "typing",
    "uuid",
    "alpha_algo_contracts",
    "alpha_algo_paper_trading",
    "alpha_algo_paper_feed",
}

BANNED_IMPORTS = {
    "alpha_algo_backtesting",
    "alpha_algo_risk_engine",
    "alpha_algo_strategies",
    "alpha_algo_market_data",
    "alpha_algo_broker_adapters",
    "alpha_algo_execution_engine",
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

# Identifiers that would imply live/broker/credential/fake-result or
# fill/order/execution surface (mirrors P8-001 plus feed-specific bans).
BANNED_IDENTIFIERS = {
    "live",
    "pnl",
    "slippage",
    "commission",
    "credential",
    "secret",
    "token",
    "password",
    "equity",
    "leverag",
    "fill",
    "order",
    "execute",
    "submit",
    "broker",
    "fetch",
    "subscribe",
    "stream",
    "cache",
    "session",
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
                    problems.append(f"{path.name}:{node.lineno} datetime.{node.attr}")
                if node.value.id == "random" and node.attr in {
                    "random",
                    "uniform",
                    "randint",
                    "choice",
                    "gauss",
                }:
                    problems.append(f"{path.name}: random.{node.attr}")
                if node.value.id == "time" and node.attr in {
                    "time",
                    "monotonic",
                    "perf_counter",
                    "sleep",
                }:
                    problems.append(f"{path.name}: time.{node.attr}")
                if node.value.id == "os" and node.attr in {"environ", "getenv", "system"}:
                    problems.append(f"{path.name}: os.{node.attr}")
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in {"open", "eval", "exec"}
            ):
                problems.append(f"{path.name}: forbidden call {node.func.id}")

    assert not problems, "\n".join(problems)


def test_package_surfaces_expose_no_live_or_fake_result_identifiers() -> None:
    surfaces = (
        ("package", set(dir(sys.modules["alpha_algo_paper_feed"]))),
        ("TickProvenance", set(dir(TickProvenance))),
        ("tick_to_reference", set(dir(tick_to_reference))),
        ("provenance_of", set(dir(provenance_of))),
    )
    for surface_name, surface in surfaces:
        for banned in BANNED_IDENTIFIERS:
            assert banned not in surface, (
                f"{surface_name} exposes banned identifier {banned!r}"
            )


def test_functions_take_no_credentials_io_or_mode_parameters() -> None:
    for func in (tick_to_reference, provenance_of):
        signature = inspect.signature(func)
        assert len(signature.parameters) == 1
        for parameter in signature.parameters.values():
            assert parameter.default is inspect.Parameter.empty
            for banned in (
                "mode",
                "source",
                "clock",
                "now",
                "credential",
                "secret",
                "token",
                "env",
                "path",
                "session",
                "policy",
            ):
                assert banned not in parameter.name


def test_package_contains_no_embedded_data_assets() -> None:
    data_extensions = {
        ".csv",
        ".json",
        ".parquet",
        ".feather",
        ".pkl",
        ".pickle",
        ".db",
        ".sqlite",
    }
    assets = [p for p in PACKAGE_ROOT.rglob("*") if p.suffix in data_extensions]

    assert assets == [], f"embedded data assets found: {assets}"


def test_feed_does_not_re_export_paper_types() -> None:
    # P8-001 owns PaperReferencePrice; the feed consumes it, never re-exports.
    assert "PaperReferencePrice" not in dir(sys.modules["alpha_algo_paper_feed"])
