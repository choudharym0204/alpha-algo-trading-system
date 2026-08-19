# Phase 3 Review — Runtime / Reconnect Behavior

Scope: `services/market_data/alpha_algo_market_data/{connection,provider,backpressure,engine,fake_provider}.py` plus the runtime-path dependencies they invoke (`safety.py`, `repository.py`, `metrics.py`), and the unit tests in `tests/unit/test_market_data_{provider,streaming}.py`.

## Findings

### 1. MAJOR — `reconnect()` bypasses `connect_timeout`; a hung connect attempt blocks forever
- **Location:** `connection.py` — `ProviderConnectionManager.reconnect()` (~L144) → `Reconnector.connect()` (~L53)
- **Why it matters:** `ProviderConnectionManager.connect()` wraps the provider call in `asyncio.wait_for(..., timeout=self._connect_timeout)`, but `reconnect()` passes `self._provider.connect` directly into `Reconnector.connect()`, which does `await connect_fn()` with **no per-attempt timeout**. The exponential backoff only caps the *delay between* attempts, not the duration of an attempt. If a real provider's `connect()` stalls (TCP connect to a dead endpoint, DNS hang, TLS negotiation that never returns), a single reconnect attempt blocks the event loop indefinitely — the whole reconnect sequence hangs and never reaches its bounded `max_attempts`/final `FAILED` state. This directly violates "reconnect attempts are bounded" and "no dead probes that hang forever."
- **Fix:** Give `Reconnector` a `timeout` parameter and apply `asyncio.wait_for(connect_fn(), timeout=...)` around each attempt (propagate `self._connect_timeout` from `ProviderConnectionManager.reconnect`). Optionally also cap the total reconnect wall-clock time.

### 2. MAJOR — Heartbeat / dead-connection detection is never driven at runtime (no watchdog)
- **Location:** `connection.py` (`HeartbeatMonitor`, `ProviderConnectionManager.is_alive/record_heartbeat`), `metrics.py` (`heartbeat_failures`)
- **Why it matters:** The heartbeat monitor is constructed but nothing ever polls it. There is no background task/loop that periodically calls `is_alive()` and triggers `reconnect()` on a dead connection. `metrics.heartbeat_failures` is declared but never incremented anywhere in the codebase. `record_heartbeat()` is only ever called via `_heartbeat.reset()` inside `connect()`/`reconnect()` — never by a stream/protocol signaling a live heartbeat. Consequently a provider that silently stops emitting (half-open socket, broker disconnect without FIN) is **never detected and never reconnected**; the "timeout + disconnect detection" portion of this subsystem is dead code. This is a structural gap for the runtime/reconnect dimension.
- **Fix:** Add a watchdog task (or heartbeat loop) that, while `state == CONNECTED`, awaits `is_alive()` on the heartbeat timeout cadence and, on death, increments `heartbeat_failures` and calls `reconnect()`. Wire a real heartbeat source into `record_heartbeat()` (e.g., the provider's keepalive/ping callback).

### 3. MINOR — `is_alive()` returns `True` when no heartbeat has ever arrived
- **Location:** `connection.py` — `HeartbeatMonitor.is_alive()` (~L84)
- **Why it matters:** `if self._last_heartbeat is None: return True` means a freshly connected provider is considered alive indefinitely until its first heartbeat is recorded. Combined with finding #2, if heartbeat delivery is never wired, a connection can never transition to "dead" at all. Even once a watchdog exists, a connect-then-silence scenario would be treated as healthy forever.
- **Fix:** Treat the connect time as the initial heartbeat baseline (seed `_last_heartbeat` at `connect()`/`reset()` with a timestamp, or store the time the connection became CONNECTED) so a provider that never sends a heartbeat is flagged dead after `heartbeat_timeout_seconds`.

### 4. MINOR — Reconnect does not tear down a stale/partial connection first
- **Location:** `connection.py` — `ProviderConnectionManager.reconnect()` (~L144)
- **Why it matters:** `reconnect()` retries `provider.connect()` without first calling `provider.disconnect()`. For a real provider whose prior connection is half-open (connect succeeded earlier but the transport died), re-invoking `connect()` can leak the old socket/connection or leave the SDK in a conflicting state. `FakeMarketDataProvider` masks this because `connect()` only flips booleans, so the tests never exercise the real reconnection semantics.
- **Fix:** Before retrying, best-effort `await self._provider.disconnect()` (or have `reconnect()` route through a `disconnect → connect` sequence), and document the provider contract that `connect()` must be idempotent/re-entrant.

### 5. MINOR — `connect()` increments `reconnect_failures` on an initial connect failure
- **Location:** `connection.py` — `ProviderConnectionManager.connect()` (~L129)
- **Why it matters:** An initial connect failure is not a reconnect, yet the code does `self._metrics.reconnect_failures += 1`. This pollutes the reconnect-failure counter (and any alerting built on it) with ordinary first-connect errors. Semantically misleading observability.
- **Fix:** Add a dedicated `connect_failures` metric (or skip incrementing) in `connect()`, and reserve `reconnect_failures` for the `reconnect()` path only.

### 6. MINOR — Drops are counted but never logged ("never silently dropped" is only half true)
- **Location:** `backpressure.py` — `BoundedQueue.put_nowait()` (~L49–76); `engine.py` — `MarketDataEngine.enqueue()` (~L169)
- **Why it matters:** Both `BoundedQueue.dropped_count` and `metrics.dropped_events` are incremented, but **no log record is emitted** on the drop path. The module docstring claims drops are "surfaced through metrics/logs", and review requirement #4 says drops must be counted *and* logged. At runtime, a burst that fills the queue drops events with zero immediate signal unless someone is actively polling `metrics.as_dict()` — effectively silent from an operator's perspective.
- **Fix:** Emit a throttled/rate-limited `logger.warning` (or `logger.info`) on each drop, including the drop policy and current queue size, e.g. in `enqueue()` when `accepted is False`.

### 7. MINOR — `drop_oldest` breaks `asyncio.Queue` `task_done`/`join` accounting
- **Location:** `backpressure.py` — `BoundedQueue.put_nowait()` drop_oldest branch (~L63–73)
- **Why it matters:** In the `drop_oldest` path, the oldest item is removed with `self._queue.get_nowait()` but `task_done()` is **never called** for it. `asyncio.Queue` increments `_unfinished_tasks` on `put` and decrements it only on `task_done()`; `get_nowait()` does not decrement it. Every dropped-oldest item therefore leaves `_unfinished_tasks` permanently inflated, so any future `queue.join()` (the underlying queue supports it) would hang forever, and the unfinished-tasks counter grows without bound over a long run.
- **Fix:** Pair the `get_nowait()` in the drop_oldest branch with a `task_done()` call (inside the `QueueEmpty` guard) so accounting stays balanced.

### 8. MINOR — `DuplicateTickDetector` uses an unbounded `set` → unbounded memory growth in the ingest path
- **Location:** `safety.py` — `DuplicateTickDetector` (~L73–84), reachable via `engine.ingest_raw → _ingest_tick → is_duplicate`
- **Why it matters:** `_seen_sequences` is a plain `set` with no eviction, TTL, or cap. Every accepted tick inserts a `(source_broker, source_sequence)` key that is retained for the lifetime of the process. A long-running market-data service ingesting continuous ticks will grow this set without bound — a direct violation of review requirement #5 ("no unbounded sets/lists/queues in the runtime path"). This is a guaranteed slow leak in production, not a theoretical one.
- **Fix:** Replace the unbounded set with a bounded, time-windowed structure — e.g. a capped LRU (`cachetools.TTLCache` / `LRUCache`), a fixed-size `deque(maxlen=N)` of recent keys, or a periodic pruning of sequences older than some horizon.

### 9. MINOR — Blocking synchronous DB I/O runs inside the async consumer loop
- **Location:** `engine.py` — `run()` (~L176) → `ingest_raw` → `_persist_tick`/`_persist_candle` (~L149–165) → `repository.persist_*` (`repository.py`, synchronous `session.commit()`)
- **Why it matters:** The consumer loop calls `self.ingest_raw(event)` synchronously, which performs synchronous SQLAlchemy `session.commit()` directly on the event loop. A slow/hung TimescaleDB will block the entire loop — stalling queue consumption, delaying `stop()` from taking effect, and starving any heartbeat/reconnect coroutines running on the same loop (directly relevant to this review's runtime/reconnect focus). This is the async-correctness analog of "blocking sleep in an async loop" (requirement #6).
- **Fix:** Offload persistence with `await asyncio.to_thread(...)` (or a dedicated executor / an async repository), or make persistence fire-and-forget through a bounded writer task so a slow DB cannot stall the consume/heartbeat path.

## Non-issues (verified correct)
- `Reconnector` does not sleep after the final failed attempt; backoff is exponential and capped via `backoff_delay` (`min(base * 2**(attempt-1), max_delay)`); `max_attempts`/`base`/`max_delay` are validated. ✓
- `Reconnector` catches `Exception` (not `BaseException`), so `asyncio.CancelledError` correctly propagates on shutdown — no task leaks from retry loops. ✓
- `BoundedQueue` enforces `maxsize >= 1` and a valid drop policy; `drop_newest`/`drop_oldest` semantics otherwise match the tests. ✓
- `HeartbeatMonitor` timeout is validated `> 0`; `_coerce_datetime`/staleness require timezone-aware clocks, avoiding naive-datetime comparison bugs. ✓
- `FakeMarketDataProvider.emit` correctly routes through the registered handler; connect/disconnect/health state transitions are deterministic for tests. ✓

## Verdict
REQUEST_CHANGES — reconnect bypasses the per-attempt timeout (can hang forever), dead-connection detection has no runtime watchdog, and the duplicate detector grows memory without bound.
