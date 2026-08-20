"""Multi-symbol portfolio input and deterministic identity (P16).

A :class:`PortfolioInput` wraps one single-instrument :class:`BacktestInput`
per symbol and validates the universe (non-empty, unique symbols, distinct
instrument identities). It derives a deterministic combined content digest
over the sorted ``(symbol, input_sha256)`` pairs so the portfolio run is
reproducible and cacheable.

The single-instrument ``BacktestInput`` remains the atomic unit: the
portfolio layer composes many of them and never revalidates or rewrites the
individual inputs' own validation.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from alpha_algo_backtesting import BacktestInput

from alpha_algo_backtest_portfolio.errors import PortfolioBacktestError

__all__ = ["PORTFOLIO_INPUT_POLICY", "PortfolioInput"]

PORTFOLIO_INPUT_POLICY = (
    "A portfolio is a non-empty tuple of single-instrument BacktestInputs "
    "with unique symbols (and unique instrument identities). Its content "
    "digest is sha256 over sorted 'symbol=content_sha256' pairs — order-stable "
    "and independent of the caller's input order."
)


@dataclass(frozen=True)
class PortfolioInput:
    """One or more single-instrument inputs forming a portfolio universe."""

    inputs: tuple[BacktestInput, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.inputs, tuple) or not self.inputs:
            raise PortfolioBacktestError("inputs must be a non-empty tuple of BacktestInput")
        if not all(isinstance(item, BacktestInput) for item in self.inputs):
            raise PortfolioBacktestError("inputs must contain only BacktestInput")
        symbols = [item.records[0].symbol for item in self.inputs]
        if len(set(symbols)) != len(symbols):
            raise PortfolioBacktestError("portfolio symbols must be unique")
        instruments = [item.records[0].instrument_id for item in self.inputs]
        if len(set(instruments)) != len(instruments):
            raise PortfolioBacktestError("portfolio instruments must be unique")

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(sorted(item.records[0].symbol for item in self.inputs))

    @property
    def symbol_inputs(self) -> dict[str, BacktestInput]:
        return {item.records[0].symbol: item for item in self.inputs}

    @property
    def content_sha256(self) -> str:
        pairs = sorted(f"{item.records[0].symbol}={item.content_sha256}" for item in self.inputs)
        return hashlib.sha256("\n".join(pairs).encode("utf-8")).hexdigest()

    @property
    def dataset_id(self) -> str:
        return "portfolio:" + ",".join(sorted(item.dataset_id for item in self.inputs))

    @property
    def source(self) -> str:
        return "portfolio:" + ",".join(sorted({item.source for item in self.inputs}))
