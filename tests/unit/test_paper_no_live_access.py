from __future__ import annotations

"""Structural safety tests for the paper trading foundation.

The paper package may import broker-adapter contracts and execution-engine
events (it implements the BrokerAdapter Protocol and emits BrokerOrderEvents),
but it must NOT import risk-engine internals, backtesting, network, environment,
randomness, or persistence machinery, and it must never enable or reference
LIVE trading.
"""

import ast
import inspect
import sys
from pathlib import Path

from alpha_algo_paper_trading import (
    PaperBrokerAdapter,
    PaperOrderBook,
    PaperPosition,
    PaperReferencePrice,
)

PACKAGE_ROOT = (
    Path(__file__).resolve().parents[2]
    / "services"
    / "paper_trading"
    / "alpha_algo_paper_trading"
)

# Top-level modules the paper package is allowed to import.
ALLOWED_IMPORTS = {
    "__future__",
    "collections",
    "dataclasses",
    "datetime",
    "decimal",
    "typing",
    "uuid",
    "alpha_algo_broker_adapters",
    "alpha_algo_execution_engine",
    "alpha_algo_paper_trading",
}

BANNED_IMPORTS = {
    "alpha_algo_backtesting",
    "alpha_algo_risk_engine",
    "alpha_algo_strategies",
    "alpha_algo_contracts",
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

# Identifiers that would imply live/broker/credential or fake-result surface.
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
                    # The injected clock is the ONLY timestamp source (ADR-0007);
                    # zero wall-clock sites are allowed.
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
        ("PaperBrokerAdapter", set(dir(PaperBrokerAdapter))),
        ("PaperOrderBook", set(dir(PaperOrderBook))),
        ("PaperPosition", set(dir(PaperPosition))),
        ("PaperReferencePrice", set(dir(PaperReferencePrice))),
        ("package", set(dir(sys.modules["alpha_algo_paper_trading"]))),
    )
    for surface_name, surface in surfaces:
        for banned in BANNED_IDENTIFIERS:
            assert banned not in surface, (
                f"{surface_name} exposes banned identifier {banned!r}"
            )


def test_constructors_take_no_credentials_or_io() -> None:
    for cls in (PaperBrokerAdapter, PaperOrderBook):
        signature = inspect.signature(cls.__init__)
        for parameter in signature.parameters:
            assert "credential" not in parameter
            assert "secret" not in parameter
            assert "token" not in parameter
            assert "env" not in parameter
            assert "broker" not in parameter
            assert "path" not in parameter
            assert "session" not in parameter


def test_paper_broker_constructor_requires_clock_and_reference_prices() -> None:
    signature = inspect.signature(PaperBrokerAdapter.__init__)
    assert "clock" in signature.parameters
    assert "reference_prices" in signature.parameters
    # No defaults: both are required (no wall-clock fallback, no empty mapping
    # that silently means "no data").
    assert signature.parameters["clock"].default is inspect.Parameter.empty
    assert (
        signature.parameters["reference_prices"].default is inspect.Parameter.empty
    )


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


def test_paper_adapter_cannot_enable_live_trading() -> None:
    adapter = PaperBrokerAdapter(clock=lambda: None, reference_prices={})
    assert adapter.capabilities.supports_live_trading is False


def test_paper_book_has_no_mode_selection_surface() -> None:
    # The book takes no trading mode anywhere: PAPER is enforced by identity
    # check in submit(), and the book's own types pin TradingMode.PAPER.
    signature = inspect.signature(PaperOrderBook.submit)
    assert "trading_mode" not in signature.parameters
