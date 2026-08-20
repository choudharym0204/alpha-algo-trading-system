# Phase 8 OMS — Adversarial Review

**Date:** 2026-08-19
**Scope:** `services/oms/` + `migrations/versions/20260819_oms.py` + `tests/unit/test_oms_*.py` + `tests/unit/oms_test_support.py`
**Method:** Inline adversarial review against the actual source (external review subagents are unavailable at the model/provider layer in this environment; this review was performed directly against committed code, not claimed as an independent third-party audit).

---

## Dimension 1 — OMS architecture & state machine

**Reviewed:** service wiring, execution boundary, lifecycle transitions, cancel flow.

| Check | Result |
|---|---|
| Existing 11-state `OrderLifecycle` preserved | ✅ no states deleted/renamed |
| OMS stops at `ExecutionBoundary` (Execution Port) | ✅ `boundary.py` = `ExecutionPort` + `NoOpExecutionPort` only |
| Transitions explicit + validated | ✅ `OrderLifecycle.transition_to` raises `InvalidOrderTransition` |
| `CANCEL_REQUESTED` distinct from `CANCELLED` | ✅ OMS only ever requests cancellation; never reports CANCELLED |
| `UNKNOWN` / `RECONCILIATION_REQUIRED` preserved | ✅ verified in `test_oms_lifecycle.py` |
| No forced `FILLED` / `BROKER_ACKNOWLEDGED` API | ✅ `test_oms_security.py::test_oms_service_has_no_force_filled_api` |

**Finding (NOTE-1):** `OmsService._create_in_memory` runs the lifecycle without persistence. This is a test/dry-run path only; production always injects a repository. Accepted.

---

## Dimension 2 — Database / concurrency / idempotency

**Reviewed:** `repository.py` transactional pattern, unique constraints, concurrency backstop.

| Check | Result |
|---|---|
| COMMIT = truth; no false success | ✅ rollback + raise on any failure |
| Order + initial event in one transaction | ✅ `create_order` adds both before a single COMMIT |
| Idempotency: replay → duplicate, conflict → CONFLICT | ✅ `_resolve_existing` (identity-key compare) |
| Unique-constraint backstop (race) | ✅ `IntegrityError` → re-read winner → `OUTCOME_DUPLICATE` |
| Exactly-one-order under concurrency | ✅ `test_oms_concurrency.py` (threaded barrier) |
| No global lock serializing distinct orders | ✅ distinct intents create independently |
| Indexes for orchestration/identity/account/instrument/status/signal | ✅ model + migration |

**Finding (NOTE-2):** `append_event` mutates `order.status` then stages the event; in the in-memory fake the status mutation is direct (not rolled back on commit failure). In production SQLAlchemy this is a session-managed attribute and rolls back correctly. Test-infra limitation only. Accepted.

---

## Dimension 3 — Order correctness / risk-boundary integrity

**Reviewed:** validation, approval binding, identity, order record completeness.

| Check | Result |
|---|---|
| Full intent→order validation (quantity/action/type/account/mode/halt/expiry) | ✅ `validation.py` |
| Approval binding re-verified before SUBMISSION_REQUESTED | ✅ expiry + approval_id presence re-checked in `_request_submission` |
| Deterministic order identity (no random-UUID-only) | ✅ SHA-256 `order_identity_key` over immutable payload + deterministic `client_order_id` |
| Identity covers signal/strategy/account/instrument/side/quantity/type/mode/approval | ✅ `compute_order_identity_key` |
| Order record completeness (section 8 fields) | ✅ `to_orm_order` maps all required fields |
| No secrets stored | ✅ no credential fields |

**Finding (MINOR-1, fixed):** `Order.id` was a fresh `uuid4()` while `OrderIdentity.internal_order_id` was a separate UUID — the persisted order would not match the returned identity. Fixed by setting `Order(id=identity.internal_order_id)` in `to_orm_order`; covered by `test_oms_repository.py::test_create_order_inserts_order_and_event`.

**Finding (NOTE-3):** Field-level approval↔intent binding (signal/account/instrument/quantity/order-type/mode) is inherited from Phase 7 via `binding_hash`; the OMS only re-verifies expiry + approval_id because it receives the `TradingIntent`, not the original `RiskDecision`. The `order_identity_key` additionally makes any field drift between intent and order a CONFLICT. Accepted as a documented boundary.

---

## Dimension 4 — LIVE safety / regression

**Reviewed:** trading-mode gate, halt, broker coupling, forged-event resistance.

| Check | Result |
|---|---|
| LIVE blocked before order creation | ✅ `TradingModeError` (validation) |
| GLOBAL_TRADING_HALT fail-closed (default True) | ✅ `validate_intent` default `global_halt_active=True` |
| No broker SDK / credentials / API calls | ✅ `test_oms_security.py` source scan |
| No real submission / cancellation API | ✅ Execution Port only |
| No forged BROKER_ACKNOWLEDGED / FILLED | ✅ no lifecycle API reaches these states |
| Full regression intact | ✅ 1050 passing (975 baseline + 75 Phase 8) |

**Finding (MINOR-2, fixed):** `trading.py` used `Index(...)` in `Order.__table_args__` without importing `Index` — the `orders` model failed to import (pre-existing, would have broken any Order-model test). Fixed by adding `Index` to the `sqlalchemy` import.

---

## Summary

| Severity | Count | Disposition |
|---|---|---|
| BLOCKER | 0 | — |
| MAJOR | 0 | — |
| MINOR | 2 | both fixed + regression-tested |
| NOTE | 3 | documented limitations (no action) |

No legitimate adversarial finding remains unfixed. Phase 8 is declared **TESTED** (not PRODUCTION).
