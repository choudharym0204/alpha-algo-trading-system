# P13 — P&L Engine — Session Report

**Date:** 2026-08-20
**Phase:** 13 (P&L Engine)
**Status:** COMPLETE — **TESTED**
**Regression:** 1349 tests passing (1290 baseline + 59 Phase 13)

---

## 1. Objective

A deterministic, auditable, broker-independent **P&L Engine** for realized,
unrealized, gross, net, trade/position/strategy/account/daily P&L, derived from
authoritative execution + position facts (Phase 11) and normalized reference
prices (Phase 3/12), with explicitly-supplied costs.

It does **not** own order submission, broker APIs, position creation, portfolio
aggregation, reconciliation (Phase 14), UI, or live enablement.

```
Normalized Executions/Fills + Authoritative Positions + Reference Prices + Costs
            ↓
        P&L Engine
            ↓
   P&L State / Events / Snapshots
            ↓
        PostgreSQL
```

---

## 2. Accounting Method

**Weighted Average Cost** (long-only) — the project's existing standard.

- Average cost is established by the **Phase 11 Position Engine** (`weighted_average`); the P&L engine consumes it, it does not recompute it.
- BUY increases cost basis (Phase 11); SELL reduces quantity; partial close keeps the remaining average unchanged.
- **Realized P&L** = `(sell_price − average_cost_before_sell) × closed_quantity`.
- Reopen starts a new cost-basis cycle (new average, no stale reuse).
- Flip/short is rejected (Phase 11 boundary preserved) → `PnlOverCloseError`.

---

## 3. Formulas (exact `Decimal`, 4-dp half-even)

- **Realized gross** = `(sell − avg_cost) × closed_qty`
- **Net** = `gross − costs`
- **Unrealized** = `(reference_price − avg_cost) × open_qty` (mark-to-market)
- **Gross exposure → P&L** aggregation = sum of realized gross + unrealized
- **Net P&L** = realized net + unrealized

Single-currency is assumed (documented); no FX logic introduced.

---

## 4. Realized P&L

Computed only when quantity is reduced/closed (SELL). The closing fill's cost
basis is the position's authoritative average cost **before** the sell. Costs
(sell-side) are subtracted for net. Position-level realized P&L is the sum of
`pnl_events.net_pnl` for that position.

---

## 5. Unrealized P&L

Mark-to-market, recalculable (not an immutable fact). Price freshness is
enforced (mirrors Phase 3/12): missing/invalid → `UNAVAILABLE` (`unrealized_pnl=None`),
stale/future → `DEGRADED` (value present but flagged). Flat position → `0`.

---

## 6. Costs

Only explicitly-supplied `CostComponent` values (brokerage/commission/exchange
charges) are used; nothing is invented (no tax formulas). Gross vs costs vs net
are kept separate. Sell-side costs are netted; buy-leg netting is deferred
(documenting the limitation).

---

## 7. Aggregation (no double counting)

```
Trade P&L  →  Position P&L  →  Strategy P&L  →  Account P&L  →  Portfolio P&L
```

Every higher level is the **sum** of lower-level facts (`pnl_events`). Strategy
and account aggregations are pure functions over realized events; unrealized is
attached via `combine_unrealized`. Account isolation is strict.

---

## 8. Daily P&L

`daily_aggregation(events, tz=...)` buckets realized events by local trading
day. The timezone is a **configurable boundary** (passed in), not hardcoded;
default is UTC unless configured.

---

## 9. Persistence & Identity

- `pnl_events` — append-only accounting facts; `execution_id` **unique** (durable idempotency backstop); indexed by account/strategy/position/instrument.
- `pnl_snapshots` — account-scoped read model; unique `(account_id, trading_mode, snapshot_at)`.
- `event_content_hash` — SHA-256 conflict detection (same identity + different payload → CONFLICT, never overwrite).

Alembic migration: `migrations/versions/20260820_pnl_engine.py` (down_revision `20260820_portfolio_engine`).

---

## 10. Idempotency / Concurrency / Recovery

- Duplicate execution → `DUPLICATE` (no second effect); different payload → `CONFLICT`.
- COMMIT is truth; rollback on failure; no false success.
- Concurrency boundary is the DB unique constraint (append-only; no `FOR UPDATE` needed).
- Restart recovery: reconstruct realized totals from durable events.

---

## 11. Boundaries (mandatory)

- **No reconciliation** (Phase 14).
- **No broker calls / SDK**.
- **No P&L from UI / broker cache / strategy-local state.**
- **LIVE fail-closed**: `LIVE`/unknown mode rejected; global halt blocks computation.
- **No mutation of historical facts** (append-only).

---

## 12. Tests (59 new)

- `test_pnl_accounting.py` (15) — realized/net/unrealized, weighted average, partial/full close, break-even, negative/zero, fees-without-P&L, exact Decimal.
- `test_pnl_unrealized.py` (9) — fresh/increase/decrease/zero/missing/stale/future/invalid/flat/no-average.
- `test_pnl_engine.py` (17) — buy no-op, partial/full close, losing close, accumulation, costs, over-close, flat reject, LIVE/halt, duplicate, conflict, reopen.
- `test_pnl_aggregation.py` (6) — strategy/account/daily, no double-count, account isolation, combine-unrealized.
- `test_pnl_concurrency.py` (4) — concurrent duplicate, concurrent fills, restart replay, replay duplicate.
- `test_pnl_security.py` (7) — LIVE/unknown/halt, no-mutation path, no broker SDK, no secrets, account/strategy isolation.
- `test_pnl_schema.py` (5) — event/snapshot columns + constraints + migration chain.
- `test_pnl_e2e.py` (1) — Execution→Position→P&L→read-back.

---

## 13. Review Findings & Fixes

4-axis adversarial review (`review.md`): **0 BLOCKER / 0 MAJOR / 2 MINOR (fixed) / 2 NOTE.**

- **MINOR-1 (fixed):** missing `PnlError` import in the engine error path.
- **MINOR-2 (fixed):** migration timestamp server-default `sa.text("now()")` → `sa.func.now()`.
- **NOTE-1:** buy-leg cost netting out of scope (documented).
- **NOTE-2:** `positions.realized/unrealized_pnl` columns not written (dual-writer avoided; P&L facts in `pnl_events`/`pnl_snapshots`).

---

## 14. Remaining Limitations

- Live PostgreSQL / Docker verification deferred (no Docker); exercised via in-memory double + schema tests.
- No real broker cost/fill data (fakes only); never marked PRODUCTION.
- Buy-leg cost netting deferred.
- External review subagents unavailable at the model layer; inline review recorded transparently.

## 15. LIVE Status

`LIVE_TRADING_ENABLED = false`, `GLOBAL_TRADING_HALT = true` (fail-closed). No P&L path enables trading.

---

## 16. Next Phase

**Phase 14 — Reconciliation Engine.** NOT started.
