# Phase 3 Review — Market-Data Architecture

Reviewed the Phase 3 market-data files plus the TimescaleDB migration, the
runtime config (`apps/api/alpha_algo_api/config.py`), the shared DB models, and
the broker adapter contract (order-side context). Findings are limited to real
correctness/coupling/isolation/architectural issues, ordered by severity.

---

## MAJOR issues

### M1. Persistence is synchronous and blocks the async consumer loop
- **Location:** `services/market_data/alpha_algo_market_data/engine.py:153-176`
  (`_persist_tick`/`_persist_candle`) and `engine.py:180` (`run` loop), with
  `repository.py:64-79`.
- **Why it matters:** The engine advertises an "async bounded queue + consumer
  loop" for backpressure, but every accepted event does a **synchronous**
  `session.add()` + `session.commit()` (network I/O to PostgreSQL) inline in
  `ingest_raw`, which is invoked directly from the async `run()` loop. One slow
  commit stalls the event loop, so the queue fills and the backpressure path
  (drop) kicks in even though the bottleneck is the DB write, not the consumer.
  The async design is effectively defeated.
- **Fix:** Move persistence off the event loop — run the repository in a thread
  executor (`await asyncio.to_thread(...)`) or, better, push into a dedicated
  writer coroutine/thread with its own batch queue; alternatively adopt
  `sqlalchemy.ext.asyncio`. Do not block the `run()` loop on DB commits.

### M2. One session + one commit per event; the batch methods are dead code
- **Location:** `repository.py:64-79` (`_commit_one`/`persist_tick`/
  `persist_candle`) vs `repository.py:81-96` (`persist_tick_batch`/
  `persist_candle_batch`), which the engine never calls.
- **Why it matters:** Market data can be tens of thousands of events/sec. A new
  session + `commit` per tick/candle is a severe throughput/latency problem
  (connection checkout + round-trip per row) and will overwhelm the pool. The
  batch APIs exist but are never wired, so the intended batching path is dead.
- **Fix:** Have the engine (or a writer task) accumulate accepted ticks/candles
  and flush via `persist_tick_batch`/`persist_candle_batch` on a size/time
  threshold, or use a single session-per-batch with `add_all`.

### M3. A malformed candle timeframe crashes the whole pipeline (uncaught `ValueError`)
- **Location:** `normalization.py:99-101`
  (`timeframe = CandleTimeframe(timeframe)`) vs `engine.py:95-101`
  (`ingest_raw` only catches `RawEventValidationError`) and `engine.py:180-194`
  (`run` has no `except` around `ingest_raw`).
- **Why it matters:** `validate_raw_event` checks only that the `timeframe`
  *key* is present, not that its *value* is valid. `CandleTimeframe("banana")`
  raises `ValueError` (Python `StrEnum`), which is **not** a
  `RawEventValidationError`, so it is not caught by `ingest_raw` and propagates
  out of the `run()` `while` loop, terminating the consumer task permanently.
  One bad upstream event kills the entire feed.
- **Fix:** Wrap the timeframe coercion in `try/except ValueError` and raise
  `RawEventValidationError`, and/or broaden `ingest_raw` to also catch
  `ValueError`/`TypeError` from normalization and classify them as REJECTED.
  Add a defensive `except Exception` in the `run()` loop so a single bad event
  can never kill the consumer.

### M4. A raising consumer kills the pipeline for all other consumers
- **Location:** `engine.py:141-146` (`for consumer in self._tick_consumers:
  consumer(tick)`) and `engine.py:148-151` (candle consumers).
- **Why it matters:** Fan-out is un-isolated. If any registered consumer (e.g.,
  a Strategy Engine handler, Phase 4) raises, the exception propagates through
  `ingest_raw` and out of `run()`, taking down ingestion and every other
  consumer. A single bad strategy must not stop the market-data pipeline.
- **Fix:** Catch per-consumer exceptions, log, increment a
  `consumer_failures` metric, and continue to the next consumer (and still
  persist).

### M5. No composition root: the pipeline is never assembled end-to-end
- **Location:** No module wires it. `provider.py` (Protocol),
  `connection.py` (`ProviderConnectionManager`), `engine.py`, `repository.py`,
  and `config.py:88-104` (`market_data_*` settings) all exist, but nothing:
  (a) builds a concrete provider from `market_data_provider`, (b) calls
  `provider.set_event_handler(engine.enqueue)`, (c) starts `engine.run()` as a
  task, (d) subscribes to `market_data_symbol_list`, or (e) constructs the
  `MarketDataRepository` from `database_url`.
- **Why it matters:** The "Provider → Adapter → Raw Event → … → Engine →
  Consumers → TimescaleDB" pipeline is real only as disconnected components.
  `ProviderConnectionManager` handles connect/reconnect/heartbeat but is never
  driven, never subscribes, and never bridges provider events into the engine
  queue. `Settings.market_data_*` values are validated but consumed by nothing.
  The streaming architecture cannot actually run.
- **Fix:** Add a service/composition layer (e.g., a `MarketDataService` or app
  factory) that reads `Settings`, constructs the provider + engine +
  repository + connection manager, wires the event handler to
  `engine.enqueue`, runs the consumer task, and subscribes to configured
  symbols. This is the missing integration seam that makes M1/M2 and config
  actually exercised.

### M6. Historical fetch "chunking" is misnamed and pathological; true pagination is absent
- **Location:** `historical.py:53-63` (`_chunked_ranges`), `historical.py:88-123`
  (`fetch_candles`), `historical.py:124-147` (`fetch_ticks`), and the request
  types in `provider.py:56-74` (no cursor/offset/continuation token).
- **Why it matters:**
  - `chunk_size` (default 1000, from `market_data_historical_chunk_size`) is
    passed as the **number of time windows**, not the candle count per window.
    A 1-day range of 1-minute candles (~1440 rows) is split into **~1000
    provider round-trips**, each returning 1-2 rows — roughly 1000x more
    requests than necessary.
  - `HistoricalCandlesRequest`/`HistoricalTicksRequest` have **no pagination
    field** (no `offset`, `cursor`, `page_token`). If any single window holds
    more than `limit` (`max_candles`, default 10000) rows, the surplus is
    **silently truncated** — there is no loop to fetch the next page and no
    "truncated" signal.
  - `fetch_ticks` performs a **single** request capped at `self._max_candles`
    (the *candle* max is reused for ticks) with no chunking/pagination at all.
  - The docstring claims "pagination/chunking" but only bounded fetch + retry +
    validation are actually implemented.
- **Fix:** Add an explicit pagination token/offset to the request types and
  loop until the provider signals exhaustion; make `chunk_size` mean "rows per
  page" (or derive windows from `limit`); give `fetch_ticks` its own `max_ticks`
  and a chunking path; and expose a truncation indicator instead of silently
  clipping.

---

## MINOR issues

### m1. Duplicate/unique-violation is not reconciled with the DB (candles + cross-process ticks)
- **Location:** `engine.py:147-151` (`_ingest_candle` skips duplicate detection
  and freshness); `market_data.py` unique constraints
  `uq_ticks_source_broker_sequence_timestamp` and
  `uq_candles_instrument_timeframe_start`.
- **Why it matters:** Candle duplicates are not deduped in memory, and any
  duplicate (replayed candle, or a tick that duplicates a row written by
  another process/after a restart) hits the unique constraint, raising
  `IntegrityError`, which `_persist_*` swallows and counts as
  `persistence_failures` (spamming warnings and corrupting the duplicate
  metric) instead of being classified as DUPLICATE.
- **Fix:** Dedup candles in memory (key = `instrument_id`+`timeframe`+
  `candle_start`), and/or persist with `INSERT … ON CONFLICT DO NOTHING` so
  unique violations are idempotent and counted as duplicates, not failures.

### m2. In-memory dedup key differs from the DB uniqueness key
- **Location:** `safety.py:66-73` — key `(source_broker, source_sequence)`; vs
  `market_data.py` model — unique on
  `(source_broker, source_sequence, timestamp)`.
- **Why it matters:** If a provider's `source_sequence` resets across sessions
  or days (common), the in-memory detector treats a tick with a reused
  sequence but a *different* timestamp as a duplicate and drops real data,
  while the DB would have accepted it. The two layers disagree on identity.
- **Fix:** Align the detector key with the persistence contract (include
  `timestamp`), or document/guarantee that `source_sequence` is globally unique
  per broker and make the DB constraint match.

### m3. Contract↔DB nullability mismatch
- **Location:** `contracts/market_data.py` — `source_sequence`
  (`min_length=1`) and `source_broker` are required; `db/models/market_data.py`
  — `Tick.source_sequence` (`Mapped[str | None]`) and `Candle.source_broker`
  (`Mapped[str | None]`) are nullable.
- **Why it matters:** The DB permits states the domain contract forbids, so the
  canonical invariant (every tick has a broker + sequence) is not enforced at
  the persistence boundary. Not a runtime bug today (the repository always
  supplies values), but it weakens the contract.
- **Fix:** Make the ORM columns non-nullable to mirror the contract (or relax
  the contract if nulls are genuinely supported).

### m4. Public `normalize_tick`/`normalize_candle` raise `KeyError` on missing keys
- **Location:** `normalization.py:68-95` (direct `payload["instrument_id"]`,
  `payload["ltp"]`, etc.).
- **Why it matters:** The engine path is safe because `validate_raw_event` runs
  first, but `normalize*` are exported in `__init__.py` and used by callers
  (e.g., tests, future adapters) that may skip validation — then a missing key
  surfaces as a bare `KeyError` instead of a `RawEventValidationError`,
  breaking the "normalization never raises raw exceptions" contract.
- **Fix:** Use `.get()` + explicit missing-key errors (raise
  `RawEventValidationError`), or document that these functions require prior
  validation.

### m5. Backpressure drop accounting is inconsistent under `drop_oldest`
- **Location:** `backpressure.py:56-66` (`drop_oldest` does `get_nowait()`
  without `task_done()`); `engine.py:173-177` (`enqueue` increments
  `dropped_events` only when `put_nowait` returns `False`).
- **Why it matters:** Under `drop_oldest` an item is evicted but `task_done()`
  is never called (latent `join()` deadlock if it is ever used), and the
  engine's `dropped_events` metric undercounts because `put_nowait` returns
  `True` even though the oldest item was discarded.
- **Fix:** Call `task_done()` for the evicted item (or track it) and surface
  evictions to the engine metric regardless of return value.

---

## Requirements assessment

1. **Provider isolated behind a Protocol** — PASS. `MarketDataProvider` is a
   `Protocol`; the engine consumes only provider-agnostic `RawMarketEvent`;
   the sole concrete provider (`FakeMarketDataProvider`) is a test double and
   no strategy code references a concrete provider.
2. **Streaming pipeline stage order** — PARTIAL. The stages exist in the
   correct order, but there is no composition root (M5), the pipeline can be
   killed by a bad timeframe (M3) or a raising consumer (M4), and persistence
   blocks the loop (M1).
3. **Normalization reuses existing contracts** — PASS. Produces the existing
   `MarketTick`/`MarketCandle` from `alpha_algo_contracts` unchanged.
4. **TimescaleDB persistence, no Redis source of truth** — PASS. Repository
   writes `Tick`/`Candle` ORM models; Redis is not referenced anywhere in the
   market-data path.
5. **Historical bounded fetch/pagination/chunking/retry/validation** — PARTIAL.
   Bounded fetch, retry (transient-only), and input validation are present; but
   pagination is absent and chunking is misnamed/pathological (M6).
6. **Config architecture, no committed secrets** — PASS. Provider/market-data
   settings live in the runtime `Settings` (pydantic-settings) with
   fail-closed production validation; `.env.example` contains only placeholders.
   (Config is defined but not yet wired into the service — see M5.)

---

## Verdict
REQUEST_CHANGES — six MAJOR issues (blocking synchronous persistence, per-event commits, pipeline-crashing normalization/consumer paths, missing composition root, and broken historical pagination) must be resolved before the market-data architecture can be considered production-ready.
