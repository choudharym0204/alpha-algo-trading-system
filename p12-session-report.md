# P12 — Portfolio Engine — Session Report

**Date:** 2026-08-20
**Phase:** 12 (Portfolio Engine)
**Status:** COMPLETE — **TESTED**
**Regression:** 1290 tests passing (1248 baseline + 42 Phase 12)

---

## 1. Objective

A broker-independent, durable, deterministic **Portfolio Engine** that aggregates
authoritative Phase-11 position state + account/funds state + normalized reference
prices into account- and mode-scoped portfolio snapshots persisted to PostgreSQL.

It does **not** become the P&L engine (Phase 13) or the reconciliation engine
(Phase 14), does not submit orders, and does not call brokers.

```
Authoritative Positions  +  Account/Funds  +  Market Prices
            ↓
      Portfolio Engine
            ↓
   Portfolio State / Snapshot
            ↓
        PostgreSQL
```

---

## 2. Portfolio Identity

- **Canonical portfolio key = `(broker_account_id, trading_mode)`.**
- **Snapshot identity = portfolio + `snapshot_at`.**
- Preserves the existing `portfolio_snapshots` unique constraint
  `uq_portfolio_snapshots_account_mode_snapshot_at` as the durable safety boundary.
- No duplicate authoritative record for the same logical portfolio can exist;
  the database constraint is the backstop (not a random UUID).
- `broker_account_id` is nullable on the model (BACKTEST/paper may have no live
  broker account) while the engine treats account identity as required.

---

## 3. Aggregation Semantics

Inputs are normalized, broker-independent types (`PortfolioInputs`):

- `positions` — `PositionInput` (Phase-11 authoritative position state)
- `funds` — `FundsState` (Phase-10 normalized funds snapshot)
- `prices` — `ReferencePrice` (Phase-3 normalized market data)

Position quantities are read verbatim from the Position Engine — never
independently recalculated. Only **open** positions (`quantity != 0`) are
counted; FLAT/CLOSED positions are excluded.

---

## 4. Exposure Formulas (exact `Decimal`, 4-dp half-even)

For each open position with a reference price `p` and net quantity `q`:

- position exposure `e = q × p` (signed)
- **Gross exposure** = `Σ |e|`
- **Net exposure** = `Σ e`
- **Long exposure** = `Σ max(e, 0)`
- **Short exposure** = `Σ max(−e, 0)` — stays `0` because Phase 11 is long-only

---

## 5. Market Value Semantics

```
market_value_i = quantity_i × reference_price_i
```

- Reference price comes from the normalized market-data layer only.
- **Zero open positions** → `market_value = 0` (a real, known value).
- **Open positions, all priced** → `market_value = Σ e`.
- **Open positions, some missing** → `market_value` = partial sum of priced
  positions, `completeness = PARTIAL`, `status = DEGRADED`, missing ids flagged.
- **Open positions, none priced** → `market_value = None` (unavailable — never
  fabricated as zero).
- **Average entry price is carried through but never used for exposure/market
  value** (it is a Phase-13 P&L input).

---

## 6. Price Freshness

`classify_price` returns FRESH / STALE / MISSING:

- MISSING → excluded from totals, flagged, `PARTIAL`/`DEGRADED`.
- STALE (older than `max_age_seconds`, or **future-dated**) → included but
  flagged in `stale_instrument_ids`, `DEGRADED`.
- No silent use of stale/future prices as if current.

---

## 7. Cash / Funds / Margin

- Funds flow in as a normalized `FundsState`; the engine never overwrites
  internal portfolio truth from broker data.
- Unavailable funds → `cash_balance = None` (never zero), `funds_available = False`.
- `available_margin` / `used_margin` are reported as facts (not re-ruled —
  the Risk Engine consumes them).
- **Portfolio value** = `cash_balance + market_value`, computed only when the
  portfolio is COMPLETE; otherwise `None`.

---

## 8. Strategy Aggregation

`strategy_breakdown` is a **derived read model** computed from per-position
exposures, keyed by `strategy_run_id`. It is not a separate source of truth —
authoritative positions remain the single source.

---

## 9. Snapshot Model

`PortfolioSnapshot` (immutable read model) captures: account id, trading mode,
status, completeness, position count, gross/net/long/short exposure, market
value, cash balance, equity value, available/used margin, snapshot timestamp.

The ORM `portfolio_snapshots` model gained queryable aggregate columns
(`market_value`, `gross_exposure`, `net_exposure`, `long_exposure`,
`short_exposure`, `position_count`, `available_margin`, `used_margin`, `status`)
plus a `(broker_account_id, trading_mode)` index. `snapshot_payload` stores a
bounded JSON payload (content hash, completeness, missing/stale ids, strategy
breakdown) — no arbitrary unbounded blobs.

Alembic migration: `migrations/versions/20260820_portfolio_engine.py`
(down_revision `20260820_position_engine`).

---

## 10. Idempotency, Concurrency, Transaction Boundary

- **Snapshot idempotency:** unique constraint on `(account, mode, snapshot_at)`;
  duplicate write → `DuplicateSnapshotError` → re-read existing → idempotent result.
- **Transaction boundary:** compute + INSERT + COMMIT; any failure → ROLLBACK;
  success is never reported before COMMIT.
- **Concurrency:** append-only snapshots, no global lock; PostgreSQL unique
  constraint is the durable boundary (no `FOR UPDATE` needed — no row mutation).
- **Restart recovery:** recompute from durable inputs reproduces the same state.

---

## 11. Frequency Model

On-demand snapshot generation only (bounded, deterministic). No high-frequency
loop and no scheduler are implemented — the periodic-scheduler boundary is
documented for a future phase.

---

## 12. State Machine

`UNINITIALIZED / READY / DEGRADED / ERROR` (smallest useful set):

- READY — all open positions freshly priced + funds available.
- DEGRADED — any stale/missing price or funds unavailable (flagged, never zero).
- ERROR — reserved for computation failure.

`Completeness` = `COMPLETE` / `PARTIAL` (partial is never reported as complete).

---

## 13. Boundaries (mandatory)

- **No P&L:** `realized_pnl` / `unrealized_pnl` remain NULL placeholders; Phase 13 owns them.
- **No reconciliation:** no broker comparison/correction path; Phase 14 owns it.
- **No broker calls:** package imports no broker SDK; only normalized types cross the boundary.
- **LIVE fail-closed:** `LIVE` mode rejected; unknown mode rejected; global halt blocks computation.

---

## 14. Tests (42 new)

- `test_portfolio_identity.py` (6) — account/mode isolation, uniqueness, duplicate, LIVE reject.
- `test_portfolio_aggregation.py` (11) — zero/one/multi, exposure, strategy breakdown, funds, stale/missing/future, margin.
- `test_portfolio_snapshots.py` (7) — create/persist, duplicate, deterministic recalc, rollback, DB failure, restart recovery, content hash.
- `test_portfolio_concurrency.py` (4) — concurrent same/different portfolio, consistent aggregates, restart.
- `test_portfolio_security.py` (7) — LIVE block, unknown mode, halt, cross-account leak, no broker SDK, no secrets, no P&L.
- `test_portfolio_schema.py` (4) — columns, unique constraint, index, migration chain.
- `test_portfolio_e2e.py` (2) — Position→Portfolio→read-back; average-vs-reference price.

---

## 15. Review Findings & Fixes

4-axis adversarial review (`review.md`): **0 BLOCKER / 0 MAJOR / 3 MINOR (fixed) / 2 NOTE.**

- **MINOR-1 (fixed):** missing `Integer` import in `safety.py`.
- **MINOR-2 (fixed):** zero-position `market_value` now `0` (known) vs open-but-unpriced `None`.
- **MINOR-3 (fixed):** security-scan path `parents[3]`→`parents[2]` (scans were vacuous).
- **NOTE-1:** append-only snapshots → unique constraint (not `FOR UPDATE`) is the concurrency boundary.
- **NOTE-2:** nullable `broker_account_id` vs required engine account key (documented).

---

## 16. Remaining Limitations

- Live PostgreSQL / Docker verification deferred (no Docker in this environment);
  real row-lock/constraint behavior exercised through in-memory double + schema tests.
- No real broker funds/positions (Phase 10/11 tested via fakes); no PRODUCTION / LIVE_PROVIDER claim.
- No periodic snapshot scheduler (on-demand only, per scope).
- External adversarial-review subagents unavailable at the model layer; review performed inline against source (recorded transparently).

## 17. LIVE Status

`LIVE_TRADING_ENABLED = false`, `GLOBAL_TRADING_HALT = true` (fail-closed). No
Portfolio path enables LIVE trading.

---

## 18. Next Phase

**Phase 13 — P&L Engine** (owns `realized_pnl` / `unrealized_pnl`). NOT started.
