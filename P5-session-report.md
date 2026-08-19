# P5 Session Report — Phase 5: Signal Engine

**TaskId:** alpha-algo-phase5
**Date:** 2026-08-19
**Repository:** `projects/alpha-algo-trading-system/`
**Status:** COMPLETE — capabilities **TESTED** (never PRODUCTION; LIVE blocked by design)

---

## 1. Objective

Build the dedicated, persistent, deterministic, auditable **Signal Engine** — the
boundary between the Phase-4 Strategy Runtime and the future Phase-6 Risk Engine.
It must accept only validated `StrategySignal` outputs, re-validate them at the
boundary (so no arbitrary caller can bypass Phase-4 validation), enforce
deterministic identity + content hashing + idempotency, enforce a signal state
machine, persist transactionally, allow only BACKTEST/PAPER (LIVE fail-closed),
and expose a clean Phase-6 routing interface. It must **not** implement
Risk/OMS/Execution/Broker/LIVE.

## 2. Delivered scope

New package `services/signal_engine/alpha_algo_signal_engine/` (11 modules):

| Module | Responsibility |
|---|---|
| `errors.py` | `SignalRejectedError`, `TradingModeError` |
| `state.py` | `SignalState` (8 states) + `SignalStateMachine` (transition-safe, fail-closed) |
| `identity.py` | deterministic `identity_key` + `content_hash` + `event_timestamp`/`code_hash`/`run_id` extraction |
| `directory.py` | `StrategyDirectory` protocol + `StrategyRecord` |
| `validation.py` | `SignalIngestionValidator` (boundary re-validation + mode gate) |
| `idempotency.py` | `SignalIdempotency` (in-memory LRU; `check`/`record` split) |
| `repository.py` | `SignalRepository` (transactional persist + `to_orm_signal`) |
| `service.py` | `SignalEngine` (composition root) + `SignalRecord`/`SignalIngestResult` |
| `metrics.py` | `SignalMetrics` (counters + latency + per-strategy/instrument) |
| `boundary.py` | `build_signal_engine` / `connect_strategy_runtime` (Phase 4 → 5 wiring) |
| `__init__.py` | public exports |

Extended `Signal` ORM model (`packages/shared/.../db/models/trading.py`) with 10
new columns and a migration (`migrations/versions/20260819_signal_engine.py`).

## 3. Key design decisions

- **Identity key** = SHA-256 over `strategy_id | strategy_version | config_hash | instrument_id | action | event_timestamp` — **not** derived from the random `signal_id`.
- **Content hash** = SHA-256 over `confidence | reason | event_timestamp | metadata` (canonical JSON) — anchored to the authoritative event timestamp so a replay with a fresh `signal.timestamp` is still a DUPLICATE, not a false CONFLICT.
- **Event timestamp** read from `metadata["event_timestamp"]` (Phase-4 enrichment) with fallback to `signal.timestamp`.
- **Idempotency `check`/`record` split**: `check` is a pure lookup; `record` runs only after a durable INSERTED/DUPLICATE outcome. A retry after a DB failure re-attempts persistence instead of being swallowed as a false duplicate.
- **Persistence is transactional**: COMMIT is the sole boundary of truth; any exception rolls back + re-raises (no false SUCCESS). Duplicate vs conflict are distinguished by content_hash; neither overwrites.
- **State machine** now driven inside `ingest`: RECEIVED → VALIDATED → ACCEPTED → PERSISTED (terminal REJECTED / DUPLICATE / CONFLICT / EXPIRED).
- **Trading mode** passed as `ingest(signal, trading_mode="PAPER")`; LIVE raises `TradingModeError`; allow-set exactly `{BACKTEST, PAPER}`.

## 4. Contract changes (documented)

- `Signal` ORM: added `signal_id`, `identity_key`, `content_hash`, `strategy_id`, `strategy_version`, `config_hash`, `code_hash`, `run_id`, `state`, `processed_at`; unique constraints `uq_signals_signal_id` and `uq_signals_identity_key`; `strategy_run_id`/`strategy_version_id` made nullable with FK `ondelete=SET NULL`.
- Migration `20260819_signal_engine` revises `20260812_timescale_market_data`. New NOT NULL columns are safe because the `signals` table is empty at this point (Phase 5 is its first writer; LIVE fail-closed) — documented in the migration docstring.

## 5. Test evidence

- Phase 5 suite: 8 files, **68 tests** (identity, state, idempotency, ingestion, persistence, engine, integration, model).
- Full suite: **827 passed, 0 failed, 1 pre-existing StarletteDeprecationWarning** (baseline 759).
- Forbidden-import grep of `signal_engine` clean (no broker/order/execution/position/portfolio/risk/provider/credential/network).

## 6. Review (4 axes) + resolutions

| Axis | Verdict | Notable fix |
|---|---|---|
| Architecture | FAIL → resolved | wired `SignalStateMachine` into `ingest` |
| Live-safety | PASS | LIVE fail-closed confirmed |
| Persistence + idempotency | FAIL → resolved | content_hash anchored to `event_timestamp` (no false CONFLICT) |
| Signal-integrity | PASS | spoof-proof future-`event_timestamp` check added |

The "`identity.py` keys are `"***"` placeholders" finding (flagged by 3 reviewers)
was a **false positive**: ord-level byte check confirms the file contains
`"event_timestamp"`/`"strategy_code_hash"`/`"strategy_run_id"` (the `read`/`repr`
display redacts these strings). Full detail: `.cluster/alpha-algo-phase5/review.md`.

Two real defects fixed + two regression tests added:
- `test_content_hash_stable_across_replay_with_fresh_timestamp`
- `test_future_event_timestamp_rejected`

## 7. Documentation & registers updated

- `IMPLEMENTATION_STATUS.md` — §0e + §5.5 (11 capabilities → TESTED) + §6 counts.
- `trading_engine_register.md` — §8 Signal Engine → TESTED + Phase 5 delta.
- `platform_capability_matrix.md` — Phase 5 delta.
- `current_architecture_register.md` — Phase 5 delta.
- `dependency_register.md` — Phase 5 delta (no new dependencies).

## 8. Deferred (NOT done, by phase-scoping discipline)

- Risk engine (Phase 6), OMS (Phase 8), Execution (Phase 9), Broker adapters (Phase 10), Position/Portfolio/P&L/Reconciliation (Phases 11–14).
- Expiry is disabled by default (`max_signal_age=None`) — the EXPIRED path and event-time-based expiry are design-ready for Phase 6.
- Live PostgreSQL / end-to-end DB-backed verification (no Docker/PostgreSQL in this environment).

## 9. LIVE-blocked verification

LIVE is **fail-closed and blocked by design**: `SignalIngestionValidator` allows
only `{BACKTEST, PAPER}` and raises `TradingModeError` for any other mode
(case-normalized); Phase-4 `runtime.start()` independently blocks LIVE; the
signal engine imports no broker/provider/risk/execution code. Capabilities are
**TESTED** — never PRODUCTION. No broker credentials, orders, positions, or live
paths exist in this subsystem.
