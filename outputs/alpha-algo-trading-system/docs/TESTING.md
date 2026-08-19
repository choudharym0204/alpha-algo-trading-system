# Testing Architecture

This document is a proposal for the full testing architecture. The unit-test layer is implemented for the verified foundation tasks (Phase 1 through Phase 8 foundations, including the deterministic backtesting foundation, the backtest simulation engine, the backtest performance report layer, the paper trading foundation, the paper market-data feed, and the walk-forward testing harness). Integration, safety, and end-to-end layers remain planned.

## Test Layers

Unit tests:

- Indicators.
- Strategy lifecycle.
- Signal generation.
- Risk rules.
- Position calculations.
- P&L calculations.
- Order validation.
- Backtesting deterministic time advancement (simulation clock).
- Backtesting mode isolation (BACKTEST separated from PAPER/LIVE).
- Backtesting explicit historical input validation and canonical manifest stability.
- Backtesting no-live/broker-access structural checks (banned imports and surface identifiers).
- Paper broker adapter Protocol conformance (async surface, capabilities with live/cancel disabled, PAPER-only mode enforcement, connect ignores secrets and never authenticates).
- Paper fill policy determinism (MARKET at injected last, LIMIT executable-or-reject against injected bid/ask, STOP/STOP_LIMIT rejected).
- Paper event round trips through the execution state machine (ACK then FILL to terminal FILLED with exact-quantity completion; REJECTED to terminal REJECTED).
- Paper idempotency (duplicate client_order_id returns stored response with no new events; conflicting payload raises).
- Paper positions (PAPER-labeled aggregation, Decimal-quantized average price, per-account/instrument separation).
- Paper no-live/broker-access structural checks (AST import allowlist, zero wall-clock/random/env sites, no embedded assets).
- Paper market-data feed conversion (pure, stateless MarketTick -> PaperReferencePrice mapping: field mapping with missing legs to None, no leg synthesis, exact Decimal precision, reference_at from tick.timestamp, never the epoch default).
- Paper market-data feed fail-loud validation (typed PaperFeedError for non-tick/candle input, bid > ask, last outside the spread, non-Decimal, non-finite via model_construct bypass, non-positive prices, naive timestamps).
- Paper market-data feed provenance (TickProvenance with (source_broker, source_sequence) P3-003 dedup key, tz-aware timestamps, frozen/immutable, deterministic).
- Paper market-data feed structural checks (AST import allowlist, zero wall-clock/random/env sites, banned-identifier surface scan, no embedded data assets, no PaperReferencePrice re-export).
- Paper feed-to-broker round trips (feed-built reference map drives PaperBrokerAdapter: MARKET fill at the mapped last, LIMIT honest reject on missing ask, absent-instrument reject) with zero adapter changes.
- Backtest engine deterministic fills (MARKET at executable tick side with ltp fallback, LIMIT at crossed ask/bid with missing-leg unfilled, candle MARKET/LIMIT at next open only, next-record-strictly-after timing).
- Backtest engine costs (flat commission, MARKET-only bps slippage, Decimal exactness under localcontext precision, negative/oversized parameter rejection).
- Backtest engine ledger and metrics (FIFO realized P&L with cost attribution; core metrics with None for undefined ratios; BacktestMetricsError on non-positive marked equity).
- Backtest engine fail-loud validation (non-Decimal/non-finite/non-positive quantities, naive decision times, unsupported order types, unsorted intents).
- Backtest engine determinism (identical input + parameters across runs and PYTHONHASHSEED values; wall-clock/random never consulted).
- Backtest engine structural checks (AST import allowlist, zero wall-clock/random/env sites, banned-identifier surface scan, no embedded data assets, no credentials/IO/mode knobs).
- Walk-forward window construction (count-based uniform rolling windows over explicit history; strictly forward, contiguous, and strictly disjoint within a window; train/val/test ordering; step_records >= test_records so OOS windows never overlap across periods; required-no-defaults config; too-short history and empty/oversized config fail-loud errors; boundary timestamps derived from explicit record timestamps only; trailing remainder unused, never truncated, visible in coverage metadata).
- Walk-forward no-look-ahead (a period's slices never contain records beyond their ranges; OOS evaluation can never observe future records).
- Walk-forward per-period independence (each WindowBacktestResult carries its window identity and IS/OOS metric pairs; periods stored independently, ascending and gap-free, never blended).
- Walk-forward aggregation math (cross-window mean/median/population-stdev per core metric and IS-vs-OOS degradation on the five scale-free metrics, exact Decimal under fixed localcontext, no float path; trade_count degradation structurally None; nothing annualized).
- Walk-forward overfitting flags (fixed-threshold boundaries 0.5/30/100/1.0, LOW/MEDIUM/HIGH composite, informational-only - nothing auto-rejected, nothing gated; degenerate inputs cap at LOW with explicit reasons).
- Walk-forward runner-contract validation (typed result shape and window identity enforced, carried metric values validated, malformed/foreign results rejected fail loud; runner exceptions propagate unchanged with no partial aggregate; determinism of the whole run documented as a caller commitment).
- Walk-forward determinism (identical inputs + config + runner across runs and PYTHONHASHSEED values; wall-clock/random never consulted).
- Walk-forward structural checks (AST import allowlist, zero wall-clock/random/env/io sites, banned-identifier surface scan, no embedded data assets, no credentials/IO/mode knobs, no strategy/executor surface, no trading-mode classes).
- Backtest report trade reconstruction (fill-sequence join to timestamps/prices; net_pnl == realized_pnl, fees == entry_cost+exit_cost, gross_pnl == net_pnl+fees, entry_slippage == slippage_per_share*quantity, exit_slippage exact only when each exit fill sequence is exclusive to one trade; symbol/signal/reason/stop/target/MFE/MAE/regime None - never fabricated).
- Backtest report statistics (loss rate, expectancy, average win/loss, risk/reward, largest win/loss, max consecutive wins/losses, average trade duration via fill-sequence join, recovery factor net_profit/currency-max-drawdown, total fees/slippage; undefined ratios None - never 0, never Infinity; recovery factor None when trade_count==0).
- Backtest report risk ratios (Sortino = (mean-rf)/downside with population semi-deviation vs a zero target; Calmar = non-annualized total_return/max_drawdown; both None on a zero denominator; non-positive marked equity raises BacktestReportError).
- Backtest report curves and buckets (peak-resetting drawdown ratio + dollar amount; daily/monthly/yearly return buckets; single-point bucket -> None return; invalid granularity fails loud).
- Backtest report determinism (identical run across runs and PYTHONHASHSEED values; frozen dataclasses; wall-clock/random never consulted; no cross-run state).
- Backtest report structural checks (AST import allowlist of only alpha_algo_backtesting + alpha_algo_backtest_engine, zero wall-clock/random/env/io sites, banned-identifier surface scan, no embedded data assets, no credentials/IO/mode knobs, no live/persistence/strategy service imports, public docstrings carry "hypothetical" AND "not evidence of profitability").

Integration tests:

- PostgreSQL persistence.
- TimescaleDB hypertables.
- Redis transient state.
- Broker adapter contract tests.
- Market data pipeline.
- Execution pipeline.

Trading safety tests:

- Duplicate orders.
- Partial fills.
- Rejected orders.
- Broker timeout.
- WebSocket disconnect.
- Stale market data.
- Daily loss breach.
- Position limit breach.
- Unexpected position.
- Engine restart.
- Redis failure.
- Database failure.
- Risk engine failure.

End-to-end tests:

```text
Login
  -> Dashboard
  -> Strategy
  -> Signal
  -> Risk
  -> Order
  -> Fill
  -> Position
  -> P&L
```

## Verification Policy

A task is complete only when it is:

```text
IMPLEMENTED
TESTED
VERIFIED
DOCUMENTED
```

Live trading cannot be enabled from unit tests alone. It requires integration, safety, reconciliation, monitoring, and operational verification.
