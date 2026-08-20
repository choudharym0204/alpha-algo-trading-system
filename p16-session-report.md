# P16-session-report.md — Phase 16: Backtesting Expansion

**Project:** Alpha Algo Trading System
**Date:** 2026-08-20
**Status:** COMPLETE — TESTED (never PRODUCTION / LIVE_READY)
**Baseline:** 1476 tests passing (Phases 1–15)
**Result:** 1611 tests passing (+135), 1 pre-existing warning (FastAPI `httpx` deprecation, unrelated to Phase 16)

---

## 1. Objective

Expand the existing deterministic backtesting subsystem into a fuller quantitative-research / portfolio-simulation system **without breaking** its deterministic, look-ahead-safe, LIVE-isolated design. The existing P7-001 foundation, P7-002 engine, P7-004 reports, and P7-003 walk-forward are preserved **byte-for-byte**; Phase 16 is entirely additive.

## 2. What was built (6 new packages, all under `backtesting/`)

| Package | Purpose |
|---|---|
| `alpha_algo_backtest_analytics` | Advanced metrics: CAGR, historical VaR/CVaR, CAPM Alpha/Beta, per-trade MFE/MAE, and a composite `compute_advanced_metrics`. |
| `alpha_algo_backtest_quality` | Observational data-quality classification: `valid` / `quarantined` / `rejected` (no silent repair). |
| `alpha_algo_backtest_optimize` | Deterministic lexicographic grid search + reproducible (seeded, SHA-256-derived) bootstrap Monte Carlo. |
| `alpha_algo_backtest_persistence` | Optional outer-layer run identity (canonical SHA-256, wall-clock excluded) + stable JSON record + in-memory store with duplicate/conflict semantics + result caching key. |
| `alpha_algo_backtest_portfolio` | Multi-symbol, shared-capital, long-only portfolio simulation with explicit capital allocation (reserved-cash floor + per-symbol budget caps). |
| `alpha_algo_backtest_latency` | Deterministic latency model (signal/decision/submission/fill components) that shifts intent effective-decision time. |

## 3. Features, semantics, and accounting model

### 3.1 Advanced metrics
- **CAGR** — `exp(ln(ending/beginning) · ppy/periods) − 1` via `Decimal.ln/exp` (no float). `periods_per_year` is an explicit caller basis (the analytics package has no calendar model). `None` on insufficient duration; non-positive capital raises `AnnualizationError`.
- **VaR/CVaR** — historical (non-parametric) order-statistic; `k = max(1, floor((1−c)·n))`; loss magnitudes clamped ≥ 0; per-period, informational, no distribution/horizon claim.
- **Alpha/Beta** — population covariance/variance with an injected per-period risk-free rate; requires explicitly aligned benchmark series + `benchmark_identity` + `frequency`; `None` when undefined.
- **MFE/MAE** — post-trade analytics over the strict `(entry, exit]` price path (no data beyond trade close); long/short mirrored; `mfe ≥ 0`, `mae ≤ 0`.

### 3.2 Portfolio simulation + capital allocation
- One `PortfolioInput` per symbol universe (unique symbols/instruments); deterministic combined digest over sorted `symbol=sha256` pairs.
- **Shared cash pool** (never infinite): every BUY is evaluated against available cash.
- **Reserved-cash floor**: a fill that would push cash below `reserved_cash` is refused (`INSUFFICIENT_CASH`).
- **Per-symbol budget**: a BUY whose gross notional (`quantity × fill_price`) exceeds the symbol budget is refused.
- **Long-only**: SELL beyond position → `INSUFFICIENT_POSITION` (short/flip never silently created — mirrors the production Position Engine).
- Reuses the single-engine `evaluate_fill` + FIFO ledger per symbol (identical cost-attribution), merging all symbols into a `(timestamp, symbol)`-sorted global timeline for determinism. Equity = `cash + Σ(position · last-mark)`.

### 3.3 Optimization + Monte Carlo
- Grid search in deterministic lexicographic order with first-evaluation tie-break; **train/test separation is caller-closure enforced** (optimizer never sees the test set). Sequential only.
- Monte Carlo: seeded SHA-256 PRNG (no `random` module); bootstrap with replacement; deterministic shuffle; summary with mean/min/max + p5/p50/p95.

### 3.4 Persistence / identity / caching (outer layer)
- `BacktestRunIdentity` canonical digest over immutable inputs (dataset, strategy, config, cost model, capital, period, universe, simulator version, seed). Wall-clock excluded.
- `BacktestRecord` round-trips stable JSON with integrity validation; `InMemoryBacktestStore` keys by identity digest (duplicate → no-op, conflicting payload → error).
- Core backtest remains a pure computation independent of persistence.

### 3.5 Latency
- `LatencyModel` sums `signal/decision/submission/fill` delays (all non-negative, zero default); `apply_latency` shifts `decided_at`. Simulation time controls latency (no wall-clock sleep). Verified to move fills to a strictly later record.

## 4. Explicitly DEFERRED / UNSUPPORTED (honest scope)

| Spec item | Decision | Rationale |
|---|---|---|
| STOP / STOP_LIMIT (§9) | **DEFERRED** | Intra-bar trigger on candle data is unknowable without flattering fills (the existing `CANDLE_LIMIT_NO_IMPROVEMENT` precedent). |
| Partial fills (§10) | **DEFERRED** | Would entangle the engine's 1:1 intent→outcome accounting; not built half-way. |
| Market impact (§13) | **NOT IMPLEMENTED** | Data/requirements don't support a defensible model; avoided false precision. |
| Short selling / position flip (§14–15) | **DEFERRED** | Production Position Engine rejects short/flip; no independent backtest short model added. |
| Multi-timeframe data (§28) | **DEFERRED** | Availability semantics not modeled. |
| Corporate actions (§29) | **UNSUPPORTED / DOCUMENTED** | No fabricated split/dividend handling; dataset adjustment status is the caller's contract. |
| Parallel optimization (§37) | **DEFERRED** | Sequential grid only; deterministic result ordering preserved by not parallelizing. |

## 5. Testing (135 new tests)

- **Analytics** — CAGR (one-year/partial/multi-year/flat/loss/insufficient-duration/zero&negative-capital), VaR/CVaR (quantile, tail mean, empty, all-gains, out-of-range confidence), Alpha/Beta (identity, scaling, excess, flat-benchmark, misalignment), MFE/MAE (long/short, window filtering, sign invariants), composite + determinism.
- **Quality** — valid/out-of-order(REJECTED)/duplicate(QUARANTINED)/future/gap classification, rejection precedence, malformed calls.
- **Optimize** — lexicographic order, tie-break, combination count, score coercion/rejection, train/test separation, repeatability.
- **Monte Carlo** — same-seed identity, seed differentiation, path count, ordering, percentile ordering, shuffle-as-permutation.
- **Persistence** — identity determinism, seed/cost/period inclusion, wall-clock exclusion, order-stable universe, 64-hex digest, JSON round-trip, corruption/missing/invalid rejection, store duplicate/conflict semantics.
- **Portfolio** — shared capital + equity, single-symbol equivalence, simultaneous cross-symbol ordering, completed trade + realized P&L, short rejection, reserved-cash floor, budget cap, unknown-symbol/tied-decided_at rejection, input-order determinism.
- **Latency** — zero identity, component sum, shift, field preservation, fill-timing change.
- **Security** — AST import allowlist, no wall-clock/random/os usage, no broker/live identifiers, BACKTEST-only mode.

## 6. Determinism & look-ahead guarantees

- Same inputs → same output, verified by `==`-equality determinism tests and hash-seed-independent run.
- Portfolio global timeline sorted by `(timestamp, symbol)`; grid lexicographic; Monte Carlo seeded SHA-256 PRNG — none depend on scheduling/hash seeds.
- Fill timing: intent fills at the first record **strictly after** `decided_at` (per symbol); no future record contributes to signals, fills, positions, equity, or metrics.
- No wall clock, no network, no broker, no live data, no randomness (except explicitly seeded, persisted, identity-included).

## 7. LIVE safety

- `BacktestTradingMode` remains single-member (`BACKTEST`). No PAPER/LIVE path is representable.
- No broker credentials, no broker APIs, no network, no secret leakage (AST + `dir()` scans).
- Persistence is an in-memory/JSON outer layer — no filesystem writes, no DB, no production-state mutation.
- Long-only portfolio sim rejects short/flip, consistent with the production Position Engine.

## 8. Known limitations (honest)

- Live PostgreSQL / Docker verification remains deferred (tests use in-memory doubles) — consistent with Phases 11–15.
- Portfolio timeline is fully materialized in memory (bounded by input size).
- Per-symbol budget caps order gross notional (not continuously marked exposure).
- Cross-engine orchestration (Strategy→Signal→Risk→Portfolio-sim in one flow) is not wired — the portfolio sim consumes caller-decided intents like the single engine.

## 9. Verification

- Full regression: **1611 passed** (1476 baseline + 135 Phase 16), 1 pre-existing warning.
- Phase 16 capabilities are **TESTED**, not `PRODUCTION` — `PRODUCTION` requires live-DB/provider verification (Phase 24+).
