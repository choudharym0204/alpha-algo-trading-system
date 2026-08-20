"""Portfolio Engine (Phase 12).

Aggregates authoritative Phase-11 position state + account/funds state +
normalized reference prices into deterministic, durable portfolio snapshots.
It is broker-independent, account- and mode-isolated, and does NOT compute P&L
(Phase 13) or reconcile (Phase 14), does NOT submit orders, and never enables
LIVE.

Source-of-truth hierarchy: Position Engine (PostgreSQL) → Funds → Reference
prices → Portfolio Engine. Missing/stale sources produce a DEGRADED / PARTIAL
portfolio, never fabricated zeros.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from time import perf_counter
from typing import Callable, Protocol
from uuid import UUID

from alpha_algo_portfolio_engine.aggregation import compute_portfolio
from alpha_algo_portfolio_engine.contracts import (
    PortfolioComputation,
    PortfolioIdentity,
    PortfolioInputs,
    PortfolioResult,
    PortfolioSnapshot,
    PortfolioStatus,
)
from alpha_algo_portfolio_engine.errors import (
    DuplicateSnapshotError,
    PortfolioModeError,
    PortfolioPersistenceError,
    PortfolioValidationError,
)
from alpha_algo_portfolio_engine.identity import (
    build_portfolio_identity,
    snapshot_content_hash,
)
from alpha_algo_portfolio_engine.metrics import PortfolioMetrics

_ALLOWED_MODES = frozenset({"BACKTEST", "PAPER"})


class PortfolioRepository(Protocol):
    """Durable portfolio snapshot store (PostgreSQL-backed)."""

    def save_snapshot(
        self,
        *,
        snapshot: PortfolioSnapshot,
        computation: PortfolioComputation,
        content_hash: str,
    ) -> PortfolioSnapshot: ...

    def load_snapshot(
        self, *, account_id: UUID, trading_mode: str, snapshot_at: datetime
    ) -> PortfolioSnapshot | None: ...

    def load_latest(
        self, *, account_id: UUID, trading_mode: str
    ) -> PortfolioSnapshot | None: ...

    def list_snapshots(
        self, *, account_id: UUID, trading_mode: str, limit: int = 100
    ) -> list[PortfolioSnapshot]: ...


class PortfolioEngine:
    def __init__(
        self,
        *,
        repository: PortfolioRepository | None = None,
        metrics: PortfolioMetrics | None = None,
        global_halt_active: Callable[[], bool] | None = None,
        max_age_seconds: int | None = None,
    ) -> None:
        self._repository = repository
        self._metrics = metrics or PortfolioMetrics()
        self._global_halt_active = global_halt_active or (lambda: True)
        self._max_age_seconds = max_age_seconds

    # ---------------------------------------------------------------- compute
    def compute(
        self,
        inputs: PortfolioInputs,
        *,
        now: datetime | None = None,
        max_age_seconds: int | None = None,
    ) -> PortfolioComputation:
        """Deterministic recomputation from authoritative inputs (restart-safe).

        Same inputs => same portfolio state. No wall-clock randomness, no
        process-local mutable state, no unordered iteration.
        """
        self._validate(inputs)
        started = perf_counter()
        computation = compute_portfolio(
            inputs=inputs,
            now=now or datetime.now(tz=UTC),
            max_age_seconds=(
                max_age_seconds
                if max_age_seconds is not None
                else self._max_age_seconds
            ),
        )
        self._metrics.record_recalculation()
        self._metrics.record_latency(perf_counter() - started)
        return computation

    # ---------------------------------------------------------------- snapshot
    def snapshot(
        self,
        inputs: PortfolioInputs,
        snapshot_at: datetime,
        *,
        max_age_seconds: int | None = None,
    ) -> PortfolioResult:
        """Compute + atomically persist one portfolio snapshot."""
        if self._repository is None:
            raise PortfolioPersistenceError("no portfolio repository configured")

        computation = self.compute(
            inputs, now=snapshot_at, max_age_seconds=max_age_seconds
        )
        snapshot = self._to_snapshot(computation)
        content_hash = snapshot_content_hash(
            account_id=computation.identity.account_id,
            trading_mode=computation.identity.trading_mode,
            snapshot_at=snapshot_at,
            gross_exposure=str(computation.gross_exposure),
            net_exposure=str(computation.net_exposure),
            long_exposure=str(computation.long_exposure),
            short_exposure=str(computation.short_exposure),
            market_value=(
                str(computation.market_value)
                if computation.market_value is not None
                else None
            ),
            cash_balance=(
                str(computation.cash_balance)
                if computation.cash_balance is not None
                else None
            ),
            position_count=computation.position_count,
        )

        try:
            persisted = self._repository.save_snapshot(
                snapshot=snapshot, computation=computation, content_hash=content_hash
            )
        except DuplicateSnapshotError:
            self._metrics.record_duplicate()
            existing = self._repository.load_snapshot(
                account_id=inputs.account_id,
                trading_mode=inputs.trading_mode,
                snapshot_at=snapshot_at,
            )
            if existing is None:
                raise PortfolioPersistenceError(
                    "snapshot duplicate but no existing snapshot found"
                )
            return PortfolioResult(
                status=existing.status,
                snapshot=existing,
                duplicate=True,
                computation=computation,
            )

        self._metrics.record_snapshot_write()
        self._record_quality(computation)
        return PortfolioResult(
            status=computation.status,
            snapshot=persisted,
            computation=computation,
        )

    # ------------------------------------------------------------------- reads
    def get_latest(
        self, *, account_id: UUID, trading_mode: str
    ) -> PortfolioSnapshot | None:
        if self._repository is None:
            return None
        return self._repository.load_latest(
            account_id=account_id, trading_mode=trading_mode
        )

    def list_snapshots(
        self, *, account_id: UUID, trading_mode: str, limit: int = 100
    ) -> list[PortfolioSnapshot]:
        if self._repository is None:
            return []
        return self._repository.list_snapshots(
            account_id=account_id, trading_mode=trading_mode, limit=limit
        )

    # --------------------------------------------------------------- internals
    def _validate(self, inputs: PortfolioInputs) -> None:
        mode = (inputs.trading_mode or "").upper()
        if mode == "LIVE":
            raise PortfolioModeError("LIVE trading is disabled (fail-closed)")
        if mode not in _ALLOWED_MODES:
            raise PortfolioModeError(f"unknown trading mode: {inputs.trading_mode}")
        if self._global_halt_active():
            raise PortfolioValidationError(
                "global trading halt is active; portfolio computation refused"
            )

    def _to_snapshot(self, c: PortfolioComputation) -> PortfolioSnapshot:
        return PortfolioSnapshot(
            snapshot_id=None,
            account_id=c.identity.account_id,
            trading_mode=c.identity.trading_mode,
            status=c.status,
            completeness=c.completeness,
            position_count=c.position_count,
            gross_exposure=c.gross_exposure,
            net_exposure=c.net_exposure,
            long_exposure=c.long_exposure,
            short_exposure=c.short_exposure,
            market_value=c.market_value,
            cash_balance=c.cash_balance,
            equity_value=c.equity_value,
            available_margin=c.available_margin,
            used_margin=c.used_margin,
            snapshot_at=c.snapshot_at,
        )

    def _record_quality(self, c: PortfolioComputation) -> None:
        if c.completeness.value == "PARTIAL":
            self._metrics.record_incomplete()
        if c.status == PortfolioStatus.DEGRADED and c.stale_instrument_ids:
            self._metrics.record_stale()
