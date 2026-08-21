# Alpha Algo — Event Architecture (Phase 21)

A unified **internal** domain-event architecture for the trading system. It is a
visibility/decoupling layer, not a trading decision engine: events describe what
already happened and never modify trading state, never enable LIVE, and never
carry secrets (Phase 20 §2/§38 preserved).

## 1. Scope ("where justified")

| Area | Decision |
|---|---|
| Internal event flow | **Implemented** — unified envelope + in-process bus. |
| Broker/streaming eventing | **Deferred** — no scale justification (no Kafka/RabbitMQ/Redis; the Phase 10 broker event normalization + dedup already covers provider event ingestion). |

## 2. Architecture

```
Pipeline (signal → risk → orchestration → OMS → execution → position →
          portfolio → P&L → reconciliation)
        │  (existing synchronous boundaries + per-phase persisted events, unchanged)
        ▼
Unified domain event  ── alpha_algo_contracts.events.DomainEvent
        │
        ▼
In-process event bus  ── alpha_algo_event_bus.EventBus (pub/sub)
        │
        ▼
Cross-cutting subscribers (observability / audit / notification) — decoupled
```

The bus is an **additive** layer: it does not rewire the tested synchronous
engines, and it introduces no external broker or network dependency.

## 3. Domain event envelope

`DomainEvent` (immutable, validated):

- `event_type` — lowercase dotted topic (`order.created`, `execution.filled`, …)
  validated against `[a-z][a-z0-9_.]*`.
- `occurred_at` — **timezone-aware** (naive rejected).
- `source` — non-empty service name.
- `event_id` — UUID (fresh per event).
- `correlation_id` / `causation_id` / `trace_id` — correlation + causality.
- `domain_ids` — `str→str` domain identifiers (order_id, execution_id, …), never
  replacing domain ids.
- `payload` — plain dict of facts; **secrets rejected** (`validate_no_secrets`,
  recursive: password/token/secret/api_key/authorization/credential/private_key/
  refresh/cookie/session_id).

`DomainEvent.derive(...)` creates a causally-linked child (sets `causation_id` to
the parent's `event_id`, inherits `correlation_id`/`trace_id`/`domain_ids`).

## 4. Event catalog (standard topics)

`signal.accepted`, `signal.rejected`, `risk.decision`, `intent.created`,
`order.created`, `order.state_changed`, `execution.submitted`,
`execution.acknowledged`, `execution.filled`, `execution.rejected`,
`execution.unknown`, `position.updated`, `position.closed`,
`portfolio.snapshotted`, `pnl.realized`, `reconciliation.discrepancy`,
`reconciliation.completed`, `paper.run_started`, `paper.fill`, `system.health`.

## 5. Event bus

`EventBus` (in-process, thread-safe):

- `subscribe(topic, handler)` → `Subscription` (`cancel()` to unsubscribe).
- `publish(event)` / `publish_many(events)` — synchronous, deterministic FIFO.
- `"*"` wildcard receives all events.
- **Handler isolation** — a failing handler is recorded (`failures()`) and
  skipped; it never breaks the publisher or other handlers.
- `NoopEventBus` — offline/tests.

## 6. Correlation model

A trading lifecycle is reconstructable end-to-end: `correlation_id` (the whole
chain), `causation_id` (parent event), `trace_id` (Phase 20 tracing), and
`domain_ids` (signal → order → execution → position → pnl → reconciliation ids).
Correlation ids supplement — never replace — domain ids.

## 7. Failure isolation / LIVE safety

- A failing subscriber never breaks the pipeline (observability must not break
  trading).
- Events are append-only facts; they cannot enable LIVE or modify state.
- Secrets cannot enter the stream (rejected at envelope construction).

## 8. Tests

- `tests/unit/test_event_architecture.py` — envelope validation + bus behavior (18).
- `tests/unit/test_event_bus_integration.py` — pipeline event flow (3).
- Full backend regression: **1669 passed** (1648 baseline + 21 new, zero regressions).
