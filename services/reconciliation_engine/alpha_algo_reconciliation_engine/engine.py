"""Reconciliation Engine (Phase 14).

Compares internal authoritative state against broker observations (Phase 10
normalized read models), classifies matches vs. discrepancies, persists
evidence, and produces controlled recovery actions. It **never** silently
overwrites internal financial truth — corrections route through existing
domain boundaries.

No provider-specific logic, no broker calls, no credential values. LIVE and
unknown trading modes are fail-closed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Callable, Protocol
from uuid import UUID, uuid4

from alpha_algo_reconciliation_engine.contracts import (
    Discrepancy,
    DiscrepancyKind,
    EntityType,
    ReconciliationInputs,
    ReconciliationRun,
    ReconciliationScope,
    RecoveryAction,
    ResolutionStatus,
    RunResult,
    RunStatus,
    Severity,
)
from alpha_algo_reconciliation_engine.errors import (
    DuplicateDiscrepancyError,
    ReconciliationDataError,
    ReconciliationModeError,
    ReconciliationPersistenceError,
    ReconciliationValidationError,
)
from alpha_algo_reconciliation_engine.identity import compute_discrepancy_key
from alpha_algo_reconciliation_engine.matching import (
    MatchContext,
    reconcile_executions,
    reconcile_funds,
    reconcile_orders,
    reconcile_positions,
)
from alpha_algo_reconciliation_engine.metrics import ReconciliationMetrics
from alpha_algo_reconciliation_engine.tolerance import Tolerance

_ALLOWED_MODES = frozenset({"BACKTEST", "PAPER"})


class ReconciliationRepository(Protocol):
    """Durable reconciliation store (PostgreSQL-backed)."""

    def save_run(self, *, run: ReconciliationRun) -> ReconciliationRun: ...

    def load_run(self, run_id: UUID) -> ReconciliationRun | None: ...

    def save_discrepancy(self, *, discrepancy: Discrepancy) -> Discrepancy: ...

    def load_discrepancy(self, discrepancy_key: str) -> Discrepancy | None: ...

    def list_discrepancies(
        self, *, run_id: UUID | None = None, account_id: UUID | None = None
    ) -> list[Discrepancy]: ...


class ReconciliationEngine:
    def __init__(
        self,
        *,
        repository: ReconciliationRepository | None = None,
        metrics: ReconciliationMetrics | None = None,
        global_halt_active: Callable[[], bool] | None = None,
        tolerance: Tolerance | None = None,
    ) -> None:
        self._repository = repository
        self._metrics = metrics or ReconciliationMetrics()
        self._global_halt_active = global_halt_active or (lambda: True)
        self._tolerance = tolerance or Tolerance()

    # -------------------------------------------------------------------- run
    def run(
        self,
        *,
        scope: ReconciliationScope,
        inputs: ReconciliationInputs,
        tolerance: Tolerance | None = None,
        stale_seconds: int | None = None,
        now: datetime | None = None,
    ) -> RunResult:
        if self._repository is None:
            raise ReconciliationPersistenceError("no reconciliation repository configured")

        self._guard(scope)
        now = now or datetime.now(tz=UTC)
        tol = tolerance or self._tolerance
        run_id = uuid4()
        ctx = MatchContext(
            run_id=run_id,
            account_id=scope.account_id,
            broker=scope.broker,
            trading_mode=scope.trading_mode.upper(),
        )

        discrepancies: list[Discrepancy] = []
        counts = {
            "matched": 0, "mismatched": 0, "internal_only": 0,
            "broker_only": 0, "unknown": 0, "unavailable": 0, "skipped": 0,
        }

        if "ORDERS" in scope.domains:
            r = reconcile_orders(ctx, list(inputs.orders_internal), list(inputs.orders_broker), tol)
            discrepancies += list(r.discrepancies)
            counts["matched"] += r.matched
            counts["internal_only"] += r.internal_only
            counts["broker_only"] += r.broker_only

        if "EXECUTIONS" in scope.domains:
            r = reconcile_executions(ctx, list(inputs.executions_internal), list(inputs.executions_broker), tol)
            discrepancies += list(r.discrepancies)
            counts["matched"] += r.matched
            counts["internal_only"] += r.internal_only
            counts["broker_only"] += r.broker_only

        if "POSITIONS" in scope.domains:
            r = reconcile_positions(
                ctx, list(inputs.positions_internal), list(inputs.positions_broker),
                tol, stale_seconds=stale_seconds, now=now,
            )
            discrepancies += list(r.discrepancies)
            counts["matched"] += r.matched
            counts["internal_only"] += r.internal_only
            counts["broker_only"] += r.broker_only
            counts["unknown"] += r.unknown

        if "FUNDS" in scope.domains:
            r = reconcile_funds(
                ctx, inputs.funds_internal, inputs.funds_broker,
                tol, stale_seconds=stale_seconds, now=now,
            )
            discrepancies += list(r.discrepancies)
            counts["matched"] += r.matched
            counts["unknown"] += r.unknown
            counts["unavailable"] += r.unavailable

        counts["mismatched"] = sum(1 for d in discrepancies if d.kind not in (DiscrepancyKind.STALE, DiscrepancyKind.UNKNOWN))

        # Persist discrepancies idempotently.
        persisted, conflicts = self._persist_discrepancies(discrepancies)
        counts["skipped"] = conflicts

        status = (
            RunStatus.PARTIAL
            if (counts["unavailable"] > 0 or counts["unknown"] > 0)
            else RunStatus.COMPLETED
        )

        run = ReconciliationRun(
            run_id=run_id,
            account_id=scope.account_id,
            broker=scope.broker,
            trading_mode=scope.trading_mode.upper(),
            scope=",".join(sorted(scope.domains)),
            status=status,
            started_at=now,
            completed_at=now,
            matched=counts["matched"],
            mismatched=counts["mismatched"],
            internal_only=counts["internal_only"],
            broker_only=counts["broker_only"],
            unknown=counts["unknown"],
            unavailable=counts["unavailable"],
            skipped=counts["skipped"],
            conflicts=conflicts,
        )

        saved_run = self._repository.save_run(run=run)
        self._metrics.record_run(status)

        recovery = self._recovery_actions(persisted)
        return RunResult(
            status=status, run=saved_run,
            discrepancies=tuple(persisted), recovery_actions=tuple(recovery),
        )

    # -------------------------------------------------------------- internals
    def _guard(self, scope: ReconciliationScope) -> None:
        mode = (scope.trading_mode or "").upper()
        if mode == "LIVE":
            raise ReconciliationModeError("LIVE reconciliation is disabled (fail-closed)")
        if mode not in _ALLOWED_MODES:
            raise ReconciliationModeError(f"unknown trading mode: {scope.trading_mode}")
        if self._global_halt_active():
            raise ReconciliationValidationError("global trading halt is active; reconciliation refused")
        if not scope.account_id:
            raise ReconciliationDataError("reconciliation scope requires an account_id")

    def _persist_discrepancies(self, discrepancies: list[Discrepancy]) -> tuple[list[Discrepancy], int]:
        persisted: list[Discrepancy] = []
        conflicts = 0
        for d in discrepancies:
            try:
                persisted.append(self._repository.save_discrepancy(discrepancy=d))
            except DuplicateDiscrepancyError:
                existing = self._repository.load_discrepancy(d.discrepancy_key)
                if existing is not None and existing.content_hash == d.content_hash:
                    continue  # idempotent replay — no duplicate
                conflicts += 1
                self._metrics.record_conflict()
                conflict_d = self._conflict_discrepancy(d, existing)
                try:
                    persisted.append(self._repository.save_discrepancy(discrepancy=conflict_d))
                except DuplicateDiscrepancyError:
                    pass
        return persisted, conflicts

    def _conflict_discrepancy(self, original: Discrepancy, existing: Discrepancy | None) -> Discrepancy:
        key = compute_discrepancy_key(
            account_id=original.account_id,
            entity_type=original.entity_type.value,
            entity_id=original.entity_id,
            kind=DiscrepancyKind.CONFLICT.value,
        )
        return Discrepancy(
            id=None,
            discrepancy_key=key,
            run_id=original.run_id,
            account_id=original.account_id,
            broker=original.broker,
            trading_mode=original.trading_mode,
            entity_type=original.entity_type,
            entity_id=original.entity_id,
            kind=DiscrepancyKind.CONFLICT,
            severity=Severity.HIGH,
            internal_state={"original_discrepancy_key": original.discrepancy_key, "original_content_hash": existing.content_hash if existing else None},
            broker_state={"new_content_hash": original.content_hash},
            resolution_status=ResolutionStatus.OPEN,
            content_hash=original.content_hash,
            observed_at=original.observed_at,
        )

    def _recovery_actions(self, persisted: list[Discrepancy]) -> list[RecoveryAction]:
        actions: list[RecoveryAction] = []
        for d in persisted:
            if d.entity_type == EntityType.EXECUTION and d.kind == DiscrepancyKind.BROKER_ONLY:
                actions.append(
                    RecoveryAction(
                        discrepancy_id=d.id,
                        action_type="ROUTE_BROKER_FILL",
                        target_boundary="execution_engine",
                        normalized_fill={
                            "broker_execution_id": d.broker_state.get("broker_execution_id"),
                            "quantity": d.broker_state.get("quantity"),
                            "price": d.broker_state.get("price"),
                            "side": d.broker_state.get("side"),
                            "order_id": d.broker_state.get("order_id"),
                        },
                        note="route via trusted execution boundary; do not mutate positions/pnl/portfolio directly",
                    )
                )
            elif d.kind not in (DiscrepancyKind.STALE, DiscrepancyKind.UNKNOWN, DiscrepancyKind.ROUNDING_DIFFERENCE):
                actions.append(
                    RecoveryAction(
                        discrepancy_id=d.id,
                        action_type="ESCALATE",
                        target_boundary="none",
                        note="manual review required; no automatic correction",
                    )
                )
        return actions

    # ------------------------------------------------------------------ reads
    def load_run(self, run_id: UUID) -> ReconciliationRun | None:
        if self._repository is None:
            return None
        return self._repository.load_run(run_id)

    def list_discrepancies(self, *, account_id: UUID | None = None) -> list[Discrepancy]:
        if self._repository is None:
            return []
        return self._repository.list_discrepancies(account_id=account_id)
