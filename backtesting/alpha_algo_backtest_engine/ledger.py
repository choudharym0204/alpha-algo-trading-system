"""FIFO trade ledger for the backtest simulation engine (P7-002).

Realized P&L is computed over completed FIFO lots with documented cost
attribution. The ledger is internal state used only inside ``run_backtest``;
its classes are private and never exported as public surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, localcontext

from alpha_algo_backtest_engine.costs import DECIMAL_PRECISION
from alpha_algo_backtest_engine.errors import BacktestEngineError
from alpha_algo_backtest_engine.fills import FillRecord
from alpha_algo_backtest_engine.intents import IntentSide

__all__ = ["COST_ATTRIBUTION_POLICY", "TradeRecord"]

COST_ATTRIBUTION_POLICY = (
    "FIFO lot matching: entry commission is attributed to the lot that "
    "consumed it; exit commission is split proportionally across the lots "
    "consumed by a partial exit. Realized P&L per completed lot is "
    "(exit - entry) * quantity - entry cost share - exit cost share."
)


@dataclass(frozen=True)
class TradeRecord:
    """A completed FIFO lot: one round trip from entry fill to exit fill(s)."""

    sequence: int
    entry_fill_sequence: int
    exit_fill_sequences: tuple[int, ...]
    quantity: Decimal
    entry_price: Decimal
    exit_price: Decimal
    entry_cost: Decimal
    exit_cost: Decimal
    realized_pnl: Decimal


@dataclass
class _Lot:
    entry_fill_sequence: int
    entry_price: Decimal
    total_quantity: Decimal
    remaining_quantity: Decimal
    entry_cost: Decimal
    exit_fill_sequences: list[int] = field(default_factory=list)
    weighted_exit_sum: Decimal = Decimal("0")
    entry_cost_used: Decimal = Decimal("0")
    exit_cost_used: Decimal = Decimal("0")
    realized_total: Decimal = Decimal("0")


class _FifoLedger:
    """Internal FIFO lot ledger (private; state lives only inside a run)."""

    def __init__(self) -> None:
        self._lots: list[_Lot] = []
        self._trade_sequence = 0

    def open_lot(self, fill: FillRecord) -> None:
        if fill.side is not IntentSide.BUY:
            raise BacktestEngineError("only BUY fills open lots")
        self._lots.append(
            _Lot(
                entry_fill_sequence=fill.sequence,
                entry_price=fill.fill_price,
                total_quantity=fill.quantity,
                remaining_quantity=fill.quantity,
                entry_cost=fill.commission_amount,
            )
        )

    def close_lots(self, fill: FillRecord) -> tuple[TradeRecord, ...]:
        """Match a SELL fill against the oldest open lots (FIFO).

        Returns one TradeRecord per lot completed by this fill. A partial
        exit leaves the lot open; realized P&L and costs accumulate on the
        lot until it completes.
        """
        if fill.side is not IntentSide.SELL:
            raise BacktestEngineError("only SELL fills close lots")
        remaining = fill.quantity
        completed: list[TradeRecord] = []
        with localcontext() as ctx:
            ctx.prec = DECIMAL_PRECISION
            for lot in self._lots:
                if remaining <= 0:
                    break
                if lot.remaining_quantity <= 0:
                    continue
                matched = min(remaining, lot.remaining_quantity)
                entry_share = lot.entry_cost * matched / lot.total_quantity
                exit_share = fill.commission_amount * matched / fill.quantity
                realized_share = (fill.fill_price - lot.entry_price) * matched - entry_share - exit_share
                lot.remaining_quantity -= matched
                lot.exit_fill_sequences.append(fill.sequence)
                lot.weighted_exit_sum += fill.fill_price * matched
                lot.entry_cost_used += entry_share
                lot.exit_cost_used += exit_share
                lot.realized_total += realized_share
                remaining -= matched
                if lot.remaining_quantity == 0:
                    completed.append(
                        TradeRecord(
                            sequence=self._trade_sequence,
                            entry_fill_sequence=lot.entry_fill_sequence,
                            exit_fill_sequences=tuple(lot.exit_fill_sequences),
                            quantity=lot.total_quantity,
                            entry_price=lot.entry_price,
                            exit_price=lot.weighted_exit_sum / lot.total_quantity,
                            entry_cost=lot.entry_cost_used,
                            exit_cost=lot.exit_cost_used,
                            realized_pnl=lot.realized_total,
                        )
                    )
                    self._trade_sequence += 1
        if remaining > 0:
            raise BacktestEngineError("SELL fill exceeded open position (ledger invariant violated)")
        self._lots = [lot for lot in self._lots if lot.remaining_quantity > 0]
        return tuple(completed)
