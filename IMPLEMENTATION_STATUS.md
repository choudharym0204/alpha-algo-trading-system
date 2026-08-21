# IMPLEMENTATION_STATUS.md

**Project:** Alpha Algo Trading System
**Document purpose:** Phase 0 - Baseline Synchronization (implementation-control document).
**Repository:** `projects/alpha-algo-trading-system/`
**Date:** 2026-08-18
**Execution mode:** Architecture-Preserving Incremental Implementation

> **Read-only baseline discovery.** This document records the current capability status, dependencies, target phase, owner module, and verification requirement for every tracked capability. It is derived from the 10 audit registers (`CURRENT_ARCHITECTURE_REGISTER.md`, `TECHNOLOGY_STACK_REGISTER.md`, `TRADING_ENGINE_REGISTER.md`, `PROVIDER_INTEGRATION_REGISTER.md`, `PLATFORM_CAPABILITY_MATRIX.md`, `DEPENDENCY_REGISTER.md`, `ARCHITECTURE_DEPENDENCY_GRAPH.md`, `SINGLE_POINT_OF_FAILURE_REGISTER.md`, `TECHNOLOGY_COUPLING_REGISTER.md`, `AUDIT_SUMMARY.md`) and verified against source. **No code was modified.**

---

## 0. Phase 1 - Foundation Hardening (COMPLETE)

Phase 1 was implemented and verified on 2026-08-18 (see `.cluster/alpha-algo-phase1/DELIVERY/P1-session-report.md`). All §5.1 Foundation capabilities are now **TESTED** (implemented + unit-tested + integrated). They are intentionally **not** marked PRODUCTION/VERIFIED because live PostgreSQL and end-to-end DB-backed verification are deferred to Phase 2. Full suite: **618 tests passing**. LIVE remains **fail-closed**.

---

## 0b. Phase 2 - Database Runtime (COMPLETE)

Phase 2 was implemented and verified on 2026-08-18 (see `.cluster/alpha-algo-phase2/DELIVERY/P2-session-report.md`). All 5.2 Database Runtime capabilities are now **TESTED** (implemented + unit-tested + integrated). Live PostgreSQL connectivity, real pool behavior under load, and end-to-end `alembic upgrade head` against a live DB remain deferred (no Docker/PostgreSQL in this environment) and must be re-verified at VERIFIED/PRODUCTION time. Full suite: **651 tests passing**. LIVE remains **fail-closed**.

---

## 0c. Phase 3 - Market Data (COMPLETE)

Phase 3 was implemented and verified on 2026-08-18 (see `.cluster/alpha-algo-phase3/DELIVERY/P3-session-report.md`). The market-data runtime - provider abstraction, connection lifecycle (reconnect/backoff/heartbeat/timeout/watchdog), streaming pipeline with bounded backpressure, validation/normalization safety, TimescaleDB persistence, historical retrieval (page-based pagination + retry), composition root, and observability metrics - is now **TESTED** (implemented + unit-tested + integration-tested). Live provider connectivity (real broker/market-data vendor feeds) remains deferred (no real providers in this environment) and must be re-verified at VERIFIED/PRODUCTION time. Full suite: **696 tests passing**. LIVE remains **fail-closed**.

---

## 0d. Phase 4 - Strategy Runtime (COMPLETE)

Phase 4 was implemented and verified on 2026-08-18/19 (see `.cluster/alpha-algo-phase4/DELIVERY/P4-session-report.md`). The strategy runtime - registry (register/unregister/discover/load/validate/enable/disable/status/duplicate-prevention), a 7-state lifecycle machine, strategy identity + deterministic config/code hashing, validated + deep-frozen config, per-instance isolation + signal validation + bounded LRU dedup, event dispatcher (instrument/timeframe/event-type/enabled/state routing), run records, observability metrics, the Phase-3→Phase-4 market-data boundary, and a reference SMA-crossover strategy - is now **TESTED** (implemented + unit-tested + integration-tested + adversarial-review-fixed). A 4-dimension adversarial review (strategy architecture; runtime/concurrency/isolation; signal correctness/data integrity; LIVE-safety/regression) was run; every legitimate finding was fixed and 7 regression tests added. Live execution and downstream OMS/Risk/Execution/signal-persistence wiring are deferred (no downstream consumers are registered; the runtime ends at a validated, traceable `StrategySignal`). Full suite: **759 tests passing** (Phase 4 added 63 tests over the verified 696-test baseline). LIVE remains **fail-closed** - only BACKTEST/PAPER are allowed; LIVE raises `TradingModeError`.

---

## 0e. Phase 5 - Signal Engine (COMPLETE)

Phase 5 was implemented and verified on 2026-08-19 (see `.cluster/alpha-algo-phase5/DELIVERY/P5-session-report.md`). The Signal Engine - the dedicated, persistent, deterministic, auditable boundary between the Phase-4 Strategy Runtime and the future Phase-6 Risk Engine - is now **TESTED** (implemented + unit-tested + integration-tested + 4-axis-review-fixed). It re-validates every `StrategySignal` at the boundary, enforces deterministic identity (`identity_key`) + content hashing, enforces an 8-state lifecycle machine, dedups via in-memory LRU + DB unique constraints, persists transactionally to PostgreSQL `signals` (COMMIT = truth boundary), and exposes a Phase-6 consumer fan-out (`add_consumer` + `SignalRecord`). Trading mode is fail-closed: only BACKTEST/PAPER are accepted; LIVE raises `TradingModeError`. Live DB connectivity and end-to-end DB-backed verification remain deferred (no Docker/PostgreSQL in this environment). Full suite: **827 tests passing** (Phase 5 added 68 tests over the 759-test baseline). LIVE remains **fail-closed**. Risk/OMS/Execution/Broker/LIVE are **not** implemented in this phase.

---

## 0f. Phase 6 - Live Risk Engine (COMPLETE)

Phase 6 was implemented and verified on 2026-08-19 (see `.cluster/alpha-algo-phase6/review.md` and `P6-session-report.md`). The Live Risk Engine - the runtime-connected, fail-closed decision boundary between the Phase-5 Signal Engine and the future Phase-7 Trading Orchestrator - is now **TESTED** (implemented + unit-tested + integration-tested + 4-axis-adversarial-review-fixed). It adds: an immutable `RiskSnapshot`, a fail-closed `RiskStateProvider` protocol, a `RiskContextBuilder`/`RiskContextValidator` (with snapshot↔intent identity + trading-mode reconciliation), six new configurable controls (max drawdown, price deviation, order frequency, account limits, execution-timeout, retry-safety), approval binding + expiry, an actual `CircuitBreaker` (closed/open/half-open) + registry, and durable idempotent persistence to `risk_events` keyed on a stable `identity_key`. `RiskService` is serialized (RLock) and fanned out **only after a durable COMMIT**; LIVE/unknown trading mode is rejected at the boundary. A 4-dimension adversarial review surfaced 2 BLOCKERs + ~10 MAJORs (global-halt replay bypass, non-durable idempotency, fan-out-on-failed-persist, fail-open exposure/drawdown, optional approval binding); **every BLOCKER/MAJOR was fixed**. Full suite: **928 tests passing** (Phase 6 added 101 tests over the 827-test Phase-5 baseline). Live PostgreSQL connectivity and a real runtime state provider (positions/portfolio/P&L are Phase 11+) remain deferred; the default provider fails closed. The engine ends at `RiskDecision → APPROVED/REJECTED`; OMS/execution/LIVE are **not** implemented in this phase.

---

## 0g. Phase 7 - Trading Orchestrator (COMPLETE)

Phase 7 was implemented and verified on 2026-08-19 (see `.cluster/alpha-algo-phase7/review.md` and `P7-session-report.md`). The Trading Orchestrator - the coordination layer connecting the Phase-5 Signal Engine → Phase-6 Risk Engine → an explicit OMS-ready handoff boundary - is now **TESTED** (implemented + unit-tested + integration-tested + 4-axis-adversarial-review-fixed). It verifies signal acceptance (PERSISTED + identity match), resolves the concrete order intent through a pluggable fail-closed resolver, validates action (BUY/SELL/EXIT; HOLD/unknown never mint an intent), drives Phase-6 risk evaluation, re-validates approval binding + expiry (`PRIOR_APPROVAL_INVALID` preserved), normalizes an OMS-ready `TradingIntent`, and persists it durably (`trading_intents`, `orchestration_id` unique) before an explicit OMS-port handoff notification. Idempotency is deterministic (signal identity + strategy run + quantity + account + order type + mode), concurrency is narrow (RLock around check-and-persist), and LIVE/unknown trading modes are blocked fail-closed. The 4-axis adversarial review surfaced 1 MAJOR (model↔migration metadata column drift) + 2 MINOR; all fixed. Full suite: **975 tests passing** (Phase 7 added 47 tests over the 928-test Phase-6 baseline). Live PostgreSQL connectivity and the downstream OMS (Phase 8) remain deferred. The pipeline ends at an `OMS-ready Intent` - **never** a broker. LIVE remains **fail-closed**.

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

## 0j. Phase 10 - Broker Adapters (COMPLETE)

Phase 10 was implemented and verified on 2026-08-20 (see `P10-session-report.md` and `review.md`). The broker-adapter layer - the **translation and isolation boundary** behind the Phase-9 Execution Engine - is now **TESTED** (implemented + unit-tested + contract-tested + 4-axis-adversarial-review-fixed).

It adds a universal broker framework (`services/broker_adapters/alpha_algo_broker_integration/`) and three concrete adapters:

- **Universal contract** - `BrokerAdapter` Protocol (auth/connect/health/reconnect/orders/account), `BrokerCapabilities` (full capability model), `BrokerOrderRequest`/`BrokerOrderResponse` (normalized), `BrokerPositionSnapshot`/`BrokerHoldingSnapshot`/`BrokerFundsSnapshot`, `BrokerConnectionConfig` (incl. static-IP prerequisite), `BrokerCredentialsRef` (opaque ref, no secret values).
- **Error model** - `BrokerError` + `BrokerErrorClass` (AUTHENTICATION/AUTHORIZATION/RATE_LIMIT/VALIDATION/ORDER_REJECTED/TIMEOUT/NETWORK/PROVIDER_UNAVAILABLE/NOT_FOUND/UNSUPPORTED/DUPLICATE/UNKNOWN) + retryability classification.
- **Connection lifecycle** - DISCONNECTED→CONNECTING→CONNECTED→DEGRADED→RECONNECTING with bounded, jittered backoff; reconnect never duplicates orders.
- **Rate limiting** - per-scope token-bucket, provider-specific policies.
- **Instrument/symbol mapping** - `BrokerInstrument` + `InstrumentMapping` (resolve + validate before submission; never guesses a broker instrument).
- **Order/product-type isolation** - unsupported order/product types rejected (`UNSUPPORTED`), never silently downgraded (e.g. Upstox has no NRML).
- **Event normalization + dedup** - `NormalizedBrokerEvent` + `EventDeduplicator` (duplicate → drop; same identity + different payload → conflict).
- **Concrete adapters** - Zerodha (Kite Connect v3), Upstox (API v2), Angel One (SmartAPI). Each has provider-specific status/error/order-type/product mapping + response/event parsers + auth (OAuth token / bearer / loginByPassword) isolated behind the boundary.

**LIVE safety is preserved**: `LIVE` trading mode is refused (`UNSUPPORTED`), `GLOBAL_TRADING_HALT` blocks all submission (fail-closed), no credentials are hardcoded/committed/logged, and no real broker SDK/secret is used in tests (fake placeholders only). Provider constraints are modelled explicitly: Zerodha (static IP since 2025-04-01) and Angel One (static IP since 2026-04-01) for order execution; Upstox V3 WebSocket (V2 discontinued 2025-08-22) + sandbox.

Full suite: **1194 tests passing** (Phase 10 added 77 tests over the 1117-test Phase-9 baseline). Live broker connectivity/credentials remain deferred (no real providers in this environment); adapters are unit/mocked-tested. Phase 11 (Position Engine) is now **COMPLETE - TESTED** (see §0k).

---

## 0k. Phase 11 - Position Engine (COMPLETE)

Phase 11 was implemented and verified on 2026-08-20 (see `P11-session-report.md` and `review.md`). The **Position Engine** - the durable, authoritative, idempotent state boundary between the Execution Engine and the future Portfolio/P&L/Reconciliation phases - is now **TESTED** (implemented + unit/arithmetic/identity/concurrency/repository/schema/security/E2E-tested + 4-axis-adversarial-review-fixed).

It adds `services/position_engine/alpha_algo_position_engine/` (contracts, identity, arithmetic, engine, repository, metrics, errors) and a migration adding `positions.last_execution_id` (`migrations/versions/20260820_position_engine.py`).

- **Canonical identity** = `(strategy_run_id, instrument_id, trading_mode)` (preserves the existing `uq_positions_*` constraint; `broker_account_id` is a recorded attribute, not a key).
- **Lifecycle** = FLAT / OPEN / CLOSED (derived from net quantity; `PARTIALLY_CLOSED` is derivable, not stored).
- **Long-only** - BUY opens/increases; SELL decreases/closes; short + flip rejected (`PositionOverCloseError`), never negative, never silently downgraded.
- **Weighted average entry** using exact `Decimal` arithmetic (4 dp, half-even).
- **Idempotent** - `position_events.source_event_id` (unique) is the durable execution-identity backstop; duplicate → no-op, conflict → preserved + evidence + `PositionConflictError`.
- **Atomic + concurrent-safe** - position + event committed in one transaction; per-key lock (in-process) + `SELECT ... FOR UPDATE` + unique constraints (cross-process); restart-reconstructable.
- **Boundary** - consumes normalized `PositionFill` (never broker SDK/payloads), never overwrites internal state from broker snapshots, never computes P&L (`realized_pnl`/`unrealized_pnl` left NULL - Phase 13 owns them), never enables LIVE.

Full suite: **1248 tests passing** (Phase 11 added 54 tests over the 1194-test Phase-10 baseline). Live PostgreSQL row-lock verification remains deferred (no Docker in this environment). Phase 12 (Portfolio Engine) is **not** started.

---

## 0l. Phase 12 - Portfolio Engine (COMPLETE)

Phase 12 was implemented and verified on 2026-08-20 (see `P12-session-report.md` and `review.md`). The **Portfolio Engine** - the broker-independent, deterministic, durable aggregation layer over authoritative positions + funds + reference prices - is now **TESTED** (implemented + identity/aggregation/exposure/market-value/funds/snapshot/concurrency/security/schema/E2E-tested + 4-axis-adversarial-review-fixed).

It adds `services/portfolio_engine/alpha_algo_portfolio_engine/` (contracts, errors, identity, aggregation, engine, repository, metrics, adapters), new queryable aggregate columns on `portfolio_snapshots` (`market_value`, `gross_exposure`, `net_exposure`, `long_exposure`, `short_exposure`, `position_count`, `available_margin`, `used_margin`, `status` + a `(broker_account_id, trading_mode)` index), and a migration (`migrations/versions/20260820_portfolio_engine.py`, down_revision `20260820_position_engine`).

- **Identity** = `(broker_account_id, trading_mode)`; snapshot = portfolio + `snapshot_at`; preserves `uq_portfolio_snapshots_account_mode_snapshot_at` as the durable boundary.
- **Aggregation** = exact `Decimal` (4-dp half-even); gross/net/long/short exposure; market value from normalized reference price (never average entry); open positions only.
- **Freshness** = FRESH/STALE/MISSING; missing → flagged + excluded (PARTIAL/DEGRADED), stale/future → flagged + DEGRADED; never fabricated zeros.
- **Funds/margin** = normalized `FundsState`; unavailable → `None` (never zero); margin reported as facts (Risk consumes, not re-ruled).
- **Snapshots** = append-only, atomic COMMIT; idempotent via unique constraint; deterministic recalculation; restart-reconstructable; on-demand only (no scheduler loop).
- **Boundary** = no P&L (`realized_pnl`/`unrealized_pnl` left NULL - Phase 13 owns them), no reconciliation (Phase 14), no broker calls, LIVE/unknown mode fail-closed.

Full suite: **1290 tests passing** (Phase 12 added 42 tests over the 1248-test Phase-11 baseline). Live PostgreSQL verification remains deferred (no Docker in this environment). Phase 13 (P&L Engine) is **not** started.

---

## 0m. Phase 13 - P&L Engine (COMPLETE)

Phase 13 was implemented and verified on 2026-08-20 (see `P13-session-report.md` and `review.md`). The **P&L Engine** - deterministic, auditable, broker-independent realized + unrealized P&L derived from authoritative execution/position facts - is now **TESTED** (implemented + accounting/unrealized/engine/aggregation/concurrency/security/schema/E2E-tested + 4-axis-adversarial-review-fixed).

It adds `services/pnl_engine/alpha_algo_pnl_engine/` (contracts, errors, identity, accounting, unrealized, aggregation, engine, repository, metrics), new tables `pnl_events` (append-only realized facts, `execution_id` unique) and `pnl_snapshots` (account-scoped read model), and a migration (`migrations/versions/20260820_pnl_engine.py`, down_revision `20260820_portfolio_engine`).

- **Accounting** = Weighted Average Cost (long-only); consumes Phase 11's authoritative average cost as the realized cost basis (never recomputes position truth).
- **Realized** = `(sell - avg_cost) × closed_qty`, net = gross - sell-side costs; exact `Decimal` (4-dp half-even).
- **Unrealized** = mark-to-market `(ref - avg) × open_qty` with Phase 3/12 freshness (missing/invalid → UNAVAILABLE, stale/future → DEGRADED).
- **Idempotency** = `pnl_events.execution_id` unique; duplicate → no-op, same identity + different payload → CONFLICT (original preserved).
- **Aggregation** = trade→position→strategy→account (sum of facts, no double-counting); daily P&L with configurable timezone.
- **Boundary** = no reconciliation (Phase 14), no broker calls, no P&L from UI/cache, historical facts immutable, LIVE/unknown mode fail-closed.

Full suite: **1349 tests passing** (Phase 13 added 59 tests over the 1290-test Phase-12 baseline). Live PostgreSQL verification remains deferred (no Docker in this environment). Phase 14 (Reconciliation Engine) is **not** started.

---

## 0n. Phase 14 - Reconciliation Engine (COMPLETE)

Phase 14 was implemented and verified on 2026-08-20 (see `P14-session-report.md` and `review.md`). The **Reconciliation Engine** - durable, deterministic, auditable comparison of internal authoritative state against broker observations - is now **TESTED** (implemented + order/execution/position/funds reconciliation + idempotency/concurrency/security/schema/E2E-tested + 4-axis-adversarial-review-fixed).

It adds `services/reconciliation_engine/alpha_algo_reconciliation_engine/` (contracts, errors, identity, tolerance, matching, engine, repository, metrics, adapters), new tables `reconciliation_runs` + `reconciliation_discrepancies` (append-only evidence, unique `discrepancy_key`), and a migration (`migrations/versions/20260820_reconciliation_engine.py`, down_revision `20260820_pnl_engine`).

- **Principle** = observation + correction-control; never silently overwrites internal financial truth.
- **Matching** = identity-first (broker order/execution ID → client ID → internal identity); deterministic; MATCH counted, non-MATCH persisted as evidence.
- **Taxonomy/severity** = smallest-useful `DiscrepancyKind`; INFO/WARNING/HIGH/CRITICAL (unexpected broker fill = CRITICAL).
- **Tolerance** = narrow, explicit, configurable (price/fee/funds epsilon + timestamp skew); stale/unavailable never fabricated as zero.
- **Corrective workflow** = broker-only fill → `ROUTE_BROKER_FILL` recovery action → existing execution boundary; no direct position/P&L/portfolio mutation.
- **Idempotency** = unique `discrepancy_key`; replay → no duplicate, same identity + different evidence → CONFLICT (original preserved).
- **Boundary** = no broker SDK/provider branch, no new accounting engine, LIVE/unknown mode + global halt fail-closed.

Full suite: **1412 tests passing** (Phase 14 added 63 tests over the 1349-test Phase-13 baseline). Live PostgreSQL verification remains deferred (no Docker in this environment).

---

## 0o. Phase 15 - Paper Trading Completion (COMPLETE)

Phase 15 was implemented and verified on 2026-08-20 (see `P15-session-report.md` and `review.md`). The **Paper Trading runtime** - the operational layer that completes the paper lifecycle on top of the P8-001 deterministic simulator foundation - is now **TESTED** (account/funds/run/costs/routing/service/persistence implemented + unit/E2E/determinism/isolation/security/schema-tested + 4-axis-adversarial-review-fixed).

It adds `services/paper_trading/alpha_algo_paper_runtime/` (account, funds, run, costs, routing, service, repository), three paper-specific tables `paper_runs` + `paper_accounts` + `paper_funds` (no duplicate order/execution/position storage), and a migration (`migrations/versions/20260820_paper_trading.py`, down_revision `20260820_reconciliation_engine`).

- **Account/run** = explicit PAPER account (pinned mode, explicit starting capital) + `paper_run_id` isolation + deterministic config-hash replay.
- **Funds** = deterministic cash/reserve ledger (never negative); insufficient-funds is a service-level pre-submission guard.
- **Cost model** = explicit (default ZERO) slippage (FIXED_BPS) + commission (FIXED_PER_TRADE); no tax formulas invented.
- **Mode routing** = BACKTEST/PAPER/LIVE; LIVE fail-closed, unknown/missing fail loud, never UI-string driven.
- **Service** = orchestrates account + funds + paper broker + cost model; fills flow through the broker → execution-events boundary (no direct Position/P&L mutation).
- **Persistence** = `SqlPaperRepository` + in-memory double; funds restart recovery tested.
- **Reconciliation** = paper state reconciles through Phase 14 (funds + positions E2E-tested).

Full suite: **1476 tests passing** (Phase 15 added 64 tests over the 1412-test Phase-14 baseline). Live PostgreSQL verification remains deferred (no Docker in this environment). Phase 16 (Backtesting Expansion) is **not** started.

---

## 0p. Phase 16 - Backtesting Expansion (COMPLETE)

Phase 16 was implemented and verified on 2026-08-20 (see `P16-session-report.md` and `review.md`). The deterministic backtesting subsystem was expanded with **six additive packages** (no existing engine file was modified):

- **`backtesting/alpha_algo_backtest_analytics/`** - advanced metrics: CAGR (explicit periods-per-year basis), historical VaR/CVaR (order-statistic, confidence-configurable), CAPM Alpha/Beta (aligned benchmark required), per-trade MFE/MAE (strict `(entry, exit]` window), and a composite `compute_advanced_metrics`.
- **`backtesting/alpha_algo_backtest_quality/`** - observational data-quality classification into `VALID` / `QUARANTINED` / `REJECTED` (out-of-order, duplicate, future-dated, gap, identity/timeframe drift, OHLC/tick sanity); no silent repair.
- **`backtesting/alpha_algo_backtest_optimize/`** - deterministic lexicographic grid search (first-evaluation tie-break, train/test separation by caller-closure) + reproducible seeded bootstrap Monte Carlo (SHA-256-derived PRNG, no `random` module).
- **`backtesting/alpha_algo_backtest_persistence/`** - optional outer-layer run identity (canonical SHA-256, wall-clock excluded) + stable JSON record + in-memory store with duplicate/conflict semantics + result-cache key.
- **`backtesting/alpha_algo_backtest_portfolio/`** - multi-symbol, shared-capital, long-only portfolio simulation with explicit capital allocation (reserved-cash floor + per-symbol budget caps); `(timestamp, symbol)`-sorted global timeline; reuses the single-engine fill/cost/FIFO semantics.
- **`backtesting/alpha_algo_backtest_latency/`** - deterministic latency model (signal/decision/submission/fill components) that shifts intent effective-decision time (simulation-time controlled, no wall-clock sleep).

**Explicitly DEFERRED / UNSUPPORTED** (documented in `P16-session-report.md` and `review.md`): STOP/STOP_LIMIT (intra-bar trigger unknowable on candle data), partial fills (would entangle 1:1 intent→outcome accounting), market impact (no defensible data/requirements), short selling / position flip (production Position Engine rejects short/flip), multi-timeframe data, corporate actions (`UNSUPPORTED / DOCUMENTED`), parallel optimization (sequential only).

**LIVE safety preserved**: `BacktestTradingMode` remains single-member (`BACKTEST`); no broker/network/live imports (AST-scanned); no wall-clock/random/os usage; persistence is an in-memory/JSON outer layer (no filesystem/DB writes); long-only sim rejects short/flip. Determinism and look-ahead protection verified end-to-end.

Full suite: **1611 tests passing** (Phase 16 added 135 tests over the 1476-test Phase-15 baseline), 1 pre-existing warning (FastAPI deprecation). Live PostgreSQL verification remains deferred (no Docker in this environment). Phase 17 (Web Platform) is **not** started.

---

## 0q. Phase 17 - Web Platform (COMPLETE)

Phase 17 was implemented and verified on 2026-08-20 (see `P17-session-report.md`, `review.md`, and `apps/web/README.md`). The **Web Trading Terminal** (`apps/web/`) - a presentation/control layer consuming the backend only through authenticated REST + WebSocket - is now **TESTED** (implemented + unit/component-tested + production-build-verified + 4-axis-adversarial-review-fixed).

**Honest scope (backend contract discovery):** the backend exposes only auth (`/api/v1/auth/login|refresh|me`), system (`/system/health|ready|request-id`), and an authenticated WebSocket gateway (`/api/v1/ws` → `HEALTH_UPDATE`). There are **no** trading-data endpoints yet (orders, positions, portfolio, P&L, strategies, risk, brokers, reconciliation, market data, watchlist).

What was built:
- **Auth** - real login/refresh/me/logout/session-restore/expiry/401/403 against the backend contract; tokens held **in memory only** (backend returns JSON tokens, sets no httpOnly cookie).
- **RBAC** - `system:read` gates the shell, `trading:view` gates trading areas; server 401/403 remains the authority.
- **Protected routing + app shell** - sidebar (permission-filtered), topbar, **PAPER/LIVE mode badge** (fail-closed from `health.live_trading`), WebSocket connection indicator, session controls, toast notifications.
- **Dashboard** - real system health/readiness (`service`, `api`/`database`/`broker` checks), LIVE-safety panel, real-time `HEALTH_UPDATE`; trading metrics shown **Unavailable** (never zero).
- **Design system** - Button/Input/Select/Modal/Table/Badge/Tabs/Toast/Tooltip/Skeleton/Empty/Error/Status (dot+text, non-color-only).
- **REST client** (typed, parses structured error envelope) + **WebSocket client** (reconnect + typed event validation).
- **Routes** - `login`, `dashboard` (real), `settings` (real session/permissions), and `markets...alerts` as honest Unavailable states.

**LIVE safety preserved:** `live_trading` reflect-only (no toggle, no LIVE path); broker credentials/tokens never reach the browser; no broker/DB access from the browser.

Verification: **29 web tests passing** (7 files); production build green (19 routes, strict TypeScript); backend regression unchanged at **1611 passed** (1 pre-existing warning). Live backend E2E and trading-data wiring remain deferred (no Docker/PostgreSQL; no backend trading-data endpoints).

---

## 0r. Phase 18 - Mobile Platform (TESTED; real PostgreSQL auth + device E2E GREEN)

Phase 18 was **implemented** on 2026-08-20 (see `P18-session-report.md`, `review.md`, and `apps/mobile/README.md`). The **Flutter mobile foundation** (`apps/mobile/`) - a presentation/control layer consuming the backend only through authenticated REST + WebSocket - is written. On **2026-08-21** the agent installed the missing toolchain (Flutter 3.47.1, Dart 3.13.1, JDK 17, Android SDK 36) and executed every runnable gate: `flutter analyze` → **0 issues**, `flutter test` → **23/23 passed**, `flutter build apk --debug` → `app-debug.apk` (158 MB), `flutter build apk --release` → `app-release.apk` (48.4 MB), and installed + launched the app on a **real Pixel 6 / Android 16** with no crash. Platform folders (`android/`/`ios/`/...) were generated via `flutter create` without discarding existing source. Backend regression re-run: **1611 passed**.

**Honest scope (backend contract):** the backend exposes only auth (`/auth/login|refresh|me`), system (`/system/health|ready`), and an authenticated WebSocket gateway (`/api/v1/ws` → `HEALTH_UPDATE`). No trading-data endpoints exist.

What was written:
- **Auth** - login/refresh/me/logout/restore/expiry/401/403; tokens in `flutter_secure_storage` (Keystore/Keychain backed).
- **RBAC + navigation** - `system:read` gates the shell, `trading:view` gates trading tabs; server 401/403 remains authoritative.
- **Shell** - bottom nav, PAPER/LIVE mode badge (fail-closed), connection indicator, session controls.
- **Dashboard** - real health/readiness (`service`, `api`/`database`/`broker`) + LIVE-safety + WS status; trading metrics shown **Unavailable** (never zero).
- **Typed REST client** (structured error envelope) + **WebSocket client** (reconnect + typed event validation) + **system polling** (staleness).
- **Design system** + 8 test files (auth, error envelope, WS validation, trading-mode, widget states).

**LIVE safety preserved:** `live_trading` reflect-only (no toggle); broker credentials/tokens never reach the app; no direct DB/broker access; no authoritative math in Dart.

**Status (§54):** Phase 18 is now **TESTED**. On 2026-08-21 the final E2E blocker was remediated: PostgreSQL 17 was provisioned locally (`C:\src\pgdata`, role `alpha_algo_app`, DB `alpha_algo`), the pre-TimescaleDB migrations were applied (auth/RBAC tables), a dedicated test user was seeded (argon2id hash, `system:read` + `trading:view`), and the API was started against the real database. Verified with real runtime evidence: `POST /auth/login` (200), `POST /auth/refresh` (200), `GET /auth/me` (200 with expected permissions), negative RBAC (401 no-token, 401 bad-token, 403 insufficient-permission, 401 wrong-password), and authenticated WebSocket (valid token → `HEALTH_UPDATE` `live_trading: disabled`). A real-device integration test (`apps/mobile/integration_test/app_e2e_test.dart`) ran on the Pixel 6 (adb-reverse port 8000): login → dashboard → PAPER badge → WS `status: connected` → Database `ok` → logout → re-login, **all passed**. `flutter analyze` 0 issues; `flutter test` 23/23; `flutter build apk --debug` green; backend regression **1611 passed**. Secret/fake-data scan clean. The prior WS "403" was root-caused as standard ASGI behavior (the route's `close(1008)` before `accept()` is surfaced by uvicorn as HTTP 403) - not a defect; the authenticated WS path is verified working. Remaining documented limitations (not Phase-18 blockers): full `alembic upgrade head` is blocked by the TimescaleDB-required migration (extension not installed; the auth/RBAC schema is migrated and verified), and iOS is deferred (no macOS/Xcode). LIVE remains **fail-closed**. Phase 19 (Desktop) is **not** started.

---

## 0s. Phase 19 - Desktop Platform (TESTED — Windows build + runtime verified)

Phase 19 was **implemented and TESTED** on 2026-08-21 (see `P19-session-report.md` and `P19-review.md`). The **Flutter desktop trading terminal** (`apps/desktop/`) — a presentation/control layer consuming the backend only through authenticated REST + WebSocket — is written. It reuses the Phase 18 mobile client layer (auth/REST/WS/models/repositories) as a documented mirror, and adds a desktop-native shell: persistent permission-gated sidebar (13 destinations), top status bar (PAPER/LIVE badge + connection indicator + account + sign-out), multi-column dashboard, honest `Unavailable` panels for all trading workspaces, and keyboard shortcuts (`Ctrl+1..4`, `Ctrl+K`).

**Backend-first honesty:** the backend exposes only auth + system + WebSocket (no trading-data endpoints), so every trading workspace renders `Unavailable` — never fabricated zeros. LIVE remains **fail-closed** (`LIVE_TRADING_ENABLED=false`, `GLOBAL_TRADING_HALT=true`); the mode badge is reflect-only and there is no local LIVE switch.

**Verification (real evidence):** `flutter analyze` → **0 issues**; `flutter test` → **29/29 passed**; `flutter build windows` → ✅ `build\windows\x64\runner\Release\alpha_algo_desktop.exe`; Windows runtime E2E (`flutter test integration_test/app_e2e_test.dart -d windows` against the real PostgreSQL-backed API) → **All tests passed!** (login → dashboard → authenticated WS `status: connected, live_trading: disabled` → honest Unavailable → logout → re-login; PAPER mode; LIVE blocked). Backend regression → **1611 passed**. Security scan → 0 secrets / 0 fake values / 0 direct DB/broker access. One real build defect found and fixed: the VS "Desktop development with C++" workload omitted ATL headers (`atlstr.h`) required by `flutter_secure_storage_windows`; installed `Microsoft.VisualStudio.Component.VC.ATL` and rebuilt green. macOS is deferred (no Xcode). Verification ran on a clean-path copy `C:\src\desktop_verify` (repo path apostrophe breaks Flutter test tooling, as in Phase 18).

**Status (§52):** Phase 19 is **TESTED** — analyze, tests, Windows build, real runtime, security review, and backend regression are all green with evidence. macOS is deferred. Phase 20 (Observability) is **not** started.

---

## 0t. Phase 20 - Observability Platform (TESTED — provider-neutral abstraction + API instrumentation + regression)

Phase 20 was **implemented and TESTED** on 2026-08-21 (see `P20-session-report.md`, `P20-review.md`, and `docs/observability.md`). A provider-neutral observability abstraction (`packages/observability/alpha_algo_observability/`) was added: metrics (`Counter`/`Gauge`/`Histogram` with bounded labels), structured logging with recursive secret `redact()`, tracing (contextvar spans + W3C `traceparent`), error normalization (`FailureClass`), health registry (liveness/readiness/dependency/trading-safety), alerting (deterministic dedup + auditable lifecycle), and append-only audit (chained hashes). No external telemetry backend is required; a no-op path exists for tests/offline (§40–§42).

The FastAPI surface is instrumented: request metrics + latency histograms + trace/request/correlation-id propagation in the middleware, auth/permission/rate-limit counters, active HTTP/WS gauges, trading-safety health registration, and a new read-only `GET /api/v1/system/observability` endpoint (gated by `system:read`) returning metrics + health (incl. trading safety) + alerts + recent traces. Core services already carry Phase 8–16 domain metrics (`OmsMetrics`, `ExecutionMetrics`, `PositionMetrics`, `PortfolioMetrics`, `PnlMetrics`, `ReconciliationMetrics`, `PaperMetrics`) matching the §14–§26 catalog; Phase 20 documents that catalog rather than duplicating it.

**Verification (real evidence):** observability unit tests (25) + API instrumentation tests (6) + failure-isolation tests (6) → **37 new tests**; full backend regression → **1642 passed** (1611 baseline, zero regressions). LIVE remains **fail-closed** (`LIVE_TRADING_ENABLED=false`, `GLOBAL_TRADING_HALT=true`); observability is observation-only and can never enable LIVE or modify trading state.

**Status (§67):** Phase 20 is **TESTED** — logging/metrics/tracing/health/alerting/audit implemented+tested, failure isolation verified, security review completed, regression green. Phase 21 is **not** started.

---

## 0u. Phase 21 - Event Architecture (TESTED — unified envelope + in-process bus + regression)

Phase 21 was **implemented and TESTED** on 2026-08-21 (see `P21-session-report.md`, `P21-review.md`, and `docs/event-architecture.md`). A unified **internal** domain-event architecture was added: a validated `DomainEvent` envelope (`packages/contracts/alpha_algo_contracts/events.py` — tz-aware, safe event_type, recursive `validate_no_secrets`, causation/correlation/trace + `domain_ids`) plus an in-process, thread-safe `EventBus` (`packages/events/alpha_algo_event_bus/` — pub/sub, `*` wildcard, deterministic FIFO, handler-failure isolation, `NoopEventBus`). Both are **additive**; no existing engine was modified (per the "do not modify completed phases" rule). Broker/streaming eventing is **deferred** (no scale justification; Phase 10 broker-event normalization + dedup already covers provider ingestion).

**Verification (real evidence):** event-architecture unit tests (18) + pipeline event-flow integration tests (3) → **21 new tests**; full backend regression → **1669 passed** (1648 baseline, zero regressions). The integration test drives the full pipeline (signal → risk → orchestration → OMS → execution → position → P&L → reconciliation) as a causally-linked, correlated event stream and verifies ordering, causation, correlation, and domain-id reconstruction. LIVE remains **fail-closed**; events are append-only facts and can never enable LIVE or modify trading state.

**Status:** Phase 21 is **TESTED** — envelope + bus implemented and tested, correlation/causation verified, secrets rejected, regression green.

---

## 0v. Phase 22 - CI/CD (IMPLEMENTED — VERIFICATION DEFERRED; all local gates green)

Phase 22 was **implemented** on 2026-08-21 (see `P22-session-report.md`, `P22-review.md`, `docs/ci-cd.md`). A 7-job GitHub Actions workflow (`.github/workflows/ci.yml`: `lint`, `test`, `security`, `migration-check`, `web-build`, `mobile-build`, `desktop-build`) was added with caching, plus `requirements-dev.txt`, a portable `scripts/security_scan.py` (secrets/broker-placeholder/LIVE-fail-closed), an offline `scripts/check_migrations.py` (single head/base/linear/no-orphans + offline SQL), and `scripts/run_ci.py` (local runner). `ruff` was introduced (`F`,`E9`) and **115 real pyflakes findings were fixed** (unused imports/redefinitions/unused-vars + a Phase-20 `AlertIdentity` `__all__` bug), with the full regression confirming zero behavior change. Web gained a `typecheck` (`tsc --noEmit`) script.

**Verification (local executable evidence):** backend regression **1669 passed**; `ruff` 0; migration check 15 revisions single-head/single-base + offline SQL OK; security scan clean; web typecheck + 29 tests + production build green; mobile `flutter analyze` 0 + 23 tests; desktop `flutter analyze` 0 + 29 tests; `ci.yml` YAML parses (7 jobs). **Deferred (cannot execute in this environment):** remote GitHub Actions execution and Docker-based jobs (no runner/Docker locally); `flutter build apk`/`flutter build windows` re-run (cited from Phases 18/19, code unchanged); iOS/macOS. Per spec §19, final status is **IMPLEMENTED — VERIFICATION DEFERRED** (not upgraded on YAML inspection alone). LIVE remains **fail-closed**; no job enables LIVE or deploys credentials.

**Status:** Phase 22 is **IMPLEMENTED — VERIFICATION DEFERRED**. Phase 23 is **not** started.

---

## 0w. Phase 23 - Full System Verification (TESTED — kill switch + verified safety controls)

Phase 23 was **implemented and TESTED** on 2026-08-21 (see `P23-session-report.md`, `P23-review.md`, `docs/system-verification.md`). "Full system verification" closed the last LIVE-readiness safety-control gap and verified the full fail-closed chain. The single implementation gap was the **kill switch**: added `GlobalHaltController` (`services/risk_engine/alpha_algo_risk_engine/gates.py`) — a fail-closed, immutable, thread-safe controller with `activate(reason, actor)` / `deactivate(reason, actor)` / `is_halted()` (starts **halted**; deactivate requires explicit reason + actor). Enforcement is unchanged and already fail-closed (`GlobalHaltRule` first in the engine rejects everything while halted; `LiveModeRule` blocks LIVE unless explicitly enabled). The 17 LIVE safety gates (`LiveSafetyGateEvaluator`) and the circuit breaker (`CircuitBreaker`/`CircuitBreakerRegistry`, already wired into the risk service) were **verified** (their §5.14 statuses were stale PARTIAL/MISSING, not code gaps).

**Verification (real evidence):** 10 kill-switch unit tests + 4 full-system integration tests (halts instantly, lifts cleanly, gates-green-does-not-enable-LIVE, breaker trips+resets, single authoritative halt source) → **14 new tests**; full backend regression → **1683 passed** (1669 baseline, zero regressions); `ruff` clean; security scan clean. LIVE remains **fail-closed** (`LIVE_TRADING_ENABLED=false`, `GLOBAL_TRADING_HALT=true`); gates-green + halt-lifted still cannot enable LIVE. Phase 24 is **not** started.

**Status:** Phase 23 is **TESTED**. Phase 24 is **not** started.

---

## 1. Current Product Maturity Level

**LEVEL 1 - FOUNDATION.**

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

### 5.1 Foundation (Phase 1 - COMPLETE)

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
| Secure errors | PRODUCTION | 1 | `errors.py` | - | JSON envelope + request-id on 401/403/404/422/429/500 |
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


### 5.3 Market Data (Phase 3 - COMPLETE)

| Capability | Current Status | Target Phase | Owner/Module | Dependencies | Verification Requirement |
|---|---|---|---|---|---|
| Provider interface | TESTED | 3 | `services/market_data/.../provider.py` | async `MarketDataProvider` Protocol | fake provider satisfies contract (unit tests) |
| Provider authentication | TESTED | 3 | `provider.py` + `fake_provider.py` | `ProviderHealth.authenticated` + auth-fail error | auth failure raises + health reports auth (unit tests) |
| Subscription management | TESTED | 3 | `provider.py` + `service.py` | subscribe/unsubscribe routing | symbols routed via `set_event_handler` (integration test) |
| Reconnect | TESTED | 3 | `connection.py` (`Reconnector`) | bounded exponential backoff + connect timeout | auto-reconnect within bounded attempts (unit tests) |
| Heartbeat | TESTED | 3 | `connection.py` (`HeartbeatMonitor` + watchdog) | heartbeat monitor + `run_monitor` | dead connection detected + reconnected (unit tests) |
| Timeout | TESTED | 3 | `connection.py` + `engine.py` (staleness max_age) | connect-timeout + staleness | timeout aborts; staleness enforced (unit tests) |
| Sequence handling | TESTED | 3 | `safety.py` (bounded `DuplicateTickDetector`) + `ConnectionState` | bounded LRU dedup + state transitions | duplicate `(broker, sequence)` deduped; state machine enforced |
| Duplicate detection | PRODUCTION | 3 | `market_data/safety.py` | - | same `(broker, sequence)` deduped (now bounded) |
| Stale-data detection | PRODUCTION | 3 | `market_data/safety.py` | - | future/stale/fresh classified |
| Backpressure | TESTED | 3 | `backpressure.py` (`BoundedQueue`) + `engine.py` | bounded queue + drop policy | overflow handled without OOM; drops counted+logged |
| Normalized tick | PRODUCTION | 3 | `contracts/market_data.py` (MarketTick) | - | tz, ltp>0, extra-field reject |
| Normalized candle | PRODUCTION | 3 | `contracts/market_data.py` (MarketCandle) | - | OHLC range/timeframe/tz validation |
| Historical ingestion | TESTED | 3 | `historical.py` (`HistoricalDataClient`) | page-based cursor pagination + retry | candles/ticks pageable + bounded (unit tests) |

> Phase 3 capabilities are marked **TESTED** (implemented + unit-tested + integration-tested). Live provider connectivity and real end-to-end vendor-feed verification are deferred (no Docker/PostgreSQL/providers in this environment) and must be re-verified at VERIFIED/PRODUCTION time. The deterministic helpers/contracts (duplicate/stale detection, normalized tick/candle) retain their Phase-0 **PRODUCTION** status as pure deterministic components.

### 5.4 Strategy Runtime (Phase 4 - COMPLETE)

| Capability | Current Status | Target Phase | Owner/Module | Dependencies | Verification Requirement |
|---|---|---|---|---|---|
| Strategy registry | TESTED | 4 | `services/strategy_engine/.../registry.py` | `StrategyDefinition` + `StrategyIdentity` | register/unregister/discover/load/validate/enable/disable/status; dup prevention (id + code) |
| Lifecycle manager | TESTED | 4 | `services/strategy_engine/.../instance.py` + `state.py` | `RunStateMachine` (7 states) | `initialize→on_start→...→on_stop` ordering; illegal transitions rejected |
| Scheduler/event dispatcher | TESTED | 4 | `services/strategy_engine/.../dispatcher.py` | routing by instrument/timeframe/event-type/enabled/state | events routed to relevant RUNNING instances only |
| Startup/shutdown | TESTED | 4 | `services/strategy_engine/.../runtime.py` | `StrategyRuntime.start/stop/shutdown` | hooks fire on start/stop; shutdown non-blocking |
| Tick callback | TESTED | 4 | `instance.py` (`on_tick`) + `runtime.py` | `MarketTick` (Phase 3) | `on_tick` receives MarketTick → validated StrategySignal |
| Candle callback | TESTED | 4 | `instance.py` (`on_candle`) + `runtime.py` | `MarketCandle` (Phase 3) | `on_candle` receives MarketCandle → validated StrategySignal |
| Order-update callback | TESTED | 4 | `instance.py` + `runtime.on_order_update` | `OrderUpdate` stream | receives state transitions → signals |
| Position-update callback | TESTED | 4 | `instance.py` + `runtime.on_position_update` | `PositionUpdate` stream | receives quantity changes → signals |
| Configuration management | TESTED | 4 | `config.py` | `validate_config` + `compute_config_hash` | config validated, deep-frozen, hashed, injected |
| Version management | PRODUCTION | 4 | `contracts/signals.py` (StrategyVersion) | - | version/config_hash/code_hash validation |
| Runtime isolation | PRODUCTION | 4 | `strategies/.../lifecycle.py` | - | strategy cannot reach broker/network/live |

> Phase 4 capabilities are marked **TESTED** (implemented + unit-tested + integration-tested + adversarial-review-fixed). Live execution, OMS/Risk/Execution wiring, and signal persistence are deferred to Phase 5+ (no downstream consumers are registered; the runtime ends at a validated, traceable `StrategySignal`). Trading mode is fail-closed: only BACKTEST/PAPER are allowed; LIVE raises `TradingModeError`. The contract-level components (version management, runtime isolation) retain their Phase-0 **PRODUCTION** status.

### 5.5 Signal Engine (Phase 5 - COMPLETE)

| Capability | Current Status | Target Phase | Owner/Module | Dependencies | Verification Requirement |
|---|---|---|---|---|---|
| Strategy→StrategySignal | PRODUCTION | 5 | `lifecycle.py` (emit_signal) | - | identity match validation |
| Signal validation (contract) | PRODUCTION | 5 | `contracts/signals.py` (StrategySignal) | - | confidence 0-1, reason 1-500, tz |
| Traceability fields (9) | PRODUCTION | 5 | `contracts/signals.py` | - | `audit_key` reconstructs full lineage |
| Ingestion validation (boundary re-validation) | TESTED | 5 | `validation.py` | `StrategyDirectory` | 11 rejections with stable reason codes |
| Deterministic signal identity | TESTED | 5 | `identity.py` | SHA-256 | identity_key over strategy|version|config|instrument|action|event_ts |
| Content hashing (conflict detection) | TESTED | 5 | `identity.py` | SHA-256 | content_hash over confidence|reason|event_ts|metadata |
| Idempotency | TESTED | 5 | `idempotency.py` + `repository.py` | LRU + DB unique | duplicate/conflict; no silent overwrite; retry-safe |
| Signal state machine | TESTED | 5 | `state.py` + `service.py` | - | 8-state lifecycle enforced; illegal transitions rejected |
| Signal persistence | TESTED | 5 | `repository.py` → `signals` | SQLAlchemy + migration | transactional COMMIT; rollback+re-raise |
| Trading-mode gate | TESTED | 5 | `validation.py` + `service.py` | `TradingModeError` | BACKTEST/PAPER accepted; LIVE rejected |
| Phase-6 consumer fan-out | TESTED | 5 | `service.py` (`add_consumer` + `SignalRecord`) | - | consumers fire only on durable PERSISTED |

> Phase 5 capabilities are marked **TESTED** (implemented + unit-tested + integration-tested + 4-axis-review-fixed). Live PostgreSQL connectivity and end-to-end DB-backed verification are deferred (no Docker/PostgreSQL in this environment). Risk/OMS/Execution/Broker/LIVE are deferred to Phase 6+. The contract-level components (Strategy→StrategySignal, signal validation, traceability fields) retain their Phase-0 **PRODUCTION** status.

### 5.6 Live Risk (Phase 6 - COMPLETE)

| Capability | Current Status | Target Phase | Owner/Module | Dependencies | Verification Requirement |
|---|---|---|---|---|---|
| Immutable risk snapshot | TESTED | 6 | `snapshot.py` (RiskSnapshot + nested) | authoritative runtime state | single coherent read; freshness + staleness |
| Fail-closed state provider | TESTED | 6 | `state.py` (RiskStateProvider + Unavailable) | - | unavailable → REJECT |
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
| Fail-closed defaults | PRODUCTION | 6 | `engine.py` + `gates.py` | - | defaults fail-closed (17 gates False) |

> Phase 6 capabilities are marked **TESTED** (implemented + unit-tested + integration-tested + 4-axis-review-fixed). Live PostgreSQL connectivity and a real runtime state provider (positions/P&L/portfolio are Phase 11+) remain deferred; the default provider fails closed. The engine ends at `RiskDecision → APPROVED/REJECTED`; OMS/execution/LIVE are Phase 7+. The contract-level rule classes (14 core rules + fail-closed defaults) retain their Phase-0 **PRODUCTION** status.

### 5.7 Trading Orchestrator (Phase 7 - COMPLETE)

| Capability | Current Status | Target Phase | Owner/Module | Dependencies | Verification Requirement |
|---|---|---|---|---|---|
| Orchestration state machine | TESTED | 7 | `services/trading_engine/.../state.py` | - | deterministic transitions; terminal states locked |
| Orchestration identity | TESTED | 7 | `services/trading_engine/.../identity.py` | signal identity | SHA-256 over signal+run+qty+account+order-type+mode |
| Order-intent resolution | TESTED | 7 | `services/trading_engine/.../intent.py` | resolver protocol | fail-closed default; never invents quantity |
| Action validation | TESTED | 7 | `services/trading_engine/.../service.py` | SignalAction | BUY/SELL/EXIT; HOLD/unknown → no intent |
| Risk consumption | TESTED | 7 | `service.py` → RiskService | Phase 6 | evaluate before OMS; rejected stops flow |
| Approval re-validation | TESTED | 7 | `service.py` → `approval_is_usable` | Phase 6 binding | expiry + binding; PRIOR_APPROVAL_INVALID preserved |
| Idempotency | TESTED | 7 | `service.py` + `repository.py` | unique `orchestration_id` | replay → DUPLICATE; no second intent |
| Transaction boundary | TESTED | 7 | `repository.py` → `trading_intents` | SQLAlchemy + migration | COMMIT = truth; no false success |
| Concurrency control | TESTED | 7 | `service.py` (RLock) | - | narrow critical section; no global lock |
| OMS handoff port | TESTED | 7 | `oms_port.py` (OmsPort/NoOpOmsPort) | - | explicit notification boundary; never a broker |
| Trading-mode gate | TESTED | 7 | `service.py` | - | BACKTEST/PAPER allowed; LIVE/unknown blocked |
| Observability | TESTED | 7 | `metrics.py` (OrchestrationMetrics) | - | received/rejected/risk/dup/persist/handoff/latency |
| End-to-end orchestrator | TESTED | 7 | `services/trading_engine/` | Phases 5 + 6 | Signal → Risk → Orchestrator → OMS-ready Intent |

> Phase 7 capabilities are marked **TESTED** (implemented + unit-tested + integration-tested + 4-axis-review-fixed). Live PostgreSQL connectivity and the downstream OMS (Phase 8) are deferred. The pipeline ends at an OMS-ready `TradingIntent`; no broker/live execution is introduced. LIVE remains **fail-closed**.

### 5.8 OMS (Phase 8)

| Capability | Current Status | Target Phase | Owner/Module | Dependencies | Verification Requirement |
|---|---|---|---|---|---|
| Order lifecycle state machine (11 states) | PRODUCTION | 8 | `execution_engine/lifecycle.py` | - | transitions enforced |
| Intent (INTENT_CREATED) | PRODUCTION | 8 | `lifecycle.py` + `submission.py` | StrategySignal | initial state + approval id |
| Order creation | PRODUCTION | 8 | `lifecycle.py` | - | legal transition |
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

### 5.9 Execution (Phase 9 - COMPLETE)

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

### 5.10 Broker Integration (Phase 10 - COMPLETE)

| Capability | Current Status | Target Phase | Owner/Module | Dependencies | Verification Requirement |
|---|---|---|---|---|---|
| BrokerAdapter Protocol + concrete adapters | TESTED | 10 | `services/broker_adapters/` (Zerodha/Upstox/Angel One) | `alpha_algo_broker_integration` | 3 adapters pass the universal contract suite |
| Capability-gated providers | TESTED | 10 | `contracts.py` (BrokerCapabilities) | capability descriptor | unsupported op → `UNSUPPORTED` |
| No scattered broker branching | PRODUCTION | 10 | `broker_adapters/` | - | core engine has no `broker ==` branching |
| Authentication/session isolation | TESTED | 10 | per-adapter `authenticate`/`validate_session` | credential resolver | creds never leave the adapter boundary |
| Connection/reconnect lifecycle | TESTED | 10 | `connection.py` (ConnectionStateMachine) | bounded backoff | DISCONNECTED→...→RECONNECTING; no order dup |
| Order mapping (type/product/status) | TESTED | 10 | per-broker `mapping.py` | universal enums | explicit maps; no silent downgrade |
| Instrument/symbol mapping | TESTED | 10 | `mapping.py` (InstrumentMapping) | broker token/key | missing/ambiguous mapping → REJECT |
| Response/error normalization | TESTED | 10 | per-broker `mapping.map_error` | BrokerError model | provider payload → universal, tested |
| Event stream normalization + dedup | TESTED | 10 | `events.py` (EventDeduplicator) | stable event identity | duplicate drop; conflict on reuse |
| Rate limiting | TESTED | 10 | `ratelimit.py` (per-scope token bucket) | provider limits | bounded throttling |
| Secure credential handling | TESTED | 10 | `BrokerCredentialsRef` + resolver | secret refs | no hardcoded/committed/logged secrets |
| LIVE gating | TESTED | 10 | `base.py` (guards) | `LIVE_TRADING_ENABLED=false` | LIVE request → blocked even with creds |

> Phase 10 capabilities are marked **TESTED** (implemented + unit/contract-tested + 4-axis-review-fixed). Live broker connectivity/credentials and real sandbox verification are deferred (no real providers in this environment); adapters are mocked-tested only. No adapter is marked PRODUCTION - that requires real provider/sandbox + controlled-live validation (Phase 24+).

### 5.11 Position / Portfolio / P&L / Reconciliation (Phases 11-14)

| Capability | Current Status | Target Phase | Owner/Module | Dependencies | Verification Requirement |
|---|---|---|---|---|---|
| Position engine (live, authoritative) | TESTED | 11 | `services/position_engine/` (PositionEngine/PositionRepository); `positions` + `position_events` (schema) | normalized fill events; P&L engine; DB runtime | live position from events + persisted + idempotent |
| Portfolio engine | TESTED | 12 | `services/portfolio_engine/` (PortfolioEngine/PortfolioRepository); `portfolio_snapshots` (schema) | position engine + funds snapshots + reference prices | value/cash/exposure/allocation persisted + idempotent + deterministic |
| P&L engine (live) | TESTED | 13 | `services/pnl_engine/` (PnlEngine/PnlRepository); `pnl_events` + `pnl_snapshots` (schema) | position/fill records; normalized reference prices; cost data | realized+unrealized+net at trade/strategy/account/daily; weighted-average cost; idempotent |
| Reconciliation | TESTED | 14 | `services/reconciliation_engine/` (ReconciliationEngine/ReconciliationRepository); `reconciliation_runs` + `reconciliation_discrepancies` (schema) | orders/executions/positions/funds; Phase 10 normalized observations | mismatch detection + persisted evidence + no silent overwrite + controlled recovery |

### 5.12 Simulation (Phases 15-16)

| Capability | Current Status | Target Phase | Owner/Module | Dependencies | Verification Requirement |
|---|---|---|---|---|---|
| Paper trading (full path) | TESTED | 15 | `services/paper_trading/alpha_algo_paper_runtime/` (account/funds/run/costs/routing/service/repository) + `paper_runs`/`paper_accounts`/`paper_funds` (schema) | paper broker foundation; Phase 14 reconciliation; position engine | BUY→HOLD→SELL→CLOSE lifecycle + funds + reconciliation; LIVE fail-closed |
| Backtesting (deterministic) | PRODUCTION | 16 | `backtesting/` (P7-001 foundation, P7-002 engine, P7-004 reports, P7-003 walk-forward) | contracts; Decimal foundation | identical inputs → identical results; no-live-access |
| Backtesting - advanced metrics (CAGR, VaR/CVaR, Alpha/Beta, MFE/MAE) | TESTED | 16 | `backtesting/alpha_algo_backtest_analytics/` | engine equity/return series | defined formulas; edge cases; determinism |
| Backtesting - data quality | TESTED | 16 | `backtesting/alpha_algo_backtest_quality/` | contracts | valid/quarantined/rejected classification; no silent repair |
| Backtesting - optimization + Monte Carlo | TESTED | 16 | `backtesting/alpha_algo_backtest_optimize/` | engine; walk-forward | deterministic grid; train/test separation; seeded reproducibility |
| Backtesting - persistence/identity/caching | TESTED | 16 | `backtesting/alpha_algo_backtest_persistence/` | engine identity | optional outer layer; duplicate/conflict; reproducible run id |
| Backtesting - multi-symbol portfolio + capital allocation | TESTED | 16 | `backtesting/alpha_algo_backtest_portfolio/` | engine fill/cost/FIFO | shared capital; reserved-cash floor; budget caps; long-only |
| Backtesting - latency model | TESTED | 16 | `backtesting/alpha_algo_backtest_latency/` | engine intents | deterministic delay; simulation-time controlled |

### 5.13 Platform (Phases 17-19)

| Capability | Current Status | Target Phase | Owner/Module | Dependencies | Verification Requirement |
|---|---|---|---|---|---|
| Web - auth | TESTED | 17 | `apps/web/` (login/refresh/me/RBAC) | backend auth | login/refresh/me/logout/expiry/401/403 vs real backend contract |
| Web - dashboard | PARTIAL | 17 | `apps/web/` (`(app)/dashboard`) | API + WS | real health/readiness/mode/WS rendered; trading metrics Unavailable (no backend endpoint) |
| Web - watchlist | PARTIAL | 17 | `apps/web/` (`(app)/watchlist`) | market-data API | shell + honest Unavailable (no backend endpoint) |
| Web - market data & charts | PARTIAL | 17 | `apps/web/` (`(app)/markets`, `charts`) | market-data runtime + charts | shell + honest Unavailable (no backend endpoint) |
| Web - positions/orders/portfolio/P&L | PARTIAL | 17 | `apps/web/` (`(app)/positions`...`pnl`) | engines | shell + honest Unavailable (no backend endpoint) |
| Web - Tier 2 | PARTIAL | 17 | `apps/web/` (`(app)/risk`, `brokers`, `alerts`, `reconciliations`) | risk/broker/alerts APIs | shell + honest Unavailable (no backend endpoint) |
| Web - Tier 3 | PARTIAL | 17 | `apps/web/` (settings) | backtesting/audit/admin | session/permissions rendered; backtesting/admin Unavailable |
| Mobile - Tier 1 (auth/shell/dashboard) | ACTIVE_DEVELOPMENT | 18 | `apps/mobile/` (auth/shell/home/design) | backend auth + system + WS | analyze 0 issues + 23/23 tests + debug/release APK + device launch GREEN; E2E auth/WS TESTED (real PostgreSQL + device integration test) |
| Mobile - Tier 2 (risk/broker/alerts) | ACTIVE_DEVELOPMENT | 18 | `apps/mobile/` (features/more + UnavailableView) | Tier 1 + risk/alert APIs | honest Unavailable states; backend endpoints missing |
| Mobile - Tier 3 (backtesting/audit/admin) | MISSING | 18 | (no screen yet) | backtesting API | no backtesting/audit/admin screen yet |
| Desktop - Windows | MISSING | 19 | (no `apps/desktop`) | shared Flutter core | Windows build |
| Desktop - macOS | MISSING | 19 | (no `apps/desktop`) | shared Flutter core | macOS build |

### 5.14 Operations & Live Readiness (Phases 20-24)

| Capability | Current Status | Target Phase | Owner/Module | Dependencies | Verification Requirement |
|---|---|---|---|---|---|
| Observability - metrics | PARTIAL | 20 | `infra/prometheus/`, `docker-compose.yml` | app instrumentation | Prometheus scrapes app targets |
| Observability - structured logs | PARTIAL | 20 | `middleware.py` (request-id) | structured logging | structured log lines |
| Observability - tracing | MISSING | 20 | - | OTel SDK | spans across engines |
| Observability - alerts | MISSING | 20 | `services/notification_engine/` (`.gitkeep`) | alert engine | alerts fire on thresholds |
| Event architecture - internal | TESTED | 21 | `contracts/events.py`, `alpha_algo_event_bus/` | unified `DomainEvent` + bus | envelope + bus tested; pipeline flow reconstructable |
| Event architecture - broker | MISSING | 21 | - | scale justification | broker only if justified (deferred) |
| CI/CD - format/lint/type | MISSING | 22 | `.github/workflows/ci.yml` | ruff/black/mypy | CI runs checks |
| CI/CD - test/security/build/migration | PARTIAL | 22 | `.github/workflows/ci.yml` | test matrix + Docker | CI full pipeline |
| Live release - safety gates (24+) | TESTED | 23 | `gates.py` (`LiveSafetyGateEvaluator` + 17 gates) | all engines + controls | all gates verified (evaluator + tests) |
| Live release - SHADOW→FULL | MISSING | 24 | - | Phase 23 + ops | controlled progression |
| Kill switch | TESTED | 23 | `gates.py` (`GlobalHaltController`) | live orchestration | halts live instantly (activate/is_halted) |
| Circuit breaker (actual) | TESTED | 23 | `circuit_breaker.py` (`CircuitBreaker`/`Registry`, wired into risk service) | live wiring | trips + resets |

---

## 6. Summary Counts

- **Total capabilities tracked:** ~168 (Foundation 12 · Database 11 · Market Data 13 · Strategy 11 · Signal 11 · Risk 28 · Orchestrator 13 · OMS 15 · Execution 9 · Broker 12 · Position/Portfolio/P&L/Reconciliation 4 · Simulation 8 · Platform 12 · Operations/Live 9).
- **PRODUCTION today:** deterministic backtesting; migration scripts; secure-error envelope; core market-data contracts + dedup/staleness helpers; signal/strategy contracts + versioning + runtime isolation; 20 risk rule classes (14 core + 6 configurable) + fail-closed defaults; 11-state order lifecycle + event engine.
- **MISSING today (highest-impact):** desktop, tracing/alerts/CI, and all LIVE release paths. (Phase 1 auth/RBAC/CORS/rate-limit + ASGI/psycopg, Phase 2 DB runtime, Phase 3 market-data runtime, Phase 4 strategy runtime, Phase 5 signal engine, Phase 6 live risk engine, Phase 7 trading orchestrator, Phase 8 OMS, Phase 9 execution engine, Phase 10 broker adapters, Phase 11 position engine, Phase 12 portfolio engine, Phase 13 P&L engine, Phase 14 reconciliation engine, Phase 15 paper trading runtime, and Phase 16 backtesting expansion are now **TESTED**. Phase 17 web terminal: **auth TESTED** + app shell/system-health/WS **PARTIAL** - trading-data screens honest Unavailable pending backend endpoints. Phase 18 mobile: **TESTED** (analyze 0 issues + 23/23 tests + debug/release APK + real-device launch + real PostgreSQL auth + device E2E integration test: login → dashboard → WS HEALTH_UPDATE → logout → re-login); auth/shell/dashboard + honest Unavailable states.)

---

*End of IMPLEMENTATION_STATUS.md - Phase 0 baseline. Read-only; source of truth remains the repository code. Subsequent phases update this document after each change (per §33 and §43).*
