# Phase 11 — Position Engine — Session Report

**Date:** 2026-08-20
**Scope:** `services/position_engine/alpha_algo_position_engine/` + `migrations/versions/20260820_position_engine.py` + `tests/unit/test_position_*.py` + `tests/unit/position_test_support.py`
**Status:** COMPLETE — TESTED (not PRODUCTION)
**Full suite:** **1248 tests passing** (1194 baseline + 54 Phase 11)

---

## 1. What Phase 11 is

The **Position Engine** converts normalized execution/fill events into durable,
authoritative, idempotent position state, persisted to PostgreSQL. It is
broker-independent (operates on `PositionFill`, never on Zerodha/Upstox/Angel One
payloads), sits directly after the Execution Engine, and stops before
Portfolio / P&L / Reconciliation.

```
Broker / Test Execution Event
        ↓
Execution Engine (Phase 9)
        ↓
Normalized Fill  (PositionFill)
        ↓
Position Engine  (Phase 11)
        ↓
Position Event + Position State
        ↓
PostgreSQL
```

---

## 2. Position identity (documented decision)

**Canonical position key = `(strategy_run_id, instrument_id, trading_mode)`.**

This **preserves** the existing `uq_positions_strategy_run_id_instrument_id_trading_mode`
unique constraint (the durable backstop). A strategy run already scopes account +
mode context; `broker_account_id` is a recorded (nullable) attribute, not a key
dimension. `side` is **not** a key dimension — it is derived from signed net
quantity.

A fill whose order has no `strategy_run_id` cannot be attributed to a position and
is rejected (`PositionIdentityError`) — fail-closed, no guessing.

---

## 3. Lifecycle / state model

Smallest clear lifecycle, derived deterministically from net quantity:

| State | Meaning |
|---|---|
| `FLAT` | no open position (net quantity == 0) |
| `OPEN` | net quantity != 0 |
| `CLOSED` | opened position reduced to zero (closed_at set) |

`PARTIALLY_CLOSED` is deliberately **not** a stored state — it is derivable from
the append-only event trail (a `POSITION_DECREASED` event while the row remains
`OPEN`).

---

## 4. Fill semantics

- **Long-only** — `BUY` opens/increases a long; `SELL` decreases/closes it.
- **No short** — a `SELL` with no open long (or exceeding it) is rejected
  (`PositionOverCloseError`). Shorting is **UNSUPPORTED** in Phase 11.
- **No flip** — a `SELL` that would cross zero is rejected, never silently
  converted to a short.
- **Partial fills** — `SELL` up to the current quantity reduces it; the average
  entry of remaining shares is unchanged.
- **Full close** — `SELL == current` → quantity 0, `average_price = NULL`,
  `status = CLOSED`, `closed_at` set.
- **Reopen** — a `BUY` after close reuses the same canonical row
  (`FLAT → OPEN`), resetting `opened_at` and clearing `closed_at`.

---

## 5. Average-price calculation

Weighted average using exact `Decimal` arithmetic (never binary float):

```
new_avg = (prev_qty × prev_avg + fill_qty × fill_price) / (prev_qty + fill_qty)
```

Rounded to 4 dp (`Decimal("0.0001")`, `ROUND_HALF_EVEN`) matching the
`positions.average_price Numeric(18,4)` column. Tested: one fill, accumulation
(`(100×100 + 50×110)/150 = 103.3333`), partial close, close/reopen.

---

## 6. Execution identity + idempotency

- **Durable execution identity** = `PositionFill.execution_id` (produced by the
  Execution Engine via `compute_event_identity`, preferring `source_event_id` /
  `broker_event_id`).
- **Idempotency backstop** = `position_events.source_event_id` (unique) stores the
  execution identity; `event_payload["_content_hash"]` stores the fill's content
  hash.
- **Duplicate** (same identity + same payload) → idempotent no-op (`DUPLICATE`).
- **Conflict** (same identity + different payload) → original preserved +
  append-only `POSITION_CONFLICT` evidence + `PositionConflictError`.

---

## 7. Transaction boundary + concurrency

- **COMMIT is truth** — position row + event row persist in one transaction;
  any failure rolls back with no partial mutation.
- **In-process** — per-position keyed lock serializes concurrent fills for the
  same key.
- **Cross-process** — `SELECT … FOR UPDATE` row-locks the position row; the
  `source_event_id` + position-key unique constraints are the durable final
  boundary.
- **Restart recovery** — state is fully reconstructable from PostgreSQL; a fresh
  engine over the same repository re-reads identical state.

---

## 8. Broker-snapshot boundary

Phase 10 broker position snapshots are external observations only. Phase 11
**never** overwrites internal position state from a broker snapshot — there is no
ingestion/mutation path (`test_no_broker_snapshot_overwrite_path`). The internal
`PositionSnapshot` read model is what Phase 14 reconciliation will consume.

---

## 9. Trading-mode safety

- `BACKTEST` → allowed.
- `PAPER` → allowed (same canonical semantics; no separate paper ledger).
- `LIVE` → fail-closed (`PositionModeError`).
- Unknown mode → reject.

`GLOBAL_TRADING_HALT` defaults active (fail-closed).

---

## 10. What Phase 11 does NOT do (scope boundary)

- No broker API calls / SDK / credentials / HTTP (no `zerodha`/`upstox`/`angel`/`kite`
  imports — source-scanned).
- No portfolio aggregation, no full P&L (`realized_pnl` / `unrealized_pnl` columns
  remain `NULL` — Phase 13 owns them).
- No reconciliation engine.
- No short/flip accounting.
- No LIVE enablement.

---

## 11. Tests (54 new)

| File | Focus |
|---|---|
| `test_position_identity.py` (6) | deterministic key, distinct dims, account mismatch |
| `test_position_arithmetic.py` (9) | weighted average, buy/sell deltas, over-close |
| `test_position_engine.py` (10) | open/accumulate/partial/full close/reopen/dup/conflict/invalid/over-close |
| `test_position_concurrency.py` (7) | 2 fills, 20 fills, same-exec, diff positions, restart, replay |
| `test_position_repository.py` (7) | ORM mappers, builders, unique-constraint, rollback |
| `test_position_schema.py` (4) | `last_execution_id` column, identity constraint, migration chain |
| `test_position_security.py` (8) | LIVE/unknown/halt, no-broker-SDK, no-overwrite, no-secrets |
| `test_position_e2e.py` (3) | BrokerOrderEvent → normalize_fill → engine → read |

---

## 12. Known limitations

- **Live PostgreSQL verification deferred** (no Docker in this environment) — the
  SQLAlchemy repository is exercised through the in-memory double + schema tests;
  real `FOR UPDATE` / row-lock behavior must be re-verified at VERIFIED/PRODUCTION.
- **Long-only** — short/flip are rejected; Phase 11 does not fake short accounting.
- **No P&L** — `realized_pnl` / `unrealized_pnl` are intentionally left `NULL`.
- **Per-position lock dict** is bounded by (strategy runs × instruments); the
  durable DB constraints are the real cross-process boundary.

---

## 13. Register-file note

`TRADING_ENGINE_REGISTER.md`, `CURRENT_ARCHITECTURE_REGISTER.md`,
`PLATFORM_CAPABILITY_MATRIX.md`, `TECHNOLOGY_STACK_REGISTER.md`,
`DEPENDENCY_REGISTER.md` do not exist as committed files; their content is
consolidated into `IMPLEMENTATION_STATUS.md` (§5.11 Position Engine matrix updated
to TESTED, §0k added).
