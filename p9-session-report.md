# Phase 9 — Execution Engine — Session Report

**Date:** 2026-08-20
**Scope:** `services/execution_engine/alpha_algo_execution_engine/` + `packages/shared/alpha_algo_shared/db/models/execution.py` + `migrations/versions/20260819_execution.py` + `tests/unit/test_execution_*.py` + `tests/unit/execution_test_support.py`
**Status:** COMPLETE — TESTED (not PRODUCTION)
**Full suite:** **1117 tests passing** (1050 baseline + 67 Phase 9)

---

## 1. What Phase 9 is

The Execution Engine is the provider-neutral boundary between the Phase-8 OMS and the future Phase-10 broker adapters. It consumes the OMS `ExecutionPort`, validates + dispatches the OMS-approved order to an `ExecutionAdapter`, and owns the execution lifecycle: submission state, bounded retry, timeout→UNKNOWN semantics, cancellation, and event normalization/dedup that drive the OMS `OrderLifecycle` through trusted events only.

**Explicit scope boundary:** no broker SDKs, no credentials, no real submission, no forged acks/fills, no LIVE. Phase 10 owns concrete adapters.

---

## 2. Architecture

```
OMS (Phase 8)  --ExecutionPort-->  ExecutionEngine (Phase 9)
                                        |
                              +---------+---------+
                              |                   |
                     ExecutionAdapter     ExecutionRepository
                     (provider-neutral    (execution_attempts,
                      Protocol)           order events + state)
                              |
                     InMemoryAdapter (TEST only)
```

**Modules** (`services/execution_engine/alpha_algo_execution_engine/`):

| Module | Responsibility |
|---|---|
| `adapter.py` | `ExecutionAdapter` Protocol + `ExecutionRequest`/`ExecutionResponse`/`ExecutionCapabilities` + `InMemoryAdapter` (TEST) |
| `engine.py` | `ExecutionEngine` (submit/cancel/apply_event), `ExecutionOutcome`, `ExecutionRepository` Protocol |
| `errors.py` | `FailureClass` enum + `ExecutionError` subclasses + `classify()` |
| `identity.py` | `compute_execution_id`, `compute_attempt_id`, `compute_event_identity`, `event_content_hash` |
| `state.py` | `ExecutionSubmissionState` (8 states) + `ExecutionAttempt` |
| `events.py` | `BrokerOrderEvent`, `OrderEventType`, `OrderExecutionState` (pre-existing building blocks) |
| `lifecycle.py` | `OrderLifecycle`, `OrderState` (pre-existing building blocks) |
| `submission.py` | `BrokerSubmissionGuard`, `BrokerSubmissionIntent` (pre-existing building blocks) |
| `metrics.py` | `ExecutionMetrics` counters |
| `repository.py` | `SqlExecutionRepository` (SQLAlchemy-backed) |

---

## 3. Submission state machine

```
SUBMISSION_REQUESTED → SUBMISSION_IN_PROGRESS → SUBMITTED → ACKNOWLEDGED
                              |                    |             |
                              +--> TIMEOUT (→UNKNOWN)
                              +--> REJECTED
                              +--> CANCELLED
```

- **Timeout** maps to `UNKNOWN` (the provider may have accepted the order) — never a blind retry.
- **Retry** is bounded and only for `TRANSIENT_FAILURE`; each retry advances `attempt_number` → new `attempt_id`.
- **Cancellation** requires authoritative confirmation (`CANCELLED`); pending/ambiguous cancellation preserves `UNKNOWN`.

---

## 4. Identity & idempotency

- `compute_execution_id(order_id, order_identity_key)` — deterministic SHA-256, stable across retries/restarts.
- `compute_attempt_id(execution_id, attempt_number)` — `{execution_id}-a{n}`.
- Submission idempotency: `(execution_id, attempt_number)` unique constraint + re-read-on-conflict → exactly one adapter dispatch even under concurrent duplicate submission.
- Event idempotency: `compute_event_identity` (prefers `source_event_id`), content-hash conflict detection (same identity + different payload → rejected).

---

## 5. Event normalization & fills

- `apply_event` loads the durable `OrderExecutionState`, applies the trusted `BrokerOrderEvent`, and persists the transition.
- Partial fills accumulate; overfill is rejected (`InvalidOrderEvent`).
- A final fill must match the exact remaining quantity.
- Duplicate events have no effect; conflicting duplicates (same identity, different payload) raise `ExecutionValidationError`.

---

## 6. Persistence

- `ExecutionAttemptRecord` → table `execution_attempts`, unique on `(execution_id, attempt_number)`, indexed on `order_id`.
- Migration `migrations/versions/20260819_execution.py` (down_revision = `20260819_oms`).
- `SqlExecutionRepository` persists attempts and order events; COMMIT = truth.

---

## 7. Failure classification

`FailureClass`: `TIMEOUT`, `TRANSIENT_FAILURE`, `AUTH_FAILURE`, `UNKNOWN_EXTERNAL_STATE`, `INTERNAL_FAILURE`.

- `classify(exception)` maps known exceptions to classes.
- Only `TRANSIENT_FAILURE` is retryable (`RETRYABLE_FAILURE_CLASSES`).

---

## 8. Security

- LIVE blocked fail-closed; unknown modes blocked; only `BACKTEST`/`PAPER` allowed.
- `GLOBAL_TRADING_HALT` honored.
- Expired/missing risk approval blocked.
- No broker SDK / credentials / API calls anywhere in the engine (source-scanned by tests).
- Forged events for unknown orders rejected.

---

## 9. Tests (67 new, 8 files + shared support)

| File | Focus |
|---|---|
| `test_execution_identity.py` (8) | deterministic execution/attempt/event identity |
| `test_execution_engine.py` (13) | submit validation, idempotency, response mapping, metrics |
| `test_execution_timeout_retry.py` (8) | timeout→UNKNOWN, bounded transient retry, classification |
| `test_execution_cancellation.py` (5) | cancel confirm/pending/reject/unsupported |
| `test_execution_events_fills.py` (11) | ack/reject/partial/fill, dedup, conflict, overfill |
| `test_execution_concurrency.py` (5) | concurrent duplicate submit + fills, unique backstop |
| `test_execution_security.py` (8) | LIVE block, forged events, no credentials |
| `test_execution_state.py` (10) | state machine + restart recovery |
| `test_execution_e2e.py` (2) | TradingIntent → OMS → Engine → FILLED; LIVE blocked |

Shared support: `tests/unit/execution_test_support.py` (`InMemoryExecutionRepository`, `make_request`, `make_event`).

---

## 10. Review

Four-dimension adversarial review recorded in `P9-review.md`: **0 BLOCKER, 0 MAJOR, 2 MINOR (fixed), 3 NOTE (documented)**.

---

## 11. LIVE status

- LIVE trading remains **fail-closed** — the engine refuses LIVE/unknown modes and honors the global halt.
- The `InMemoryAdapter` is an explicit TEST adapter (`provider_name="test"`, `supports_live_trading=False`), never a real broker.
- No `BROKER_ACKNOWLEDGED`/`FILLED` is ever forged; those states are reached only through trusted events (real adapter events in Phase 10, or explicit test events).

---

## 12. Register-file note

`TRADING_ENGINE_REGISTER.md`, `CURRENT_ARCHITECTURE_REGISTER.md`, and `PLATFORM_CAPABILITY_MATRIX.md` do not exist as committed files; their content is consolidated into `IMPLEMENTATION_STATUS.md` (§5.9 Execution matrix updated to TESTED, §0i added).

---

## 13. Known environment limitations

- Docker/PostgreSQL/live providers unavailable → tests use an in-memory execution store mirroring transactional + unique-constraint semantics.
- The engine ends at the `ExecutionAdapter` boundary with a TEST adapter; concrete broker adapters are Phase 10.
