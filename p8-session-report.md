# P8-session-report.md — Phase 8 Order Management System (OMS)

**Date:** 2026-08-19
**Status:** COMPLETE — TESTED (not PRODUCTION)
**Predecessor:** Phase 7 (Trading Orchestrator, COMPLETE)
**Successor:** Phase 9 (Execution Engine) — NOT started

---

## 1. What was built

A complete internal Order Management System at `services/oms/alpha_algo_oms/`:

| Module | Responsibility |
|---|---|
| `validation.py` | `TradingIntent` → validated immutable `OrderSpec` (fail-closed) |
| `identity.py` | deterministic `order_identity_key` (SHA-256) + `client_order_id` + `OrderIdentity` |
| `repository.py` | transactional `Order` + `OrderEvent` persistence; COMMIT = truth; unique-constraint backstop |
| `service.py` | `OmsService` — create order, request cancellation, reads |
| `boundary.py` | `ExecutionBoundary` / `ExecutionPort` / `NoOpExecutionPort` — the OMS stops here |
| `metrics.py` | `OmsMetrics` counters (create/duplicate/conflict/reject/transition/cancel/persistence-failure) |
| `errors.py` | structured errors: `OmsError` base + validation/not-found/duplicate/conflict/risk-approval/trading-mode/invalid-transition/persistence/execution-boundary |

**Flow:** `TradingIntent → validate_intent → build_order_identity → idempotency check → transactional create (Order + initial event) → INTENT_CREATED → INTERNAL_ORDER_CREATED → SUBMISSION_REQUESTED → ExecutionBoundary`.

---

## 2. Order lifecycle

Existing 11-state `OrderLifecycle` (Phase 0) preserved unchanged. The OMS drives exactly three internal transitions:

```
INTENT_CREATED → INTERNAL_ORDER_CREATED → SUBMISSION_REQUESTED
```

The OMS never reaches `BROKER_ACKNOWLEDGED`, `PARTIALLY_FILLED`, or `FILLED`. `UNKNOWN` and `RECONCILIATION_REQUIRED` are preserved (Phase 9/14 own them). Invalid transitions raise `InvalidOrderTransition`.

---

## 3. Order identity (deterministic, collision-safe)

- `order_identity_key` = SHA-256 over (orchestration_id, signal_id, strategy_id, account_id, instrument_id, side, quantity, order_type, trading_mode, risk_approval_id).
- `client_order_id` = `ord-<orchestration_id>` (deterministic).
- `internal_order_id` = DB primary key (set explicitly from `OrderIdentity`).
- `broker_order_id` = `None` placeholder (Phase 9 assigns it).
- `correlation_id` carried through for cross-boundary traceability.

---

## 4. Idempotency / intent consumption

- **Replay** (same orchestration_id + same identity key) → returns existing order, `duplicate=True`, no second order.
- **Conflict** (same orchestration_id + different payload) → `IntentConflictError`.
- **Race backstop** — a concurrent duplicate insert raises the DB unique constraint, which `repository.create_order` converts to `OUTCOME_DUPLICATE` by re-reading the winner.

---

## 5. Transaction boundary & concurrency

- Order + initial event committed in **one** transaction; any failure rolls back with no false success (`PersistenceError`).
- `orchestration_id`, `order_identity_key`, `client_order_id`, and `risk_approval_id` are unique — the durable backstop for exactly-one-order.
- Concurrency: threaded test confirms two workers on the same intent produce exactly one logical order; distinct intents create independently (no global lock).

---

## 6. Risk approval binding & LIVE safety

- `validate_intent` re-verifies approval expiry + presence before order creation.
- `_request_submission` re-verifies expiry + approval_id again before `SUBMISSION_REQUESTED` (defense-in-depth).
- `approval_id` is hashed into `order_identity_key`, so approval reuse changes identity → conflict.
- `LIVE` / unknown trading mode → `TradingModeError` (fail-closed). `GLOBAL_TRADING_HALT` defaults to active.
- No broker SDK / credentials / API calls / real submission / cancellation calls / forged broker events.

---

## 7. Schema changes

`migrations/versions/20260819_oms.py` (down_revision = `20260819_trading_orchestrator`):

- Adds `orders.orchestration_id` (unique), `order_identity_key` (unique), `correlation_id`, `strategy_id`, `strategy_version`, `risk_approval_id` (unique), `approval_expires_at`.
- Adds indexes on `orchestration_id` and `strategy_id`.
- Also fixed a pre-existing model bug: `Index` was missing from the `sqlalchemy` import in `trading.py`.

---

## 8. Tests

- **75 new tests** across `test_oms_identity.py`, `test_oms_validation.py`, `test_oms_repository.py`, `test_oms_service.py`, `test_oms_security.py`, `test_oms_concurrency.py`, `test_oms_lifecycle.py`, `test_oms_e2e.py`.
- Coverage: identity determinism, all validation rules, transactional create/rollback, duplicate/conflict idempotency, cancel flow, state-machine integration, security (no broker/no forged fills/LIVE block), concurrency (threaded), and a full E2E `Signal → Risk → Orchestrator → OMS → SUBMISSION_REQUESTED` test that stops at the boundary.
- **Full suite: 1050 passing** (975 baseline + 75 Phase 8). No test weakening, no deletion.

---

## 9. Review

See `review.md`. Four adversarial dimensions run inline against actual source. **0 BLOCKER, 0 MAJOR, 2 MINOR (both fixed), 3 NOTE (documented).**

- MINOR-1: `Order.id` vs `internal_order_id` divergence — fixed.
- MINOR-2: missing `Index` import in `trading.py` — fixed.

---

## 10. Limitations

- Live PostgreSQL verification deferred (no Docker/PostgreSQL in this environment); tests use an in-memory store mimicking transactional + unique-constraint semantics.
- OMS re-verifies approval expiry + presence; field-level approval↔intent binding is inherited from Phase 7 (`binding_hash`), since the OMS receives the `TradingIntent` rather than the original `RiskDecision`.
- `CANCEL_REQUESTED` is a request only — actual `CANCELLED` confirmation is Phase 9/10.

---

## 11. LIVE status

**LIVE remains disabled, globally halted, fail-closed.** `GLOBAL_TRADING_HALT` stays true by default. Any LIVE order creation is rejected before submission. No LIVE credential or broker path introduced.

---

## 12. Register files

`TRADING_ENGINE_REGISTER.md`, `CURRENT_ARCHITECTURE_REGISTER.md`, and `PLATFORM_CAPABILITY_MATRIX.md` are **not present as committed files** in this repository — they were Phase-0 audit inputs whose contents are consolidated into the single active control document `IMPLEMENTATION_STATUS.md` (updated with the Phase 8 `0h` section and the `5.8 OMS` capability matrix). No new register files were fabricated.
