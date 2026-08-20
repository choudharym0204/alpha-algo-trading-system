# IMPLEMENTATION_STATUS.md

**Project:** Alpha Algo Trading System
**Document purpose:** Phase 0 — Baseline Synchronization (implementation-control document).
**Repository:** `projects/alpha-algo-trading-system/`
**Date:** 2026-08-18
**Execution mode:** Architecture-Preserving Incremental Implementation

> **Read-only baseline discovery.** This document records the current capability status, dependencies, target phase, owner module, and verification requirement for every tracked capability. It is derived from the 10 audit registers (`CURRENT_ARCHITECTURE_REGISTER.md`, `TECHNOLOGY_STACK_REGISTER.md`, `TRADING_ENGINE_REGISTER.md`, `PROVIDER_INTEGRATION_REGISTER.md`, `PLATFORM_CAPABILITY_MATRIX.md`, `DEPENDENCY_REGISTER.md`, `ARCHITECTURE_DEPENDENCY_GRAPH.md`, `SINGLE_POINT_OF_FAILURE_REGISTER.md`, `TECHNOLOGY_COUPLING_REGISTER.md`, `AUDIT_SUMMARY.md`) and verified against source. **No code was modified.**

---

## 0. Phase 1 — Foundation Hardening (COMPLETE)

Phase 1 was implemented and verified on 2026-08-18 (see `.cluster/alpha-algo-phase1/DELIVERY/P1-session-report.md`). All §5.1 Foundation capabilities are now **TESTED** (implemented + unit-tested + integrated). They are intentionally **not** marked PRODUCTION/VERIFIED because live PostgreSQL and end-to-end DB-backed verification are deferred to Phase 2. Full suite: **618 tests passing**. LIVE remains **fail-closed**.

---

## 0b. Phase 2 - Database Runtime (COMPLETE)

Phase 2 was implemented and verified on 2026-08-18 (see `.cluster/alpha-algo-phase2/DELIVERY/P2-session-report.md`). All 5.2 Database Runtime capabilities are now **TESTED** (implemented + unit-tested + integrated). Live PostgreSQL connectivity, real pool behavior under load, and end-to-end `alembic upgrade head` against a live DB remain deferred (no Docker/PostgreSQL in this environment) and must be re-verified at VERIFIED/PRODUCTION time. Full suite: **651 tests passing**. LIVE remains **fail-closed**.

---

## 0c. Phase 3 — Market Data (COMPLETE)

Phase 3 was implemented and verified on 2026-08-18 (see `.cluster/alpha-algo-phase3/DELIVERY/P3-session-report.md`). The market-data runtime — provider abstraction, connection lifecycle (reconnect/backoff/heartbeat/timeout/watchdog), streaming pipeline with bounded backpressure, validation/normalization safety, TimescaleDB persistence, historical retrieval (page-based pagination + retry), composition root, and observability metrics — is now **TESTED** (implemented + unit-tested + integration-tested). Live provider connectivity (real broker/market-data vendor feeds) remains deferred (no real providers in this environment) and must be re-verified at VERIFIED/PRODUCTION time. Full suite: **696 tests passing**. LIVE remains **fail-closed**.

---

## 0d. Phase 4 — Strategy Runtime (COMPLETE)

Phase 4 was implemented and verified on 2026-08-18/19 (see `.cluster/alpha-algo-phase4/DELIVERY/P4-session-report.md`). The strategy runtime — registry (register/unregister/discover/load/validate/enable/disable/status/duplicate-prevention), a 7-state lifecycle machine, strategy identity + deterministic config/code hashing, validated + deep-frozen config, per-instance isolation + signal validation + bounded LRU dedup, event dispatcher (instrument/timeframe/event-type/enabled/state routing), run records, observability metrics, the Phase-3→Phase-4 market-data boundary, and a reference SMA-crossover strategy — is now **TESTED** (implemented + unit-tested + integration-tested + adversarial-review-fixed). A 4-dimension adversarial review (strategy architecture; runtime/concurrency/isolation; signal correctness/data integrity; LIVE-safety/regression) was run; every legitimate finding was fixed and 7 regression tests added. Live execution and downstream OMS/Risk/Execution/signal-persistence wiring are deferred (no downstream consumers are registered; the runtime ends at a validated, traceable `StrategySignal`). Full suite: **759 tests passing** (Phase 4 added 63 tests over the verified 696-test baseline). LIVE remains **fail-closed** — only BACKTEST/PAPER are allowed; LIVE raises `TradingModeError`.

---

## 0e. Phase 5 — Signal Engine (COMPLETE)

Phase 5 was implemented and verified on 2026-08-19 (see `.cluster/alpha-algo-phase5/DELIVERY/P5-session-report.md`). The Signal Engine — the dedicated, persistent, deterministic, auditable boundary between the Phase-4 Strategy Runtime and the future Phase-6 Risk Engine — is now **TESTED** (implemented + unit-tested + integration-tested + 4-axis-review-fixed). It re-validates every `StrategySignal` at the boundary, enforces deterministic identity (`identity_key`) + content hashing, enforces an 8-state lifecycle machine, dedups via in-memory LRU + DB unique constraints, persists transactionally to PostgreSQL `signals` (COMMIT = truth boundary), and exposes a Phase-6 consumer fan-out (`add_consumer` + `SignalRecord`). Trading mode is fail-closed: only BACKTEST/PAPER are accepted; LIVE raises `TradingModeError`. Live DB connectivity and end-to-end DB-backed verification remain deferred (no Docker/PostgreSQL in this environment). Full suite: **827 tests passing** (Phase 5 added 68 tests over the 759-test baseline). LIVE remains **fail-closed**. Risk/OMS/Execution/Broker/LIVE are **not** implemented in this phase.

---

## 0f. Phase 6 — Live Risk Engine (COMPLETE)

Phase 6 was implemented and verified on 2026-08-19 (see `.cluster/alpha-algo-phase6/review.md` and `P6-session-report.md`). The Live Risk Engine — the runtime-connected, fail-closed decision boundary between the Phase-5 Signal Engine and the future Phase-7 Trading Orchestrator — is now **TESTED** (implemented + unit-tested + integration-tested + 4-axis-adversarial-review-fixed). It adds: an immutable `RiskSnapshot`, a fail-closed `RiskStateProvider` protocol, a `RiskContextBuilder`/`RiskContextValidator` (with snapshot↔intent identity + trading-mode reconciliation), six new configurable controls (max drawdown, price deviation, order frequency, account limits, execution-timeout, retry-safety), approval binding + expiry, an actual `CircuitBreaker` (closed/open/half-open) + registry, and durable idempotent persistence to `risk_events` keyed on a stable `identity_key`. `RiskService` is serialized (RLock) and fanned out **only after a durable COMMIT**; LIVE/unknown trading mode is rejected at the boundary. A 4-dimension adversarial review surfaced 2 BLOCKERs + ~10 MAJORs (global-halt replay bypass, non-durable idempotency, fan-out-on-failed-persist, fail-open exposure/drawdown, optional approval binding); **every BLOCKER/MAJOR was fixed**. Full suite: **928 tests passing** (Phase 6 added 101 tests over the 827-test Phase-5 baseline). Live PostgreSQL connectivity and a real runtime state provider (positions/portfolio/P&L are Phase 11+) remain deferred; the default provider fails closed. The engine ends at `RiskDecision → APPROVED/REJECTED`; OMS/execution/LIVE are **not** implemented in this phase.

---

## 0g. Phase 7 — Trading Orchestrator (COMPLETE)

Phase 7 was implemented and verified on 2026-08-19 (see `.cluster/alpha-algo-phase7/review.md` and `P7-session-report.md`). The Trading Orchestrator — the coordination layer connecting the Phase-5 Signal Engine → Phase-6 Risk Engine → an explicit OMS-ready handoff boundary — is now **TESTED** (implemented + unit-tested + integration-tested + 4-axis-adversarial-review-fixed). It verifies signal acceptance (PERSISTED + identity match), resolves the concrete order intent through a pluggable fail-closed resolver, validates action (BUY/SELL/EXIT; HOLD/unknown never mint an intent), drives Phase-6 risk evaluation, re-validates approval binding + expiry (`PRIOR_APPROVAL_INVALID` preserved), normalizes an OMS-ready `TradingIntent`, and persists it durably (`trading_intents`, `orchestration_id` unique) before an explicit OMS-port handoff notification. Idempotency is deterministic (signal identity + strategy run + quantity + account + order type + mode), concurrency is narrow (RLock around check-and-persist), and LIVE/unknown trading modes are blocked fail-closed. The 4-axis adversarial review surfaced 1 MAJOR (model↔migration metadata column drift) + 2 MINOR; all fixed. Full suite: **975 tests passing** (Phase 7 added 47 tests over the 928-test Phase-6 baseline). Live PostgreSQL connectivity and the downstream OMS (Phase 8) remain deferred. The pipeline ends at an `OMS-ready Intent` — **never** a broker. LIVE remains **fail-closed**.

---

## 0h. Phase 8 - Order Management System (COMPLETE)

Phase 8 was implemented and verified on 2026-08-19 (see `P8-session-report.md` and `review.md`). The OMS - the internal order-management boundary between the Phase-7 Trading Orchestrator and the future Phase-9 Execution Engine - is now **TESTED** (implemented + unit-tested + integration-tested + 4-axis-adversarial-review-fixed).

It transforms a Phase-7 `TradingIntent` into a durable internal `Order`, drives the existing 11-state `OrderLifecycle` from INTENT_CREATED -> INTERNAL_ORDER_CREATED -> SUBMISSION_REQUESTED, persists append-only `order_events`, and stops at an explicit `ExecutionBoundary` (Execution Port only). Deterministic order identity (`order_identity_key` SHA-256 + deterministic `client_order_id` + correlation id + broker-order-id placeholder), durable intent-consumption idempotency (replay -> existing order returned; same orchestration_id + different payload -> CONFLICT), transactional order+event creation (COMMIT = truth; unique-constraint backstop for exactly-one-order concurrency), risk-approval binding re-verified before SUBMISSION_REQUESTED, and GLOBAL_TRADING_HALT + LIVE-mode fail-closed gating are all enforced.

The OMS introduces **no broker SDK / credentials / API calls / real submission / forged BROKER_ACKNOWLEDGED or FILLED**. LIVE remains **fail-closed** (GLOBAL_TRADING_HALT stays true). Full suite: **1050 tests passing** (Phase 8 added 75 tests over the 975-test Phase-7 baseline). Phase 9 (Execution) is **not** started.

Schema: `migrations/versions/20260819_oms.py` adds `orders.orchestration_id` (unique), `order_identity_key` (unique), `correlation_id`, `strategy_id`, `strategy_version`, `risk_approval_id` (unique), `approval_expires_at` + indexes. A pre-existing model bug (missing `Index` import in `trading.py`) was fixed so the `orders` model imports cleanly.

---

## 0i. Phase 9 - Execution Engine (COMPLETE)

Phase 9 was implemented and verified on 2026-08-20 (see `P9-session-report.md` and `review.md`). The Execution Engine - the provider-neutral boundary between the Phase-8 OMS and the future Phase-10 broker adapters - is now **TESTED** (implemented + unit-tested + integration-tested + 4-axis-adversarial-review-fixed).

It consumes the OMS `ExecutionPort`, validates + dispatches the OMS-approved order to a provider-neutral `ExecutionAdapter` (no broker SDKs - Phase 10 owns those), and manages the execution lifecycle:

- **Deterministic execution identity** - `compute_execution_id` (SHA-256 over `order_id` + `order_identity_key`) + `compute_attempt_id` (`execution_id-a{n}`), dedup across retries/restarts.
- **Submission state machine** - `SUBMISSION_REQUESTED → SUBMISSION_IN_PROGRESS → SUBMITTED → ACKNOWLEDGED`, with `TIMEOUT`/`UNKNOWN`/`REJECTED`/`CANCELLED` branches.
- **Exactly-once intent** - idempotent submission via `(execution_id, attempt_number)` unique constraint + re-read-on-conflict; concurrent duplicate submissions produce exactly one adapter dispatch.
- **Timeout → UNKNOWN (never blind retry)** - a timeout is ambiguous (the provider may have accepted); bounded classification-based retry only for `TRANSIENT_FAILURE`.
- **Cancellation lifecycle** - authoritative `CANCELLED` only on explicit confirmation; pending/ambiguous cancellation preserves `UNKNOWN`.
- **Event normalization/dedup** - `compute_event_identity` + content-hash conflict detection; partial-fill accumulation with overfill protection; exact-quantity final fill.
- **PostgreSQL persistence** - `ExecutionAttemptRecord` (`execution_attempts`) + Alembic migration `20260819_execution.py` (down_revision `20260819_oms`).
- **Failure classification** - `FailureClass` enum (TIMEOUT / TRANSIENT_FAILURE / AUTH_FAILURE / UNKNOWN_EXTERNAL_STATE / INTERNAL_FAILURE) + `classify()`.
- **Security** - LIVE blocked fail-closed, forged events rejected, no credentials/broker coupling anywhere in the engine.

Full suite: **1117 tests passing** (Phase 9 added 67 tests over the 1050-test Phase-8 baseline). LIVE remains **fail-closed**. Phase 10 (Broker Adapters) is **not** started.

Schema: `migrations/versions/20260819_execution.py` adds `execution_attempts` (unique on `execution_id` + `attempt_number`, indexed on `order_id`).

---

## 1. Current Product Maturity Level

**LEVEL 1 — FOUNDATION.**

Core contracts/libraries exist (backtesting is PRODUCTION-grade as a deterministic library). The system is **not yet** a functioning end-to-end trading platform. Higher levels require evidence and are claimed only when verified:

```
LEVEL 1  FOUNDATION              ← current
LEVEL 2  INTEGRATED BACKEND      (major engines operate together)
LEVEL 3  PAPER TRADING PLATFORM  (full end-to-end paper works)
LEVEL 4  MULTI-PLATFORM PRODUCT  (Web + Mobile + Desktop against backend)
LEVEL 5  CONTROLLED LIVE         (broker + risk + reconciliation verified)
LEVEL 6  PRODUCTION LIVE         (ops/monitoring/recovery/security/audit verified)
```

---

## 2. Baseline Reality (verbatim §3)

The current repository is a **Python 3.12+ foundation-stage algorithmic trading system**. It is NOT yet a functioning end-to-end live trading platform.

- Backtesting = strong / production-grade pure deterministic subsystem
- Risk engine = PARTIAL
- Execution engine = PARTIAL
- OMS building blocks = present but integrated pipeline missing
- Trading orchestrator = MISSING
- Strategy runtime = MISSING
- Signal runtime = MISSING
- Market-data ingestion = MISSING
- Live broker implementations = MISSING
- Portfolio engine = MISSING
- Live position engine = PARTIAL
- Live P&L computation = MISSING
- Reconciliation engine = MISSING
- Web = MISSING · Mobile = MISSING · Desktop = MISSING
- Live trading = blocked

---

## 3. Status Vocabulary & Completion Gate

Exactly one status per capability: `PRODUCTION` · `ACTIVE_DEVELOPMENT` · `PARTIAL` · `PROTOTYPE` · `EXPERIMENTAL` · `DEPRECATED` · `PLANNED` · `MISSING` · `UNKNOWN`.

Completion-gate progression (a capability reaches `PRODUCTION` only when implementation + dependencies + contracts + persistence + security + failure behavior + tests + integration + e2e + observability + documentation all hold):

```
MISSING → IMPLEMENTING → PARTIAL → INTEGRATED → TESTED → VERIFIED → PRODUCTION
```

Per-capability gate record (used from Phase 1 onward): `Capability | Before | Current | Dependencies | Tests | Evidence | Final Status`. At this Phase-0 baseline, `Before == Current` (the column below labeled **Current Status**), and `Final Status` == `Current Status`.

---

## 4. Implementation Phase Map (mandatory order, §7)

| Phase | Subsystem |
|---|---|
| 0 | Baseline & audit synchronization |
| 1 | Foundation hardening |
| 2 | Database runtime |
| 3 | Market data runtime |
| 4 | Strategy runtime |
| 5 | Signal engine |
| 6 | Live risk engine |
| 7 | Trading orchestrator |
| 8 | OMS |
| 9 | Execution engine |
| 10 | Broker adapters |
| 11 | Position engine |
| 12 | Portfolio engine |
| 13 | P&L engine |
| 14 | Reconciliation |
| 15 | Paper trading |
| 16 | Backtesting expansion (where justified) |
| 17 | Web terminal |
| 18 | Mobile |
| 19 | Desktop |
| 20 | Observability |
| 21 | Event architecture (where justified) |
| 22 | CI/CD |
| 23 | Full system verification |
| 24 | Controlled LIVE readiness |

---

## 5. Master Capability Status Matrix

Columns: `Capability | Current Status | Target Phase | Owner/Module | Dependencies | Verification Requirement`.

### 5.1 Foundation (Phase 1 — COMPLETE)

| Capability | Current Status | Target Phase | Owner/Module | Dependencies | Verification Requirement |
|---|---|---|---|---|---|
| Runtime dependencies | TESTED | 1 | `pyproject.toml` | `psycopg[binary]`, `uvicorn`, `pydantic-settings`, `argon2-cffi` declared + installed | clean-venv `pip install` succeeds |
| Production authentication | TESTED | 1 | `apps/api/alpha_algo_api/auth.py` | stdlib HS256 JWT, Argon2id | JWT signature/expiry/issuer/audience/type verified (unit tests) |
| Session/token lifecycle | TESTED | 1 | `security/tokens.py`; `routes/auth.py` | access + refresh, type separation | refresh/expiry/tamper/type-confusion tests |
| RBAC enforcement | TESTED | 1 | `auth.py`; `rbac.py` | `require_permission` + `resolve_user_permissions` | 401/403 enforcement; union of role permissions |
| Rate limiting | TESTED | 1 | `rate_limit.py` | sliding window, trust-proxy-gated, memory-bounded | 429 `RATE_LIMITED` after limit; disabled = no-op |
| Safe CORS | TESTED | 1 | `main.py` | `CORSMiddleware` + explicit allowlist | allowed Origin gets ACAO; disallowed gets none |
| PostgreSQL driver | TESTED | 1 | `pyproject.toml`; `db.py` | `psycopg[binary]>=3.2` + lazy engine | `psycopg` imports; engine lazy (no connect at import) |
| ASGI server | TESTED | 1 | `scripts/run_api.py`; `apps/api/Dockerfile` | `uvicorn` + entrypoint | `uvicorn` boots and serves `/health` |
| Runtime configuration | TESTED | 1 | `config.py` | pydantic-settings + `.env` | config loads `.env`, validates, fail-closed |
| Secret handling | TESTED | 1 | `security/secret.py`; `config.py` | placeholder detection, production rejection | no plaintext secrets; no secret/token leak |
| Secure errors | PRODUCTION | 1 | `errors.py` | — | JSON envelope + request-id on 401/403/404/422/429/500 |
| API security | TESTED | 1 | `apps/api/alpha_algo_api/` | auth/RBAC/CORS/rate-limit | unauthenticated→401, forbidden→403, malformed→422, no leak |

### 5.2 Database Runtime (Phase 2 - COMPLETE)

| Capability | Current Status | Target Phase | Owner/Module | Dependencies | Verification Requirement |
|---|---|---|---|---|---|
| PostgreSQL connectivity | TESTED | 2 | `db.py` (`ping_database`, `_probe`) | psycopg + `SELECT 1` probe | probe succeeds when reachable (mocked) |
| SQLAlchemy sessions | TESTED | 2 | `db.py` (`get_session_factory`, `get_db`) | sessionmaker + DI | session-per-request + close on teardown |
| Connection pool | TESTED | 2 | `db.py` (`get_engine`) | QueuePool + pool_size/max_overflow/timeout/recycle/pre_ping | pool config wired (live verification deferred) |
| Migrations | PRODUCTION | 2 | `migrations/` + `scripts/migrate.py` | `.env` loading + programmatic runner | `alembic upgrade head` clean |
| Transaction handling | TESTED | 2 | `db.py` (`session_scope`) | unit-of-work | COMMIT on success |
| Rollback | TESTED | 2 | `db.py` (`session_scope`) | explicit rollback | no partial state on failure |
| Retry/reconnect | TESTED | 2 | `db.py` (`run_with_retry`) | bounded linear backoff | bounded retry on transient conn errors |
| Query timeout | TESTED | 2 | `db.py` (`_connect_args`) | `statement_timeout` connect arg | server-side timeout wired |
| DB health | TESTED | 2 | `routes/system.py` (`/ready`) | `ping_database` | `/ready` returns `database: ok|error` |
| Startup verification | TESTED | 2 | `main.py` (lifespan) | `verify_database_ready` | fail fast in prod; warn in dev |
| Shutdown handling | TESTED | 2 | `main.py` (lifespan) + `db.py` (`dispose_engine`) | dispose + RLock | graceful close, idempotent |

> Phase 2 capabilities are marked **TESTED** (implemented + unit-tested + integrated). Live PostgreSQL connectivity, real pool behavior under load, and end-to-end `alembic upgrade head` against a live DB are deferred (no Docker/PostgreSQL in this environment) and must be re-verified at VERIFIED/PRODUCTION time.


### 5.3 Market Data (Phase 3 — COMPLETE)

| Capability | Current Status | Target Phase | Owner/Module | Dependencies | Verification Requirement |
|---|---|---|---|---|---|
| Provider interface | TESTED | 3 | `services/market_data/.../provider.py` | async `MarketDataProvider` Protocol | fake provider satisfies contract (unit tests) |
| Provider authentication | TESTED | 3 | `provider.py` + `fake_provider.py` | `ProviderHealth.authenticated` + auth-fail error | auth failure raises + health reports auth (unit tests) |
| Subscription management | TESTED | 3 | `provider.py` + `service.py` | subscribe/unsubscribe routing | symbols routed via `set_event_handler` (integration test) |
| Reconnect | TESTED | 3 | `connection.py` (`Reconnector`) | bounded exponential backoff + connect timeout | auto-reconnect within bounded attempts (unit tests) |
| Heartbeat | TESTED | 3 | `connection.py` (`HeartbeatMonitor` + watchdog) | heartbeat monitor + `run_monitor` | dead connection detected + reconnected (unit tests) |
| Timeout | TESTED | 3 | `connection.py` + `engine.py` (staleness max_age) | connect-timeout + staleness | timeout aborts; staleness enforced (unit tests) |
| Sequence handling | TESTED | 3 | `safety.py` (bounded `DuplicateTickDetector`) + `ConnectionState` | bounded LRU dedup + state transitions | duplicate `(broker, sequence)` deduped; state machine enforced |
| Duplicate detection | PRODUCTION | 3 | `market_data/safety.py` | — | same `(broker, sequence)` deduped (now bounded) |
| Stale-data detection | PRODUCTION | 3 | `market_data/safety.py` | — | future/stale/fresh classified |
| Backpressure | TESTED | 3 | `backpressure.py` (`BoundedQueue`) + `engine.py` | bounded queue + drop policy | overflow handled without OOM; drops counted+logged |
| Normalized tick | PRODUCTION | 3 | `contracts/market_data.py` (MarketTick) | — | tz, ltp>0, extra-field reject |
| Normalized candle | PRODUCTION | 3 | `contracts/market_data.py` (MarketCandle) | — | OHLC range/timeframe/tz validation |
| Historical ingestion | TESTED | 3 | `historical.py` (`HistoricalDataClient`) | page-based cursor pagination + retry | candles/ticks pageable + bounded (unit tests) |

> Phase 3 capabilities are marked **TESTED** (implemented + unit-tested + integration-tested). Live provider connectivity and real end-to-end vendor-feed verification are deferred (no Docker/PostgreSQL/providers in this environment) and must be re-verified at VERIFIED/PRODUCTION time. The deterministic helpers/contracts (duplicate/stale detection, normalized tick/candle) retain their Phase-0 **PRODUCTION** status as pure deterministic components.

### 5.4 Strategy Runtime (Phase 4 — COMPLETE)

| Capability | Current Status | Target Phase | Owner/Module | Dependencies | Verification Requirement |
|---|---|---|---|---|---|
| Strategy registry | TESTED | 4 | `services/strategy_engine/.../registry.py` | `StrategyDefinition` + `StrategyIdentity` | register/unregister/discover/load/validate/enable/disable/status; dup prevention (id + code) |
| Lifecycle manager | TESTED | 4 | `services/strategy_engine/.../instance.py` + `state.py` | `RunStateMachine` (7 states) | `initialize→on_start→…→on_stop` ordering; illegal transitions rejected |
| Scheduler/event dispatcher | TESTED | 4 | `services/strategy_engine/.../dispatcher.py` | routing by instrument/timeframe/event-type/enabled/state | events routed to relevant RUNNING instances only |
| Startup/shutdown | TESTED | 4 | `services/strategy_engine/.../runtime.py` | `StrategyRuntime.start/stop/shutdown` | hooks fire on start/stop; shutdown non-blocking |
| Tick callback | TESTED | 4 | `instance.py` (`on_tick`) + `runtime.py` | `MarketTick` (Phase 3) | `on_tick` receives MarketTick → validated StrategySignal |
| Candle callback | TESTED | 4 | `instance.py` (`on_candle`) + `runtime.py` | `MarketCandle` (Phase 3) | `on_candle` receives MarketCandle → validated StrategySignal |
| Order-update callback | TESTED | 4 | `instance.py` + `runtime.on_order_update` | `OrderUpdate` stream | receives state transitions → signals |
| Position-update callback | TESTED | 4 | `instance.py` + `runtime.on_position_update` | `PositionUpdate` stream | receives quantity changes → signals |
| Configuration management | TESTED | 4 | `config.py` | `validate_config` + `compute_config_hash` | config validated, deep-frozen, hashed, injected |
| Version management | PRODUCTION | 4 | `contracts/signals.py` (StrategyVersion) | — | version/config_hash/code_hash validation |
| Runtime isolation | PRODUCTION | 4 | `strategies/.../lifecycle.py` | — | strategy cannot reach broker/network/live |

> Phase 4 capabilities are marked **TESTED** (implemented + unit-tested + integration-tested + adversarial-review-fixed). Live execution, OMS/Risk/Execution wiring, and signal persistence are deferred to Phase 5+ (no downstream consumers are registered; the runtime ends at a validated, traceable `StrategySignal`). Trading mode is fail-closed: only BACKTEST/PAPER are allowed; LIVE raises `TradingModeError`. The contract-level components (version management, runtime isolation) retain their Phase-0 **PRODUCTION** status.

### 5.5 Signal Engine (Phase 5 — COMPLETE)

| Capability | Current Status | Target Phase | Owner/Module | Dependencies | Verification Requirement |
|---|---|---|---|---|---|
| Strategy→StrategySignal | PRODUCTION | 5 | `lifecycle.py` (emit_signal) | — | identity match validation |
| Signal validation (contract) | PRODUCTION | 5 | `contracts/signals.py` (StrategySignal) | — | confidence 0–1, reason 1–500, tz |
| Traceability fields (9) | PRODUCTION | 5 | `contracts/signals.py` | — | `audit_key` reconstructs full lineage |
| Ingestion validation (boundary re-validation) | TESTED | 5 | `validation.py` | `StrategyDirectory` | 11 rejections with stable reason codes |
| Deterministic signal identity | TESTED | 5 | `identity.py` | SHA-256 | identity_key over strategy|version|config|instrument|action|event_ts |
| Content hashing (conflict detection) | TESTED | 5 | `identity.py` | SHA-256 | content_hash over confidence|reason|event_ts|metadata |
| Idempotency | TESTED | 5 | `idempotency.py` + `repository.py` | LRU + DB unique | duplicate/conflict; no silent overwrite; retry-safe |
| Signal state machine | TESTED | 5 | `state.py` + `service.py` | — | 8-state lifecycle enforced; illegal transitions rejected |
| Signal persistence | TESTED | 5 | `repository.py` → `signals` | SQLAlchemy + migration | transactional COMMIT; rollback+re-raise |
| Trading-mode gate | TESTED | 5 | `validation.py` + `service.py` | `TradingModeError` | BACKTEST/PAPER accepted; LIVE rejected |
| Phase-6 consumer fan-out | TESTED | 5 | `service.py` (`add_consumer` + `SignalRecord`) | — | consumers fire only on durable PERSISTED |

> Phase 5 capabilities are marked **TESTED** (implemented + unit-tested + integration-tested + 4-axis-review-fixed). Live PostgreSQL connectivity and end-to-end DB-backed verification are deferred (no Docker/PostgreSQL in this environment). Risk/OMS/Execution/Broker/LIVE are deferred to Phase 6+. The contract-level components (Strategy→StrategySignal, signal validation, traceability fields) retain their Phase-0 **PRODUCTION** status.

### 5.6 Live Risk (Phase 6 — COMPLETE)

| Capability | Current Status | Target Phase | Owner/Module | Dependencies | Verification Requirement |
|---|---|---|---|---|---|
| Immutable risk snapshot | TESTED | 6 | `snapshot.py` (RiskSnapshot + nested) | authoritative runtime state | single coherent read; freshness + staleness |
| Fail-closed state provider | TESTED | 6 | `state.py` (RiskStateProvider + Unavailable) | — | unavailable → REJECT |
| Runtime context build | TESTED | 6 | `context.py` (RiskContextBuilder/Validator) | snapshot + signal + intent | fail-closed on missing/mismatched state |
| Kill switch / global halt | PRODUCTION | 6 | `engine.py` (GlobalHaltRule) | GlobalHaltState | REJECT when halt active; runs first |
| Live-mode gate | PRODUCTION | 6 | `engine.py` (LiveModeRule) + `service.py` | live flag | REJECT when LIVE+disabled |
| Broker health | PRODUCTION | 6 | `engine.py` (BrokerHealthRule) | broker state | REJECT when disconnected |
| Market-data freshness | PRODUCTION | 6 | `engine.py` (MarketDataFreshnessRule) | staleness source | REJECT when stale |
| Market session | PRODUCTION | 6 | `engine.py` (MarketSessionRule) | session calendar | REJECT when closed |
| Instrument restriction | PRODUCTION | 6 | `engine.py` (InstrumentRestrictionRule) | allow-list | REJECT when not allowed |
| Order quantity limit | PRODUCTION | 6 | `engine.py` (QuantityLimitRule) | order/max qty | REJECT over-limit/zero |
| Position limit | PRODUCTION | 6 | `engine.py` (PositionLimitRule) | projected position | REJECT on breach |
| Exposure limit | PRODUCTION | 6 | `engine.py` (ExposureLimitRule) | projected exposure | REJECT on breach |
| Daily loss limit | PRODUCTION | 6 | `engine.py` (DailyLossLimitRule) | daily realized P&L | REJECT on breach |
| Strategy loss limit | PRODUCTION | 6 | `engine.py` (StrategyLossLimitRule) | strategy P&L | REJECT on breach |
| Margin availability | PRODUCTION | 6 | `engine.py` (MarginAvailabilityRule) | margin | REJECT when insufficient |
| Duplicate-order protection | PRODUCTION | 6 | `engine.py` (DuplicateOrderProtectionRule) | signal dedup | REJECT when duplicate |
| Maximum open positions | PRODUCTION | 6 | `engine.py` (MaximumOpenPositionsRule) | open count | REJECT at max |
| Max drawdown control | TESTED | 6 | `engine.py` (MaximumDrawdownRule) | drawdown source | REJECT on drawdown breach |
| Price deviation control | TESTED | 6 | `engine.py` (PriceDeviationRule) | reference + tolerance | REJECT on out-of-band |
| Order frequency control | TESTED | 6 | `engine.py` (OrderFrequencyRule) | per-window counter | REJECT on rate breach |
| Account-level limits | TESTED | 6 | `engine.py` (AccountLimitRule) | account profile | REJECT on account breach |
| Execution timeout | TESTED | 6 | `engine.py` (ExecutionTimeoutRule) | unresolved-execution count | REJECT at limit |
| Retry safety | TESTED | 6 | `engine.py` (RetrySafetyRule) + `service.py` | bounded-retry policy | no duplicate submits |
| Approval binding + expiry | TESTED | 6 | `approval.py` | signal identity + intent | unexpired, bound, non-reusable |
| Idempotent persistence | TESTED | 6 | `repository.py` + `safety.py` (`risk_events.identity_key`) | SQLAlchemy + migration | COMMIT = truth; identity dedup |
| Risk service orchestration | TESTED | 6 | `service.py` (RiskService) | provider + engine + repository | deterministic; fan-out after durable commit |
| Actual circuit breaker | TESTED | 6 | `circuit_breaker.py` (CircuitBreaker + Registry) | threshold/trigger | trip + reset on failures |
| Fail-closed defaults | PRODUCTION | 6 | `engine.py` + `gates.py` | — | defaults fail-closed (17 gates False) |

> Phase 6 capabilities are marked **TESTED** (implemented + unit-tested + integration-tested + 4-axis-review-fixed). Live PostgreSQL connectivity and a real runtime state provider (positions/P&L/portfolio are Phase 11+) remain deferred; the default provider fails closed. The engine ends at `RiskDecision → APPROVED/REJECTED`; OMS/execution/LIVE are Phase 7+. The contract-level rule classes (14 core rules + fail-closed defaults) retain their Phase-0 **PRODUCTION** status.

### 5.7 Trading Orchestrator (Phase 7 — COMPLETE)

| Capability | Current Status | Target Phase | Owner/Module | Dependencies | Verification Requirement |
|---|---|---|---|---|---|
| Orchestration state machine | TESTED | 7 | `services/trading_engine/.../state.py` | — | deterministic transitions; terminal states locked |
| Orchestration identity | TESTED | 7 | `services/trading_engine/.../identity.py` | signal identity | SHA-256 over signal+run+qty+account+order-type+mode |
| Order-intent resolution | TESTED | 7 | `services/trading_engine/.../intent.py` | resolver protocol | fail-closed default; never invents quantity |
| Action validation | TESTED | 7 | `services/trading_engine/.../service.py` | SignalAction | BUY/SELL/EXIT; HOLD/unknown → no intent |
| Risk consumption | TESTED | 7 | `service.py` → RiskService | Phase 6 | evaluate before OMS; rejected stops flow |
| Approval re-validation | TESTED | 7 | `service.py` → `approval_is_usable` | Phase 6 binding | expiry + binding; PRIOR_APPROVAL_INVALID preserved |
| Idempotency | TESTED | 7 | `service.py` + `repository.py` | unique `orchestration_id` | replay → DUPLICATE; no second intent |
| Transaction boundary | TESTED | 7 | `repository.py` → `trading_intents` | SQLAlchemy + migration | COMMIT = truth; no false success |
| Concurrency control | TESTED | 7 | `service.py` (RLock) | — | narrow critical section; no global lock |
| OMS handoff port | TESTED | 7 | `oms_port.py` (OmsPort/NoOpOmsPort) | — | explicit notification boundary; never a broker |
| Trading-mode gate | TESTED | 7 | `service.py` | — | BACKTEST/PAPER allowed; LIVE/unknown blocked |
| Observability | TESTED | 7 | `metrics.py` (OrchestrationMetrics) | — | received/rejected/risk/dup/persist/handoff/latency |
| End-to-end orchestrator | TESTED | 7 | `services/trading_engine/` | Phases 5 + 6 | Signal → Risk → Orchestrator → OMS-ready Intent |

> Phase 7 capabilities are marked **TESTED** (implemented + unit-tested + integration-tested + 4-axis-review-fixed). Live PostgreSQL connectivity and the downstream OMS (Phase 8) are deferred. The pipeline ends at an OMS-ready `TradingIntent`; no broker/live execution is introduced. LIVE remains **fail-closed**.

### 5.8 OMS (Phase 8)

| Capability | Current Status | Target Phase | Owner/Module | Dependencies | Verification Requirement |
|---|---|---|---|---|---|
| Order lifecycle state machine (11 states) | PRODUCTION | 8 | `execution_engine/lifecycle.py` | — | transitions enforced |
| Intent (INTENT_CREATED) | PRODUCTION | 8 | `lifecycle.py` + `submission.py` | StrategySignal | initial state + approval id |
| Order creation | PRODUCTION | 8 | `lifecycle.py` | — | legal transition |
| Order validation | TESTED | 8 | `services/oms/validation.py` | intent/spec | quantity/action/type/account/mode/halt checks |
| Idempotency | TESTED | 8 | `services/oms/identity.py` + `repository.py` | unique `order_identity_key` | replay → duplicate; conflict → CONFLICT |
| Submission (SUBMISSION_REQUESTED) | TESTED | 8 | `services/oms/service.py` + `boundary.py` | re-validated approval | guard enforced; stops at Execution Port |
| Acknowledgment (BROKER_ACKNOWLEDGED) | PRODUCTION | 8 | `events.py` | broker ACK | transition driven |
| Partial fills (PARTIALLY_FILLED) | PRODUCTION | 8 | `events.py` (`_apply_partial_fill`) | PARTIAL_FILL event | accumulation + overfill guard |
| Fills (FILLED) | PRODUCTION | 8 | `events.py` (`_apply_fill`) | FILL event | exact quantity required |
| Rejection (REJECTED) | PRODUCTION | 8 | `events.py` | REJECTED event | transition |
| Cancel request (CANCEL_REQUESTED) | TESTED | 8 | `services/oms/service.py` | broker cancel support (Phase 9) | internal request; distinct from CANCELLED |
| Cancellation confirmation (CANCELLED) | PARTIAL | 8 | `lifecycle.py` + `events.py` | broker confirm | defined; unreachable end-to-end |
| Unknown state (UNKNOWN) | PRODUCTION | 8 | `events.py` + `lifecycle.py` | UNKNOWN event | UNKNOWN→RECONCILIATION_REQUIRED |
| Reconciliation-required | PARTIAL | 8 | `lifecycle.py` | reconciliation engine | state defined; no engine consumes |
| Traceable transition events | PRODUCTION | 8 | `lifecycle.py` (OrderStateTransition) | `order_events` table | append-only transitions |

### 5.9 Execution (Phase 9 — COMPLETE)

| Capability | Current Status | Target Phase | Owner/Module | Dependencies | Verification Requirement |
|---|---|---|---|---|---|
| Execution dispatch | TESTED | 9 | `services/execution_engine/.../engine.py` | `ExecutionAdapter` + guard | send intent to concrete adapter (no broker SDK) |
| Execution timeout | TESTED | 9 | `engine.py` | submission→ack clock | timeout → UNKNOWN (never blind retry) |
| Execution cancellation | TESTED | 9 | `engine.py` + `adapter.py` | authoritative cancel confirm | CANCELLED only on confirmation; ambiguous → UNKNOWN |
| Safe retry | TESTED | 9 | `engine.py` + `errors.py` | idempotency + bounded retry | no double-fill; TRANSIENT_FAILURE-only retry |
| Broker response handling | TESTED | 9 | `engine.py` (`_process_response`) | `ExecutionResponse` | status → outcome/order-state mapping |
| Partial fills (execution) | PRODUCTION | 9 | `events.py` | PARTIAL_FILL event | transitions + overfill guard (accumulation via `apply_event`) |
| Duplicate protection (execution) | TESTED | 9 | `engine.py` + `repository.py` | `execution_id` + attempt unique | idempotent submission + event dedup/conflict |
| Execution event processing | PRODUCTION | 9 | `events.py` (`apply_event`) | BrokerOrderEvent | all types drive transitions |
| Reconciliation triggers | PARTIAL | 9 | `lifecycle.py` | reconciliation engine | flags exist; no consumer (Phase 14) |

> Phase 9 capabilities are marked **TESTED** (implemented + unit-tested + integration-tested + 4-axis-review-fixed). Concrete broker adapters are deferred to Phase 10; the engine ends at a provider-neutral `ExecutionAdapter` boundary with a deterministic TEST adapter. Live PostgreSQL connectivity remains deferred (in-memory execution store mirrors the transactional + unique-constraint semantics).

### 5.10 Broker Integration (Phase 10)

| Capability | Current Status | Target Phase | Owner/Module | Dependencies | Verification Requirement |
|---|---|---|---|---|---|
| BrokerAdapter Protocol + concrete adapters | PARTIAL | 10 | `packages/broker_adapters/.../contracts.py` | — | Protocol; only PaperBrokerAdapter concrete |
| Capability-gated providers | PARTIAL | 10 | `contracts.py` (BrokerCapabilities) | — | Paper reports supports_live_trading=False |
| No scattered broker branching | PRODUCTION | 10 | `broker_adapters/` | — | import isolated behind Protocol |

### 5.11 Position / Portfolio / P&L / Reconciliation (Phases 11–14)

| Capability | Current Status | Target Phase | Owner/Module | Dependencies | Verification Requirement |
|---|---|---|---|---|---|
| Position engine (live, authoritative) | PARTIAL | 11 | `paper_trading/` (PaperPosition/PaperOrderBook); `positions` table (schema) | execution-event wiring; P&L engine; DB runtime | live position from events + persisted |
| Portfolio engine | MISSING | 12 | `services/portfolio_engine/` (`.gitkeep`); `portfolio_snapshots` (schema) | position + P&L engines | value/cash/exposure/allocation/drawdown persisted |
| P&L engine (live) | MISSING | 13 | (backtest-only FIFO P&L in `backtesting/.../ledger.py`) | position/fill records; CostModel | realized+unrealized+net at trade/strategy/account/daily |
| Reconciliation | MISSING | 14 | `services/reconciliation_engine/` (`.gitkeep`) | orders/executions/positions/funds/P&L | mismatch detection + persisted events + no silent overwrite |

### 5.12 Simulation (Phases 15–16)

| Capability | Current Status | Target Phase | Owner/Module | Dependencies | Verification Requirement |
|---|---|---|---|---|---|
| Paper trading (full path) | PARTIAL | 15 | `services/paper_trading/` | strategy/signal/risk/OMS runtime + persistence + P&L | end-to-end paper through P&L, as pre-live gate |
| Backtesting (deterministic) | PRODUCTION | 16 | `backtesting/` (4 packages) | contracts; Decimal foundation | identical inputs → identical results; no-live-access |

### 5.13 Platform (Phases 17–19)

| Capability | Current Status | Target Phase | Owner/Module | Dependencies | Verification Requirement |
|---|---|---|---|---|---|
| Web — auth | MISSING | 17 | `apps/web/` (`.gitkeep`) | backend auth | login vs real backend |
| Web — dashboard | MISSING | 17 | `apps/web/` (`.gitkeep`) | API + WS | live portfolio rendered |
| Web — watchlist | MISSING | 17 | `apps/web/` (`.gitkeep`) | market-data API | stream quotes |
| Web — market data & charts | MISSING | 17 | `apps/web/` (`.gitkeep`) | market-data runtime + charts | charts render ticks/candles |
| Web — positions/orders/portfolio/P&L | MISSING | 17 | `apps/web/` (`.gitkeep`) | engines | live state rendered |
| Web — Tier 2 | MISSING | 17 | `apps/web/` (`.gitkeep`) | risk/broker/alerts APIs | Tier 2 screens |
| Web — Tier 3 | MISSING | 17 | `apps/web/` (`.gitkeep`) | backtesting/audit/admin | Tier 3 screens |
| Mobile — Tier 1 | MISSING | 18 | (no `apps/mobile`) | backend contracts | Flutter app vs API |
| Mobile — Tier 2 | MISSING | 18 | (no `apps/mobile`) | Tier 1 + risk/alert APIs | Tier 2 screens |
| Mobile — Tier 3 | MISSING | 18 | (no `apps/mobile`) | backtesting API | Tier 3 screens |
| Desktop — Windows | MISSING | 19 | (no `apps/desktop`) | shared Flutter core | Windows build |
| Desktop — macOS | MISSING | 19 | (no `apps/desktop`) | shared Flutter core | macOS build |

### 5.14 Operations & Live Readiness (Phases 20–24)

| Capability | Current Status | Target Phase | Owner/Module | Dependencies | Verification Requirement |
|---|---|---|---|---|---|
| Observability — metrics | PARTIAL | 20 | `infra/prometheus/`, `docker-compose.yml` | app instrumentation | Prometheus scrapes app targets |
| Observability — structured logs | PARTIAL | 20 | `middleware.py` (request-id) | structured logging | structured log lines |
| Observability — tracing | MISSING | 20 | — | OTel SDK | spans across engines |
| Observability — alerts | MISSING | 20 | `services/notification_engine/` (`.gitkeep`) | alert engine | alerts fire on thresholds |
| Event architecture — internal | PARTIAL | 21 | `contracts/events.py`, `execution_engine/events.py` | orchestrator | internal event flow |
| Event architecture — broker | MISSING | 21 | — | scale justification | broker only if justified |
| CI/CD — format/lint/type | MISSING | 22 | `.github/workflows/ci.yml` | ruff/black/mypy | CI runs checks |
| CI/CD — test/security/build/migration | PARTIAL | 22 | `.github/workflows/ci.yml` | test matrix + Docker | CI full pipeline |
| Live release — safety gates (24+) | PARTIAL | 23 | `gates.py` (17/17 TODO) | all engines + controls | all gates verified |
| Live release — SHADOW→FULL | MISSING | 24 | — | Phase 23 + ops | controlled progression |
| Kill switch | PARTIAL | 23 | `gates.py` (GlobalHaltState) | live orchestration | halts live instantly |
| Circuit breaker (actual) | MISSING | 23 | `gates.py` (flag only) | live wiring | trips + resets |

---

## 6. Summary Counts

- **Total capabilities tracked:** ~153 (Foundation 12 · Database 11 · Market Data 13 · Strategy 11 · Signal 11 · Risk 28 · Orchestrator 13 · OMS 15 · Execution 9 · Broker 3 · Position/Portfolio/P&L/Reconciliation 4 · Simulation 2 · Platform 12 · Operations/Live 9).
- **PRODUCTION today:** deterministic backtesting; migration scripts; secure-error envelope; core market-data contracts + dedup/staleness helpers; signal/strategy contracts + versioning + runtime isolation; 20 risk rule classes (14 core + 6 configurable) + fail-closed defaults; 11-state order lifecycle + event engine.
- **MISSING today (highest-impact):** concrete brokers, portfolio/P&L/reconciliation engines, web/mobile/desktop, tracing/alerts/CI, and all LIVE release paths. (Phase 1 auth/RBAC/CORS/rate-limit + ASGI/psycopg, Phase 2 DB runtime, Phase 3 market-data runtime, Phase 4 strategy runtime, Phase 5 signal engine, Phase 6 live risk engine, Phase 7 trading orchestrator, Phase 8 OMS, and Phase 9 execution engine are now **TESTED**.)

---

*End of IMPLEMENTATION_STATUS.md — Phase 0 baseline. Read-only; source of truth remains the repository code. Subsequent phases update this document after each change (per §33 and §43).*
