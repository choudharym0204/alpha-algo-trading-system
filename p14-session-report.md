# P14 — Reconciliation Engine — Session Report

**Date:** 2026-08-20
**Phase:** 14 (Reconciliation Engine)
**Status:** COMPLETE — **TESTED**
**Regression:** 1412 tests passing (1349 baseline + 63 Phase 14)

---

## 1. Objective

A durable, deterministic, auditable Reconciliation Engine that compares internal
authoritative state (OMS/Execution/Position/Portfolio/P&L) against broker
observations (Phase 10 normalized read models) and identifies discrepancies
**without silently corrupting internal state**.

```
Internal State  ↕  Broker Observation
        ↓
  Reconciliation Engine
        ↓
  MATCH / MISMATCH / UNKNOWN
        ↓
  Persist Evidence → Controlled Recovery Workflow
```

---

## 2. Absolute Principle

Reconciliation is an observation + correction-control system, **not** an excuse
to overwrite internal financial truth. Every discrepancy is append-only,
auditable, and resolved through explicit policy — never a silent overwrite.

---

## 3. Scope

Owns: order / execution / position / funds reconciliation, discrepancy
classification + persistence, runs, evidence, safe corrective workflow,
idempotency, replay, restart recovery, status, metrics.

Does **not** own: broker adapters, market-data ingestion, risk rules, OMS design,
execution adapter design, position/P&L calculation, UI, LIVE enablement.

---

## 4. Authoritative Sources

| Domain | Internal authority |
|---|---|
| Orders | OMS / `orders` / order lifecycle |
| Executions | Execution Engine / execution attempts / trade facts |
| Positions | Position Engine (Phase 11) |
| Portfolio | Portfolio Engine (Phase 12) |
| P&L | P&L Engine (Phase 13) |
| Broker observations | Phase 10 normalized read models (orders/trades/positions/funds) |

Provider-specific raw formats never enter reconciliation logic.

---

## 5. Matching & Discrepancy Taxonomy

Identity-first, deterministic matching (broker order/execution ID → client ID →
internal identity). `DiscrepancyKind` covers: MATCH, INTERNAL_ONLY, BROKER_ONLY,
STATUS/QUANTITY/PRICE/FEE/AVERAGE_PRICE/SIDE/ORDER_TYPE/ACCOUNT/INSTRUMENT/ORDER_LINK
mismatches, CASH/MARGIN mismatch, DUPLICATE_EXECUTION, ROUNDING_DIFFERENCE,
CONFLICT, UNKNOWN, STALE.

**Severity:** INFO (rounding) / WARNING (timing lag, funds) / HIGH (position/order
state divergence) / CRITICAL (unexpected broker fill).

**Lifecycle:** DETECTED → CLASSIFIED → OPEN → INVESTIGATING → RESOLVED/ACKNOWLEDGED/ESCALATED.

---

## 6. Tolerance Model

Narrow, explicit, configurable (`Tolerance`): price epsilon (4-dp), fee epsilon,
funds epsilon, timestamp skew. No broad tolerance that hides real divergence.
Stale observations → STALE/UNKNOWN, never a hard mismatch. Unavailable funds stay
`None`, never zero.

---

## 7. Run Model

Each run: `run_id`, account, broker, trading mode, scope, started/completed,
status (PENDING/RUNNING/COMPLETED/PARTIAL/FAILED), and counts (matched/mismatched/
internal-only/broker-only/unknown/unavailable/skipped/conflicts). Explicit scope
(single account + broker + mode + domains); no implicit multi-account.

---

## 8. Corrective Workflow (no silent auto-correction)

Dangerous domains (position quantity, fills, realized P&L, order status, funds)
are **never** auto-corrected. Broker-only executions produce a `ROUTE_BROKER_FILL`
recovery action pointing at the existing `execution_engine` boundary; a trusted
orchestrator feeds the normalized fill through Execution→Position→P&L (which
already enforce idempotency). No second parallel path; no direct position/P&L/
portfolio mutation.

---

## 9. Persistence & Identity

- `reconciliation_runs` — one row per run (scope, status, counts, indexes on account).
- `reconciliation_discrepancies` — append-only evidence; unique `discrepancy_key`
  (deterministic: account + entity type + entity id + kind) is the idempotency
  backstop; `content_hash` detects conflicting evidence (CONFLICT, original preserved).
- Evidence = normalized `internal_state` + `broker_state` (bounded; no secrets).

Migration: `migrations/versions/20260820_reconciliation_engine.py` (down_revision `20260820_pnl_engine`).

---

## 10. Idempotency / Concurrency / Recovery

- Replay → no duplicate discrepancies; same identity + different evidence → CONFLICT.
- Concurrency boundary = DB unique constraint (append-only; no process lock).
- Restart recovery: discrepancies reconstructable from durable store.

---

## 11. Boundaries (mandatory)

- **No reconciliation auto-overwrite** of position/P&L/portfolio.
- **No broker calls / SDK / provider-specific branch** in core logic.
- **No new accounting engine** (position/P&L/portfolio reused).
- **LIVE fail-closed**: LIVE/unknown mode + global halt rejected.

---

## 12. Tests (63 new)

- `test_reconciliation_orders.py` (10) — match, internal/broker-only, status/quantity/side/type/instrument/account mismatch, duplicate broker order.
- `test_reconciliation_executions.py` (9) — match, internal/broker-only, duplicate, quantity/price/fee/order-link mismatch, price tolerance.
- `test_reconciliation_positions.py` (10) — match, missing internal/broker, quantity/avg-price/side mismatch, tolerance, stale, partial, avg-price-not-comparable.
- `test_reconciliation_funds.py` (7) — match, rounding, cash/margin mismatch, unavailable, stale, broker unavailable, no-internal.
- `test_reconciliation_engine.py` (9) — full clean run, recovery action, partial, LIVE/halt, persisted run, DB failure, account isolation.
- `test_reconciliation_idempotency.py` (2) — replay no-duplicate, conflict.
- `test_reconciliation_concurrency.py` (3) — same-account dedupe, multi-account isolation, no lost updates.
- `test_reconciliation_security.py` (7) — LIVE/halt, no broker branch/SDK/secret, no engine bypass, no mutation path.
- `test_reconciliation_schema.py` (4) — columns, constraints, migration chain.
- `test_reconciliation_e2e.py` (2) — broker position+funds via adapters, read-back.

---

## 13. Review Findings & Fixes

4-axis adversarial review (`review.md`): **0 BLOCKER / 0 MAJOR / 1 MINOR (fixed) / 3 NOTE.**

- **MINOR-1 (fixed):** position average-price compared even when the broker omitted it (data gap ≠ mismatch) — now only compared when both sides report it.
- **NOTE-1:** MATCH counted, not persisted (avoids evidence bloat).
- **NOTE-2:** run-level audit vs discrepancy-level idempotency.
- **NOTE-3:** recovery actions are produced-not-executed (trusted orchestrator routes them).

---

## 14. Remaining Limitations

- Live PostgreSQL / Docker verification deferred (no Docker); exercised via in-memory double + schema tests.
- No real broker observations (fakes only); never marked PRODUCTION.
- Recovery actions are produced but not auto-executed (requires trusted orchestrator — correct by design).
- External review subagents unavailable at the model layer; inline review recorded transparently.

## 15. LIVE Status

`LIVE_TRADING_ENABLED = false`, `GLOBAL_TRADING_HALT = true` (fail-closed). No reconciliation path enables LIVE or submits a live order.

---

## 16. Next Phase

**Phase 15 — Paper Trading Completion.** NOT started.
