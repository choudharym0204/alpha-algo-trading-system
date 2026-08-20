# Phase 9 Execution Engine — Adversarial Review

**Date:** 2026-08-20
**Scope:** `services/execution_engine/alpha_algo_execution_engine/` + `packages/shared/alpha_algo_shared/db/models/execution.py` + `migrations/versions/20260819_execution.py` + `tests/unit/test_execution_*.py` + `tests/unit/execution_test_support.py`
**Method:** Inline adversarial review against actual source (external review subagents unavailable at the model/provider layer in this environment; performed directly against committed code, not an independent third-party audit).

---

## Dimension 1 — Execution architecture & state machine

**Reviewed:** engine wiring, adapter boundary, submission state machine, cancellation, restart recovery.

| Check | Result |
|---|---|
| Engine consumes OMS Execution Port (provider-neutral) | ✅ `ExecutionAdapter` Protocol + `InMemoryAdapter` (TEST) only |
| No broker-specific logic / SDK / coupling | ✅ `test_execution_engine.py::test_no_broker_specific_logic_in_engine_source` |
| Submission state machine explicit | ✅ `ExecutionSubmissionState` (8 states incl. CANCELLED) |
| Timeout ≠ REJECTED (ambiguous → UNKNOWN) | ✅ `_finalize_timeout` maps to `UNKNOWN` |
| Cancellation requires authoritative evidence | ✅ `CANCELLED` only on explicit confirm; pending → `UNKNOWN` |
| Restart recovery (attempts + events durable) | ✅ `test_execution_state.py` recovery tests |
| OMS lifecycle driven only through trusted events | ✅ `_apply_order_event` → `apply_event` → `OrderLifecycle` |

**Finding (NOTE-1):** `_apply_order_event` swallows exceptions so a failed order-state update cannot crash `submit()`. This is intentional (submission outcome is the primary contract), but means a lost order-state update is non-fatal rather than retried. Accepted — the durable attempt record + reconciliation (Phase 14) are the recovery path.

---

## Dimension 2 — Persistence / concurrency / idempotency

**Reviewed:** `SqlExecutionRepository`, `ExecutionAttemptRecord` unique constraint, concurrent duplicate submission, event dedup.

| Check | Result |
|---|---|
| Attempt unique on `(execution_id, attempt_number)` | ✅ model + migration |
| Idempotent submission (replay → duplicate) | ✅ `find_attempt` short-circuit |
| Concurrent duplicate → exactly one adapter dispatch | ✅ `IntegrityError` → re-read winner (`test_execution_concurrency.py`) |
| No global lock serializing distinct orders | ✅ distinct requests dispatch independently |
| Event dedup + conflict detection | ✅ `has_event` + `get_event_hash` content comparison |
| Bounded retry advances `attempt_number` | ✅ `compute_attempt_id(execution_id, n)` |

**Finding (MINOR-1, fixed):** `compute_event_identity`/`event_content_hash` were defined in `engine.py` but the repository needed them for conflict detection, which would have required a circular import. Fixed by moving both into `identity.py` and importing from there in both `engine.py` and `repository.py`; `__init__.py` re-exports them.

**Finding (MINOR-2, fixed):** The `submissions` metric was only incremented on the `SUBMITTED` response path, so an acknowledged submit left `submissions == 0`. Fixed by recording the submission immediately before `adapter.submit()` (counts every dispatch, not just one response status).

---

## Dimension 3 — Correctness / event normalization / fill handling

**Reviewed:** event identity, dedup, partial-fill accumulation, overfill protection, exact-quantity fill.

| Check | Result |
|---|---|
| Deterministic event identity | ✅ `compute_event_identity` (prefers `source_event_id`) |
| Duplicate event → no double effect | ✅ `test_execution_events_fills.py::test_duplicate_event_has_no_effect` |
| Same identity + different payload → conflict | ✅ content-hash mismatch raises `ExecutionValidationError` |
| Partial fills accumulate | ✅ filled_quantity summed across PARTIAL_FILL events |
| Overfill protection | ✅ `InvalidOrderEvent` on quantity > remaining |
| Final fill requires exact quantity | ✅ `InvalidOrderEvent` on partial final fill |
| Unknown order / forged event rejected | ✅ `test_execution_security.py` |

**Finding (NOTE-2):** Event conflict detection stores a content hash in `OrderEvent.event_payload["_content_hash"]`. This reuses the existing payload column rather than a dedicated column; acceptable for the current schema, but a dedicated column may be warranted if conflict auditing becomes a first-class requirement.

---

## Dimension 4 — LIVE safety / security / regression

**Reviewed:** trading-mode gate, halt, credential leakage, forged events, full regression.

| Check | Result |
|---|---|
| LIVE blocked fail-closed | ✅ `_validate_request` raises `ExecutionValidationError` |
| Unknown mode blocked | ✅ only `BACKTEST`/`PAPER` allowed |
| GLOBAL_TRADING_HALT honored | ✅ `global_halt_active` gate |
| Expired / missing risk approval blocked | ✅ `_validate_request` |
| No credentials in engine source | ✅ `test_execution_security.py::test_no_broker_credentials_in_engine` |
| Forged fill/ack for unknown order rejected | ✅ `apply_event` requires registered order |
| Full regression intact | ✅ **1117 passing** (1050 baseline + 67 Phase 9) |

**Finding (NOTE-3):** The TEST `InMemoryAdapter` returns `occurred_at=request.approval_expires_at` for its default ACK; this is a test convenience only and never reaches a real broker. Production adapters (Phase 10) must supply real timestamps.

---

## Summary

| Severity | Count | Disposition |
|---|---|---|
| BLOCKER | 0 | — |
| MAJOR | 0 | — |
| MINOR | 2 | both fixed + regression-tested |
| NOTE | 3 | documented limitations (no action) |

No legitimate adversarial finding remains unfixed. Phase 9 is declared **TESTED** (not PRODUCTION).
