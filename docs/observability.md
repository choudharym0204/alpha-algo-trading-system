# Alpha Algo — Observability Platform (Phase 20)

Provider-neutral observability for the trading system. This is a
**visibility/diagnostic layer only** — it can observe trading but can never
modify orders, positions, P&L, portfolio truth, or trading mode, and it can
never enable LIVE (Phase 20 §2, §69). LIVE remains disabled and fail-closed.

## 1. Architecture

```
Domain services (OMS / execution / risk / reconciliation / paper / …)
        │  (existing Phase 8–16 domain metrics + repositories)
        ▼
Project observability abstraction  ← packages/observability/alpha_algo_observability
        │
        ├── Metrics      (Counter / Gauge / Histogram, bounded labels)
        ├── Structured logs  (redaction, request/trace/correlation ids)
        ├── Tracing      (spans, contextvars, W3C traceparent)
        ├── Audit        (append-only, chained hash)
        ├── Health       (liveness / readiness / dependency / trading-safety)
        └── Alerts       (deterministic dedup + lifecycle)
        │
        ▼
API instrumentation  ← apps/api/alpha_algo_api/observability.py + middleware
        │
        ▼
Read-only surface  ← GET /api/v1/system/observability (gated by system:read)
```

Core domain modules are **not** coupled to any vendor telemetry backend. There
is no Prometheus/Grafana/Jaeger dependency in the core (§40–§42). The registry
is in-memory and a **no-op** path exists for offline/tests.

## 2. Structured logging schema

Fields (``StructuredLogger`` → stdlib ``extra["structured"]``):

- Common: `service`, `event`, `message`, `request_id`, `correlation_id`,
  `trace_id`, `span_id`, `environment`, `version`, `timestamp` (stdlib).
- Domain (where applicable): `account_id`, `strategy_id`, `strategy_run_id`,
  `signal_id`, `risk_decision_id`, `approval_id`, `orchestration_id`,
  `intent_id`, `order_id`, `execution_id`, `position_id`, `portfolio_id`,
  `pnl_event_id`, `reconciliation_run_id`, `discrepancy_id`, `paper_run_id`,
  `broker`.

**Never logged:** password, access/refresh tokens, API keys/secrets, private
keys, full Authorization headers, broker credentials, unnecessary PII.

Log levels: `DEBUG` (diagnostics), `INFO` (lifecycle), `WARNING`
(degraded/recoverable), `ERROR` (operation failure), `CRITICAL`
(safety/system-critical). Errors are **not** blanket-classified CRITICAL.

## 3. Metric catalog

API metrics (new in Phase 20, bounded labels):

| Metric | Type | Labels |
|---|---|---|
| `api_requests_total` | Counter | `method` |
| `api_requests_by_status_total` | Counter | `status_class` (2xx/3xx/4xx/5xx) |
| `api_request_latency_seconds` | Histogram | — |
| `api_auth_failures_total` | Counter | `failure_class` |
| `api_rate_limit_events_total` | Counter | — |
| `api_active_http_connections` | Gauge | — |
| `api_active_ws_connections` | Gauge | — |

Service metrics (already present from Phases 8–16; domain dataclasses such as
`OmsMetrics`, `ExecutionMetrics`, `PositionMetrics`, `PortfolioMetrics`,
`PnlMetrics`, `ReconciliationMetrics`, `PaperMetrics`):

- OMS: orders_created, duplicate_intents, duplicate_orders, state_transitions,
  cancellations, rejections, unknown_states, reconciliation_required,
  persistence_failures.
- Execution: requests, submissions, acknowledgments, rejects, retries, timeouts,
  cancellations, fills, partial_fills, duplicate events/requests, unknown_states.
- Position / Portfolio / P&L / Reconciliation / Paper: equivalent counters
  (see each service's `metrics.py`).

## 4. Trace model

- W3C `traceparent` (`00-<trace_id>-<span_id>-<flags>`) parsed on ingress and
  linked to the local trace; the local `trace_id` is propagated into logs and
  the request state. The internal span structure is **not** echoed to clients.
- Spans propagate across `await` boundaries in the same async task via
  `contextvars`; parent/child linkage is derived only from the active span (no
  invented relationships).
- Sampling: errors and safety events are always retained; normal traffic is
  sampled with a configurable ratio.

## 5. Correlation model

A request/trading action is reconstructable via `request_id` +
`correlation_id` + `trace_id` + domain ids (order_id, execution_id, etc.).
Correlation ids **supplement** domain identifiers; they never replace them.

## 6. Health model

- **Liveness** — `GET /system/health` (process alive).
- **Readiness** — `GET /system/ready` (can safely serve; database ping).
- **Dependency health** — registered checks (database, broker, market data,
  risk, OMS, execution, observability). An **optional** dependency being down
  does not make the whole system unhealthy.
- **Trading-safety health** — read-only facts: `LIVE_TRADING_ENABLED`,
  `GLOBAL_TRADING_HALT`, `default_trading_mode`. Dashboards can **not** flip
  safety state.

## 7. Alerting

- **Severity**: CRITICAL / HIGH / WARNING / INFO.
- **Deterministic identity** = sha256(`type|source|scope|condition`) → same
  condition never creates unlimited duplicate alerts.
- **Lifecycle**: `detected → active → (acknowledged | escalated) → resolved`;
  every transition is recorded.
- **Correlation**: alerts carry `incident_id`, `correlation_id`, `trace_id`.

## 8. Retention / cardinality / sensitive data

- In-memory telemetry (development default); external exporters are modular and
  not introduced without justification (§40).
- Metric labels are **bounded** and declared per family; unknown/missing/overlong
  labels raise `CardinalityError`. Raw user/order/execution/strategy ids, raw
  timestamps, symbols, and exception strings are **never** metric labels — they
  belong in structured logs / traces / audit / domain DBs.
- No passwords, tokens, keys, or PII in telemetry; `redact()` strips
  known-sensitive keys recursively.

## 9. Error normalization

`FailureClass`: AUTHENTICATION_FAILURE, AUTHORIZATION_FAILURE,
VALIDATION_FAILURE, TIMEOUT, RATE_LIMIT, DATABASE_ERROR, BROKER_ERROR,
NETWORK_ERROR, PROVIDER_UNAVAILABLE, STATE_CONFLICT, UNKNOWN. Provider-specific
details stay in structured log/trace fields.

## 10. Dashboards (data source)

`GET /api/v1/system/observability` (requires `system:read`) returns one snapshot
covering System Overview, Trading Pipeline, Broker Health, Reconciliation, and
Security views: metrics + health (incl. trading safety) + alerts + recent traces.

## 11. SLO / SLA (documented, not enforced)

No automatic trading-disable is wired to any target. Where adopted, each target
documents `target` / `measurement` / `calculation window` / `source`. Example
candidates (not yet enforced): API availability, API p95 latency, WebSocket
availability, market-data freshness, execution response latency, reconciliation
completion time. Error budgets are for operational analysis only (§51).

## 12. Failure isolation

- Observability backend unavailable → trading remains functional (§42, §59).
- A failing dependency health check degrades the snapshot but never raises.
- No-op metrics/alerts/audit/trace paths are available for unit tests and
  offline execution.

## 13. Tests

- `tests/unit/test_observability_platform.py` — abstraction unit tests (25).
- `tests/unit/test_observability_api.py` — API instrumentation (6).
- `tests/unit/test_observability_failure_isolation.py` — failure isolation (6).
- Full backend regression: 1642 passed (1611 baseline + 37 new).

## 14. LIVE safety

`LIVE_TRADING_ENABLED=false`, `GLOBAL_TRADING_HALT=true`, default mode `PAPER`.
The observability layer is observation-only; it never becomes a trading
decision engine and never enables LIVE (Phase 20 §2, §69).
