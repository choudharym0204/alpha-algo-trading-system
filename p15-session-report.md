# P15 — Paper Trading Completion — Session Report

**Date:** 2026-08-20
**Phase:** 15 (Paper Trading Completion)
**Status:** COMPLETE — **TESTED**
**Regression:** 1476 tests passing (1412 baseline + 64 Phase 15)

---

## 1. Objective

Turn the existing paper-trading foundation (P8-001) into a complete operational
paper runtime — an explicit PAPER account, a deterministic cash/reserve funds
ledger, paper-run identity, an explicit cost model, an authoritative
trading-mode routing boundary, a `PaperTradingService` orchestrator, and
durable persistence — without ever touching LIVE.

---

## 2. Architecture

The Phase-15 runtime lives in a **separate package** `alpha_algo_paper_runtime`
(alongside, not inside, the minimal `alpha_algo_paper_trading` foundation). This
preserves the foundation's strict structural safety allowlist while giving the
operational layer an appropriate scope.

```
alpha_algo_paper_trading (foundation, P8-001)   — deterministic simulator core
        │  PaperBrokerAdapter / PaperOrderBook / fill_policy / types
        ▼
alpha_algo_paper_runtime (Phase 15)             — operational layer
        account · funds · run · costs · routing · service · repository
        ▼
shared db models (paper_runs / paper_accounts / paper_funds)  +  migration
```

---

## 3. Paper Account & Run

- `PaperAccount` — `account_id`, `trading_mode` pinned `PAPER`, explicit
  `starting_capital` (never silently defaulted), `status`, `created_at`/`reset_at`,
  `paper_run_id`. Never a real broker account id; never shares state with LIVE.
- `PaperRun` — `paper_run_id` (deterministic when seeded, securely unique
  otherwise), `config_hash` (SHA-256 replay fingerprint), `status`, timestamps.

---

## 4. Funds Ledger

`PaperFunds` — immutable, deterministic cash/reserve ledger:

- `available_cash` (never negative), `reserved_cash`, `currency`.
- `reserve` / `release` / `settle_buy` / `credit_sell` operations.
- Funds validation is a **service-level pre-submission guard** (the v1 broker is
  funds-unaware by design). Insufficient funds → normalized REJECTED outcome,
  no fill, funds unchanged.

---

## 5. Cost Model (explicit, deterministic)

- **Default = ZERO slippage + ZERO commission** (nothing applied silently).
- `SlippageModel.ZERO | FIXED_BPS` and `CommissionModel.ZERO | FIXED_PER_TRADE`.
- `apply_slippage` (BUY pays more / SELL receives less) + `commission_amount`.
- `PaperCostModel.as_config()` provides a replay fingerprint.
- No tax formulas invented. Costs are a cash-flow concern of the service, not
  of the broker's raw fill price (which stays at the reference price).

---

## 6. Mode Routing (LIVE fail-closed)

`resolve_provider` / `TradingModeRouter`:

- `BACKTEST → backtest engine`, `PAPER → paper broker`, `LIVE → blocked`.
- `LIVE`/`live` → `LiveTradingDisabledError`; unknown/missing → `UnknownTradingModeError`;
  global halt → `TradingHaltedError`. Never selected by UI string.

---

## 7. Service & Execution Model

`PaperTradingService.submit(...)`:

1. Guard account active + quantity + side.
2. Pre-submission funds guard (BUY affordability via `decide_fill`).
3. Submit through `PaperBrokerAdapter` (normalized `BrokerOrderRequest`).
4. Drain normalized events → fill price or rejection reason.
5. Apply deterministic cost model → update funds ledger → persist.

Fills remain simulator-confirmed and PAPER-labeled; positions flow through the
broker's authoritative fill trail (and, in E2E, through the real Position
Engine via `PositionFill`).

---

## 8. Persistence

New paper-specific durable state only (no duplicate order/execution/position
storage): `paper_runs`, `paper_accounts`, `paper_funds` (SQLAlchemy models +
Alembic migration `20260820_paper_trading`, down_revision
`20260820_reconciliation_engine`). `SqlPaperRepository` maps ORM ↔ runtime; the
in-memory double lives in tests. Funds restore across restart is tested.

---

## 9. Determinism / Replay / Isolation

- Deterministic: same reference + order sequence + config → same fills/cash.
- Replay: seeded `paper_run_id` + `compute_config_hash` fingerprint.
- Isolation: separate runs/accounts never share funds or order identity.

---

## 10. Reconciliation

Paper state reconciles through Phase 14 (no second system): funds match/mismatch
and position match are E2E-tested via the Phase-14 adapters + `ReconciliationEngine`.

---

## 11. Testing (64 new)

- `test_paper_account.py` (6) — PAPER pinning, capital, status, tz.
- `test_paper_funds.py` (9) — reserve/release/settle/credit, no-negative.
- `test_paper_run.py` (8) — id determinism, config hash, validation.
- `test_paper_costs.py` (9) — zero default, FIXED_BPS/FIXED_PER_TRADE, fingerprint.
- `test_paper_routing.py` (9) — PAPER/BACKTEST/LIVE/unknown/halt.
- `test_paper_service_e2e.py` (7) — BUY→HOLD→SELL→CLOSE, insufficient funds,
  position-engine fill, funds reconciliation, position reconciliation, restart recovery.
- `test_paper_determinism.py` (3) — identical inputs → identical results.
- `test_paper_isolation.py` (3) — accounts/runs isolated.
- `test_paper_security.py` (6) — source scan (no broker SDK/secret/live/bypass).
- `test_paper_schema.py` (4) — ORM columns, FK, unique constraint, migration chain.

---

## 12. Review Findings & Fixes

4-axis adversarial review (`review.md`): **0 BLOCKER / 0 MAJOR / 0 MINOR remaining / 4 NOTE.**

- **NOTE-1:** funds validation is service-level (broker funds-unaware by design).
- **NOTE-2:** runtime lives in a separate package to preserve the foundation's safety allowlist.
- **NOTE-3:** broker order book is in-memory (full book persistence deferred).
- **NOTE-4:** cross-engine orchestration E2E (Strategy→…→Execution in one flow) deferred — each engine individually TESTED, paper-broker→position→reconciliation E2E tested.

---

## 13. Known Limitations (honest status)

- Full **cross-engine orchestration** (Strategy→Signal→Risk→Orchestrator→OMS→Execution→Paper in a single flow) is **not** wired — deferred.
- Paper broker's order book is **in-memory** (funds/account/run persist; full order/execution book restart recovery deferred).
- **Partial fills:** UNSUPPORTED (v1 fills complete quantity; no fake partial fills).
- **Cancellation:** UNSUPPORTED (v1 has no working orders — every order reaches a terminal state at submission).
- Live PostgreSQL verification deferred (no Docker); exercised via in-memory doubles + schema tests.

## 14. LIVE Safety

`LIVE_TRADING_ENABLED = false`, `GLOBAL_TRADING_HALT = true` (fail-closed).
PAPER never routes to LIVE; no real broker execution; no direct
Position/P&L bypass; no secrets in logs.

---

## 15. Next Phase

**Phase 16 — Backtesting Expansion.** NOT started.
