# Phase 21 — Event Architecture — Session Report

**Date:** 2026-08-21
**Status:** TESTED — unified domain-event envelope + in-process event bus implemented and tested; full backend regression green (1669)

---

## 1. Objective

Introduce a unified **internal** event architecture ("where justified") so the
trading pipeline's event flow is observable, correlated, and consumable by
cross-cutting subscribers — without changing trading behavior, without enabling
LIVE, and without introducing a distributed broker.

## 2. Scope decision (from the control document)

`IMPLEMENTATION_STATUS.md` §5.14 lists two Phase-21 capabilities:

- **Event architecture — internal** (`PARTIAL`) → implemented here.
- **Event architecture — broker** (`MISSING`, "only if justified") → **deferred**
  (no scale justification; Phase 10 broker-event normalization + dedup already
  covers provider event ingestion).

## 3. What was built

**`packages/contracts/alpha_algo_contracts/events.py`** — unified, validated
`DomainEvent` envelope + `EventType` catalog + `create_event` factory +
recursive `validate_no_secrets` (secrets can never enter the stream).

**`packages/events/alpha_algo_event_bus/`** — in-process, thread-safe `EventBus`
(pub/sub, wildcard, deterministic FIFO, handler-failure isolation, `NoopEventBus`).

Both are **additive**; no existing engine was modified (per the "do not modify
completed phases unless a real Phase-21 dependency requires it" rule).

## 4. Correlation model

`correlation_id` (whole chain) + `causation_id` (parent event) + `trace_id`
(Phase 20) + `domain_ids` (signal→order→execution→position→pnl→reconciliation
ids) make a lifecycle reconstructable. Correlation supplements, never replaces,
domain ids.

## 5. Verification

| Gate | Result |
|---|---|
| Event architecture unit tests | ✅ 18 passed |
| Pipeline event-flow integration tests | ✅ 3 passed |
| Full backend regression | ✅ **1669 passed** (1648 baseline + 21 new, zero regressions) |

The integration test drives the full pipeline (signal → risk → orchestration →
OMS → execution → position → P&L → reconciliation) as a causally-linked,
correlated event stream through the bus and verifies ordering, causation,
correlation, and domain-id reconstruction.

## 6. Review

Inline four-axis review in `P21-review.md`. 0 BLOCKER / 0 MAJOR; 1 MINOR (fixed)
+ notes documented.

## 7. Limitations (documented, not hidden)

- **Broker/streaming eventing deferred** — no Kafka/RabbitMQ/Redis; not justified
  at current scale.
- **Bus not wired into every engine** — the tested synchronous pipeline is
  intentionally unchanged; the bus is an additive layer that engines *can*
  publish to (and cross-cutting subscribers already consume). Wiring it into a
  specific engine is an incremental, additive follow-up.
- **In-process only** — no persistence, no cross-process delivery, no replay.

## 8. LIVE safety

`LIVE_TRADING_ENABLED=false`, `GLOBAL_TRADING_HALT=true`. Events are append-only
facts and can never enable LIVE or modify trading state. Phase 22 is **not**
started.
