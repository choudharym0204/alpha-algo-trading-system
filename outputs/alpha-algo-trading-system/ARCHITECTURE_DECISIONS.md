# Architecture Decisions

## ADR-0001 - Use Modular Monorepo

Status: Accepted

Decision: Start with a modular monorepo containing `apps`, `services`, `packages`, `backtesting`, `migrations`, `tests`, `docs`, `infra`, and `docker`.

Reason: The system needs strong domain separation without the operational cost of premature microservices.

## ADR-0002 - Use PostgreSQL with TimescaleDB and Redis

Status: Accepted

Decision: PostgreSQL is the authoritative store, TimescaleDB handles market time-series data, and Redis handles transient realtime state.

Reason: Financial history must remain durable and queryable, while market data and realtime UI updates require efficient temporal storage and cache/pub-sub behavior.

## ADR-0003 - Keep Broker Logic Out of Strategies

Status: Accepted

Decision: Strategies emit broker-agnostic signals. Broker-specific behavior lives only in broker adapters.

Reason: Strategy behavior must be testable, versioned, portable, and auditable.

## ADR-0004 - Risk Engine Is a Mandatory Security Boundary

Status: Accepted

Decision: Every live order intent must pass through risk evaluation and execution must reject intents without valid risk approval.

Reason: Trading safety depends on a single enforceable path between strategy signals and broker orders.

## ADR-0005 - Defer Kubernetes and Kafka

Status: Accepted

Decision: Use Docker Compose for initial development and avoid Kafka unless scale or replay requirements justify it.

Reason: The initial platform should be reliable and modular without unnecessary distributed-systems complexity.

## ADR-0006 - Backtesting Runs on a Pure Simulation Clock in an Isolated Mode

Status: Accepted

Decision: The backtesting foundation (P7-001) uses a pure-arithmetic `SimulationClock` that has no wall-clock default and no way to read `datetime.now` in simulation math; BACKTEST mode is a single-member `BacktestTradingMode` enum (only `BACKTEST`, structurally excluding PAPER and LIVE); explicit historical inputs are validated strictly and fingerprinted with a repository-owned canonical sha256 manifest.

Reason: This is a deliberate divergence from the injectable-clock pattern used by live-facing engines (`clock or datetime.now(tz=UTC)`), where a wall-clock fallback is acceptable. A simulation clock with any wall-clock path would break determinism and reproducibility of archived runs. A single-member mode enum makes PAPER/LIVE leakage a type error rather than a runtime mistake (trading rule 25). The canonical manifest is owned by the repository (explicit field order, Decimal-to-str, UTC-normalized ISO-8601, explicit None) because `model_dump()`/`str(dict)`/`hash()` are version- and hash-seed-sensitive and would silently invalidate archived manifests. The only wall-clock read in the backtesting package is the audit-record timestamp, which is metadata only, never feeds simulation math, and is excluded from the content hash.

Consequences: The backtesting foundation contains zero trading semantics (no fills, orders, positions, P&L, slippage, or commissions) and performs no I/O; later simulation-engine tasks must keep this boundary.

## ADR-0007 - Paper Fills Are Simulator-Confirmed at Injected Reference Prices

Status: Accepted

Decision: The paper trading foundation (P8-001) implements a PAPER-only `PaperBrokerAdapter` whose fills are simulator-confirmed: a fill exists only as an explicit `BrokerOrderEvent` derived from an injected, caller-owned `PaperReferencePrice` snapshot, and only after `OrderExecutionState.apply_event` accepts it (exact-quantity completion). `submit_order` never returns a fill; it returns ACCEPTED or REJECTED only. The adapter emits a BROKER_ACKNOWLEDGED event before every FILL event because the P6-003 state machine has no `SUBMISSION_REQUESTED -> FILLED` edge. Order ids are derived deterministically via `uuid5(ORDER_ID_NAMESPACE, broker_account_id:client_order_id)` and every request must carry that id in `metadata["order_id"]` (fail loud if absent or mismatched, on EVERY submission including idempotent retries). `client_order_id` is the idempotency key scoped per broker account: identical duplicates return the stored response with no new events; conflicting payloads raise `ClientOrderIdConflictError`. The injected clock is required (no wall-clock default) and reference prices are required constructor input (never fetched, never defaulted to something that looks like real data); the paper session reports `authenticated=False` because it performs no authentication and never reads `secret_ref`. Average prices are exact-Decimal, quantized to `AVERAGE_PRICE_QUANTUM` with `ROUND_HALF_EVEN`.

Reason: The master prompt makes paper fills legitimate only as simulator-confirmed fills ("Submitted is not filled. Only broker-confirmed or simulator-confirmed fills can create trades."). Returning a fill from `submit_order` or reading a wall clock would violate rules 11 (no assumed fills) and the determinism precedent of ADR-0006. Reusing `MarketTick`/`BrokerQuote` as fill input would make injected simulation input look like real market data (rules 2/12); a dedicated `PaperReferencePrice` keeps the shape honest. `supports_order_cancel=False` and a raising `cancel_order` are honest for a v1 with zero working orders (every order reaches a terminal state at submission); claiming cancel support would be fake trading functionality (rule 1). No P&L, slippage, commissions, market-data ingestion, persistence, or working-order book is included: each would be fake precision at a single reference snapshot or an operational claim beyond a foundation (rules 1/3/4). Position `average_price` is the quantity-weighted mean of ALL fills (buys and sells) quantized to `AVERAGE_PRICE_QUANTUM` with `ROUND_HALF_EVEN` — explicitly NOT an average-cost basis of the remaining net position; snapshots carry `average_price_convention: "mean_fill_price"` in `raw_payload` so no future P&L/mark-to-market consumer misreads it (S5/M2 convention). Flat (zero-net) positions are not reported, and reference snapshots reject `last` outside the bid/ask spread when both legs are present.

Consequences: The paper package imports only broker-adapter contracts and execution-engine events; structural tests ban risk-engine, backtesting, network, environment, randomness, and persistence imports and allow zero wall-clock sites. Position snapshots are always labeled `TradingMode.PAPER`; `PaperPosition` refuses any other mode, so paper and live ledgers can never mix. This is the foundation, not the operational paper trading feature: `PAPER_TRADING_VERIFIED` remains a TODO LIVE safety gate and LIVE stays disabled. Later tasks (real market-data feed, persistence, reconciliation, working orders, partial fills) must keep the simulator-confirmed boundary and flip capabilities only when honestly supported.

## ADR-0008 - Paper Market-Data Feed Bridge Is a Pure Conversion, Not Ingestion

Status: Accepted

Decision: The paper market-data feed (P8-002) is implemented as a sibling package `services/paper_trading/alpha_algo_paper_feed/` — not inside `alpha_algo_paper_trading`, whose AST allowlist bans `alpha_algo_contracts` imports — exposing a pure, stateless conversion `tick_to_reference(tick: MarketTick) -> PaperReferencePrice` plus a separate `provenance_of(tick) -> TickProvenance` audit/dedup type. v1 accepts `MarketTick` only; `MarketCandle` input is rejected with a typed `PaperFeedError` because candles carry no executable bid/ask legs (every LIMIT order would silently reject under the P8-001 fill policy) and `close_price` is an interval aggregate, not a point-in-time last price — candle support, if ever added, must be a separate function with a fixed documented policy (v2 decision memo, deferred). Conversion is total over contract-valid ticks except where it fails loud: the feed defensively re-checks Decimal type, finiteness (`Decimal.is_finite()`), positivity, tz-awareness, and spread coherence (`bid <= ask`; `bid <= last <= ask` when both legs are present) — invariants the P3-002 contract permits to be violated at construction and that `PaperReferencePrice.__post_init__` enforces on the output. The Infinity hole is closed at both layers: pydantic 2.13 `finite_number` rejects non-finite values at `MarketTick` construction, and the feed's `is_finite` checks reject non-finite values reachable via `model_construct` bypasses. `reference_at` is derived from `tick.timestamp` — never the wall clock, never the `PaperReferencePrice` epoch default. Source identity never enters the snapshot: provenance is a separate `TickProvenance` type whose `(source_broker, source_sequence)` pair is the P3-003 dedup key, so caller-side dedup keys identically to `alpha_algo_market_data`.

Reason: The feed is the bridge that maps normalized market-data contracts (P3-002) into caller-owned `PaperReferencePrice` inputs for simulator-confirmed fills (P8-001, ADR-0007) without making injected simulation input look like real market data (rules 2/12). It must never fetch, subscribe, stream, embed sample data, read the wall clock, or invent quote legs — any of those would violate rules 1/2/3 and the ADR-0006/0007 determinism precedent. It cannot live inside `alpha_algo_paper_trading` because that package's structural allowlist bans `alpha_algo_contracts`; a sibling package importing both contracts and paper types preserves both boundaries. No P8-001 file is modified: fills remain decided exclusively by `decide_fill`, and the feed adds no capability flags. Live market-data ingestion remains a later, LIVE-gated task; `MARKET_DATA_ENABLED=false` stays.

Consequences: The feed package contains zero network, environment, randomness, persistence, broker-adapter, execution-engine, risk-engine, or pydantic imports (structural tests enforce an import allowlist and a banned-identifier surface scan). `PaperReferencePrice` is deliberately not re-exported by the feed — the type stays owned by P8-001. A future stateful facade (staleness evaluation, duplicate suppression, subscription) must follow the ADR-0006/0007 clock rule: no wall-clock default; any `now` must be injected, and dedup state must be caller-owned, not embedded. `PAPER_TRADING_VERIFIED` remains a TODO LIVE safety gate and LIVE stays disabled.

## ADR-0009 - Backtest Simulation Engine Is Deterministic over Explicit Inputs and Parameters

Status: Accepted

Decision: The backtest simulation engine (P7-002) is a sibling package
`backtesting/alpha_algo_backtest_engine/` — never added inside the P7-001 foundation package —
that composes the verified P7-001 types (`BacktestInput`, `SimulationClock` semantics,
single-member `BacktestTradingMode`) and the P3-002 market-data contracts, and consumes
caller-decided `OrderIntent` records. Fills, slippage, commissions, equity marks, and metrics
are pure functions of the explicit historical inputs, the intents, the cost model, and
initial capital: identical arguments yield an identical `BacktestRun` across runs and hash
seeds. The engine takes no clock, reads no wall clock, uses no randomness, generates no
UUIDs, and performs no I/O.

Fill policies are fixed, constant-named, and auditable (breaking any is a contract change,
the ADR-0008 precedent): an intent fills at the first record strictly after its `decided_at`
(same-record fills are impossible; no record after decision = UNFILLED). On ticks, MARKET
fills use the executable side — BUY at ask, SELL at bid, with `ltp` fallback only when the
leg is absent — a deliberate divergence from P8-001's MARKET-at-last paper reference, because
a backtest consuming real tick quotes pays the spread. Tick LIMIT fills at ask/bid iff the
limit crosses the quoted leg; a missing required leg means UNFILLED (the engine never falls
back to `ltp` for a limit execution). On candles, MARKET and LIMIT fills anchor exclusively on
the next record's `open_price`; intra-bar limit touch is deliberately not modeled (unknowable
on interval data, and assuming it would flatter results); `close_price` is used only for the
ex-post equity mark.

Costs: a flat `commission_per_fill` is charged on both sides of every fill; bps slippage
applies to MARKET fills only (applying it to a LIMIT fill could push a buy above its own
limit — an impossible execution). Both parameters are required at construction; a cost-free
run is the caller's explicit `Decimal("0")`. v1 performs no quantization: all arithmetic is
exact Decimal under an explicit `localcontext` precision of 28, so a third-party mutation of
the global decimal context cannot change results. The ledger matches fills FIFO with
documented cost attribution; realized P&L per completed lot is
`(exit - entry) * quantity - entry cost share - exit cost share`. Metrics are the core set
only (total return, trade count, win rate, gross profit/loss, profit factor, max drawdown,
per-period Sharpe); undefined ratios are `None` — never 0, never Infinity, never a crash —
and `BacktestMetricsError` fails loud when marked equity is non-positive. Nothing is
annualized and no benchmark alpha is computed (the engine has no calendar information).
The cash-account invariant holds: cash never goes negative (no margin, no silent quantity
capping), SELL requires sufficient position, and every intent gets exactly one outcome
(unfilled outcomes carry an explicit reason; nothing is silently dropped).

Reason: The master prompt's honesty rules (1/3/4) require results to be exact for the stated
inputs and nothing more. Determinism over explicit inputs and parameters is the only
defensible basis for hypothetical backtest results; a wall-clock, randomness, or I/O path
would make runs unreproducible, and an implicit or defaulted cost model would fabricate
precision. The sibling-package shape preserves the P7-001 foundation boundary (ADR-0006) and
lets structural tests enforce a strict import allowlist. The executable-side MARKET policy
diverges from the paper broker deliberately and is documented so no consumer conflates
backtest fills with paper fills. Skipping quantization and annualization is honest scope:
both would be fake precision without a documented tick-size/calendar model. Backtesting is
not a LIVE safety gate and implies no forward performance.

Consequences: Engine results are hypothetical reconstructions of the explicit historical
inputs under documented parameterized assumptions (slippage/commission/fill timing); they
imply no forward performance, no broker-accurate fills, and no real market-data ingestion.
There are no reports, no run persistence, no strategy runtime or signal evaluation, no
optimization/walk-forward/Monte Carlo, and no portfolio/risk analytics beyond the core
metrics. Structural tests (AST import allowlist, zero wall-clock/random/env sites,
banned-identifier surface scan, no embedded data assets, no credentials/IO/mode knobs)
enforce the boundary. `BacktestRun.mode` is structurally pinned to
`BacktestTradingMode.BACKTEST`. `.env.example` and `gates.py` are unchanged:
`LIVE_TRADING_ENABLED=false`, `GLOBAL_TRADING_HALT=true`, and all 17 LIVE safety gates
remain TODO; LIVE stays disabled and unavailable.

## ADR-0010 - Walk-Forward Testing Is a Pure Verification Harness over Explicit Windows

Status: Accepted

Decision: Walk-forward testing (P7-003) is a sibling package
`backtesting/alpha_algo_walk_forward/` - never added inside the P7-001 foundation or the
P7-002 engine packages - that composes verified P7-001 `BacktestInput` history and P7-002
`BacktestMetrics`/`DECIMAL_PRECISION` types. It is a pure harness with four responsibilities:
`build_windows(inputs, config)` (configurable train/validation/test window construction),
`run_walk_forward(*, inputs, config, window_runner)` (per-window execution via a
caller-supplied runner, with independent per-period results), `aggregate_periods(periods)`
(cross-window aggregation), and `assess_overfitting(periods, aggregate)` (fixed-threshold
overfitting-risk flags). The harness takes no clock, reads no wall clock, uses no
randomness, performs no I/O, embeds no data, generates no UUIDs, and persists nothing -
results are in-memory and caller-owned; the caller persists if and only if it chooses to.

Window policy (fixed, constant-named, auditable; breaking any is a contract change, the
ADR-0008/0009 precedent): windows are counted in records, never calendar time (the harness
has no calendar model, the ADR-0009 precedent). `WalkForwardConfig` takes exactly
`training_records`, `validation_records`, `test_records`, and `step_records` - all required
exact `int` values with no defaults, all at least 1, and `step_records >= test_records`
enforced at construction so out-of-sample windows never overlap across periods. Within a
window, train, validation, and test slices are contiguous, strictly ordered, and strictly
disjoint (test always after validation always after train); each slice is derived from
record indices and record timestamps (`WindowSlice` is half-open `[start_index, end_index)`
with `start_timestamp`/`end_timestamp` taken from the slice's first/last record), never
from a wall clock; a period never observes records outside its slice, so no look-ahead is
possible by construction. A trailing remainder shorter than one step is unused, never
truncated, and always visible: every `WalkForwardResult` carries mandatory coverage
metadata (`record_count`, `covered_records`, `uncovered_records`) with
`covered_records + uncovered_records == record_count` (Rule 15 - unused data is visible,
never silently deleted); history shorter than one full window fails loud with a typed
error. Per-period results are stored independently, never folded into one blended run:
each `WindowBacktestResult` carries its `window` (identity, harness-validated) plus
`is_metrics` - a backtest over exactly the window's in-sample records (train ∪ validation)
- and `oos_metrics` - a backtest over exactly the test records - both engine
`BacktestMetrics`, with `metadata` echoed only, never read.

Runner contract: `run_walk_forward` accepts `window_runner: Callable[[WalkForwardWindow],
WindowBacktestResult]`, supplied by the caller, and invokes it exactly once per window in
ascending window-index order. The harness validates what is checkable - the returned type,
the window identity (the result must echo the exact window it was handed), the carried
metric values (Decimal finiteness and documented ranges), and the call order - and rejects
malformed results fail loud. Any runner exception aborts the walk-forward immediately and
propagates unchanged; no partial aggregate is produced and nothing is fabricated
(`RUNNER_FAILURE_POLICY`). The harness itself performs no strategy fitting, no signal
generation, and no parameter optimization; if the caller's runner fits parameters on
in-sample slices and evaluates on the test slice, that fitting is entirely the caller's
responsibility and lives outside this package. Determinism of the overall run is a caller
commitment: the harness guarantees its own window math, aggregation, and assessment are
pure functions of their inputs, and the caller must supply a runner that is likewise pure
and deterministic for the run to be reproducible across runs and hash seeds.

Aggregation and overfitting scope: aggregation covers the core P7-002 metric set
(`AGGREGATED_METRICS`: total_return, win_rate, profit_factor, max_drawdown, sharpe_ratio,
trade_count) as cross-window mean/median/population-standard-deviation per metric, all in
exact Decimal under a fixed `localcontext` of `DECIMAL_PRECISION` (28, imported from the
engine - no `math`, no `statistics`, no float path, consistent with ADR-0009). IS-vs-OOS
degradation is computed for the five scale-free metrics only
(`direction * (is_mean - oos_mean) / abs(is_mean)`, `max_drawdown` lower-is-better);
`trade_count` degradation is structurally `None` (IS and OOS windows cover unequal record
counts); undefined ratios are `None` - never 0, never Infinity, never a crash. Nothing is
annualized (the harness has no calendar information) and no benchmark alpha is computed.
Overfitting assessment emits eight fixed, constant-named, documented threshold flags
(per-metric degradation beyond `DEGRADATION_THRESHOLD` (0.5), mean OOS trades below
`LOW_TRADE_COUNT_THRESHOLD` (30), a single OOS window return beyond
`MAX_RETURN_SANITY_BOUND` (100), OOS total-return coefficient of variation beyond
`DEPENDENCY_CV_THRESHOLD` (1.0)) and a composite `OverfittingRisk` of LOW/MEDIUM/HIGH (the
highest triggered severity; zero OOS trades or fewer than `MIN_PERIODS_FOR_ASSESSMENT` (3)
periods cap at LOW with explicit reasons, with flags always computed and reported so the
cap is never mistaken for "flags cleared"). The flags are informational only: they
auto-reject nothing and block nothing - walk-forward cannot gate trading, and LIVE is
already disabled independently.

Reason: The master prompt's honesty rules (1/3/4) require walk-forward results to be exact
for the stated inputs and assumptions and nothing more. Walk-forward is the natural next
Phase 7 deliverable: P7-001/P7-002 are VERIFIED, the Phase 7 remainder (reports, run
persistence) is not yet viable, and P8-003 (paper persistence) is blocked by the absence of
docker/PostgreSQL on the host - walk-forward completes the backtesting story with zero new
operational dependencies. The sibling-package shape preserves the P7-001/P7-002 boundaries
(their allowlists do not include `alpha_algo_walk_forward`, so the dependency direction is
structurally enforced) and lets structural tests enforce the same strict import allowlist,
zero wall-clock/random/env/io sites, banned-identifier surface scan, and no-embedded-data
invariants as ADR-0009. Delegating fitting to a caller-supplied runner is the only honest
division of labor: the engine structurally bans strategy runtime, so a harness that fit
strategies itself would violate ADR-0009; a runner contract keeps the harness pure while
making the caller's fitting role explicit and auditable. Coverage metadata is the honest
resolution of trailing data: unused records are visible, never silently dropped (Rule 15).
No persistence is honest scope: run persistence remains an unstarted Phase 7 item, and
in-memory results keep the package free of I/O and DB surfaces. Fixed-threshold
informational flags (no auto-reject) follow rule 1: a research aid must not masquerade as
an automated trading decision, and any future automated rejection must be a new ADR, not a
knob.

Consequences: Walk-forward results are hypothetical reconstructions of the explicit
historical inputs under documented window, cost, and runner assumptions; they are not
evidence of profitability and imply no forward performance. The package contains no
strategy runtime, no optimizer, no reports, no persistence, no network, no environment
access, and no randomness; it defines no trading modes (mode isolation is inherited - the
harness composes engine types whose `BacktestRun.mode` is BACKTEST-pinned, ADR-0009).
Aggregation is exact Decimal; all thresholds are fixed named constants.
`run_walk_forward` determinism depends on the caller's runner - documented as a caller
commitment, with the harness validating result shape, identity, and carried values only.
`.env.example` and `gates.py` are unchanged: `LIVE_TRADING_ENABLED=false`,
`GLOBAL_TRADING_HALT=true`, and all 17 LIVE safety gates remain TODO; LIVE stays disabled
and unavailable. ADR-0009's "no optimization/walk-forward/Monte Carlo" clause is
superseded for walk-forward by this record; the engine package itself remains unchanged
and still contains none of those surfaces.

## ADR-0011 - Backtest Performance Reports Compose the Verified Engine into an Immutable, Honesty-Framed Report

Status: Accepted

Decision: Backtest performance reports (P7-004) are a sibling package
`backtesting/alpha_algo_backtest_reports/` - never added inside the P7-001 foundation, the
P7-002 engine, or the P7-003 walk-forward packages - that composes verified P7-001/P7-002
types (`BacktestRun`, `BacktestMetrics`, `DECIMAL_PRECISION`, `BacktestEngineError`) into a
single immutable, honesty-framed `BacktestReport`. The report layer computes only what is
derivable from `BacktestRun` + `BacktestMetrics` + the fill-sequence-to-timestamp join:
trade reconstruction (`TradeReconstruction`), extended trade statistics
(`TradeStatistics`), non-annualized risk ratios (`RiskMetrics`: Sortino and Calmar), a
drawdown curve, per-period return buckets (daily/monthly/yearly), and a fixed
`REPORT_LIMITATIONS` disclosure. It takes no clock, reads no wall clock, uses no
randomness, performs no I/O, embeds no data, generates no UUIDs, and persists nothing - a
report is an in-memory value the caller owns.

Honest-scope contract (fixed, constant-named, auditable): the report layer computes only
what is derivable from the engine's existing records. Because the v1 engine is
single-position, long-only, and records no symbol, signal, reason, stop/target, MFE/MAE,
regime, or short-side, those fields are `None` (or documented not-computable) - never
fabricated. Trade reconstruction joins fill sequences to `FillRecord` timestamps and
prices; `entry_label`/`exit_label` surface `OrderIntent.label` only (the structurally
banned "signal" token is not a field). `net_pnl` is the engine's `realized_pnl`; `fees` is
`entry_cost + exit_cost`; `gross_pnl = net_pnl + fees` (self-consistent exact);
`entry_slippage = entry_fill.slippage_per_share * quantity`; `exit_slippage`/`slippage`
are exact only when every exit fill sequence is exclusive to one trade (else `None`).
Statistics: `recovery_factor = net_profit / currency_max_drawdown` (`None` when
`trade_count == 0` or the dollar drawdown is zero); `average_trade_duration` is the mean
over trades of (max exit fill time - entry fill time); undefined ratios are `None` - never
0, never Infinity, never a crash. Risk: Sortino is
`(mean return - rf) / downside_deviation` with downside deviation the population
semi-deviation against a zero target; Calmar is non-annualized `total_return / max_drawdown`.
All arithmetic is exact Decimal under a fixed `localcontext` of 28 (no `math`, no
`statistics`, no float path); every public docstring carries the "hypothetical" and
"not evidence of profitability" framing.

Reason: The master prompt's honesty rules (1/3/4) require reports to be exact for the
stated inputs and nothing more. Reports are the natural next Phase 7 deliverable after the
verified engine and walk-forward harness, and they need zero operational dependencies
(unlike run persistence, which is blocked by the absence of docker/PostgreSQL on the
host). The sibling-package shape preserves the P7-001/P7-002/P7-003 boundaries and lets
structural tests enforce the same import allowlist (only `alpha_algo_backtesting` +
`alpha_algo_backtest_engine`), zero wall-clock/random/env/io sites, banned-identifier
surface scan, no-embedded-data, and docstring-honesty invariants as ADR-0009/0010.
Reconstructing only what the engine records - and returning `None` for everything else -
is the honest resolution: fabricating symbol/signal/reason/stop/target/MFE/MAE/regime
would be fake precision (rules 1/3). No persistence is honest scope: a report is a pure
value; the caller decides whether to archive it.

Consequences: Report results are hypothetical reconstructions of the explicit historical
inputs under documented engine (fill/cost) and report (reconstruction/statistics/risk)
assumptions; they are not evidence of profitability and imply no forward performance. The
package contains no strategy runtime, no optimizer, no persistence, no network, no
environment access, no randomness, and defines no trading modes (it composes engine types
whose `BacktestRun.mode` is BACKTEST-pinned). `.env.example` and `gates.py` are unchanged:
`LIVE_TRADING_ENABLED=false`, `GLOBAL_TRADING_HALT=true`, and all 17 LIVE safety gates
remain TODO; LIVE stays disabled and unavailable. ADR-0009's "no reports" consequence
clause is superseded for reports by this record; the engine package itself remains
unchanged and still contains no report surface.

