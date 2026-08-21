# Alpha Algo — Controlled LIVE Readiness (Phase 24)

Phase 24 implements the **controlled live-release progression** capability
(`Live release - SHADOW→FULL`, §5.14). It is **advisory readiness only**: it
formalizes *how* the system progresses toward LIVE without ever enabling real
order submission. LIVE remains fail-closed.

## 1. Scope (from control documents)

- `IMPLEMENTATION_STATUS.md` §5.14: `Live release - SHADOW→FULL | MISSING | 24 | Phase 23 + ops | controlled progression`
- Maturity `LEVEL 5 = CONTROLLED LIVE` (broker + risk + reconciliation verified).
- "No adapter is marked PRODUCTION — requires real provider/sandbox + controlled-live validation (Phase 24+)."

The single real gap was the absence of a **release-stage** concept and a
**controlled-progression controller**.

## 2. What was built (additive, `services/risk_engine/.../gates.py`)

- **`LiveReleaseStage`** — `DISABLED → SHADOW → FULL`.
- **`LiveReleaseDecision`** — immutable, tz-aware, self-validating (an *approved*
  decision can never carry failed gates, an active halt, or an open breaker).
- **`LiveReleaseController`** — fail-closed state machine:
  - starts `DISABLED`;
  - `advance_to_shadow(actor, reason, snapshot)` → re-evaluates the **17 LIVE
    safety gates** + **global halt** (kill switch) + **circuit breaker**; advances
    only when all pass;
  - `advance_to_full(...)` → only from `SHADOW`, with the same full re-evaluation;
  - `disable(actor, reason)` → pull back to `DISABLED` at any time (fail-closed);
  - `can_submit_live(live_trading_enabled)` → advisory readiness signal (default
    `False`; only `True` at `FULL` + config `live_trading_enabled` + halt inactive
    + breaker closed).

## 3. Progression state machine

```
DISABLED ──advance_to_shadow(gates green)──▶ SHADOW ──advance_to_full(gates green + breaker closed)──▶ FULL
    ▲                                                                                                        │
    └────────────────────────────────────── disable() (always allowed) ◀────────────────────────────────────┘
```

Transitions are audited (actor + reason) and immutable; stage mutation is atomic.

## 4. Safety boundary (LIVE stays fail-closed)

`LiveReleaseController` is **advisory only**. It never enables, routes, or
submits real orders. The hard LIVE boundary is unchanged and remains fail-closed:

- `LIVE_TRADING_ENABLED=false` (config)
- `GLOBAL_TRADING_HALT=true` (config) + `GlobalHaltRule` (first risk rule)
- `LiveModeRule` (blocks LIVE unless explicitly enabled)
- broker `_guard_live` + `supported_modes={BACKTEST, PAPER}` + `supports_live_trading=False`

Reaching `FULL` does **not** enable actual live submission — it only declares
readiness, and `can_submit_live` still returns `False` unless the config flag is
independently turned on. Phase 24 does not modify `TradingMode`, broker
adapters, or any tested engine.

## 5. Verification evidence

- `tests/unit/test_live_release.py` — 12 tests (fail-closed default, green
  shadow/full progression, failed-gate/halt/breaker blocks, `NOT_IN_SHADOW`,
  idempotent guards, `disable` pull-back, `can_submit_live` fail-closed,
  decision invariant).
- Full backend regression green (see `P24-session-report.md`).
- `ruff` clean · security scan clean · migration graph OK.

## 6. Out of scope (explicitly not done)

- Real broker/sandbox connectivity and actual `SHADOW` order routing (shadow
  fills/P&L) — deferred (no real providers in this environment).
- Actual `FULL` live order submission — remains behind the existing fail-closed
  guards; requires `LIVE_TRADING_ENABLED=true` + real broker integration, which
  is a separate, explicitly-gated operational decision beyond Phase 24.
