# Phase 7 (Trading Orchestrator) — Runtime / Concurrency / Database Review

**VERDICT: REQUEST_CHANGES**

Scope read: `service.py`, `repository.py`, `metrics.py`, `db/models/trading.py`
(`TradingIntentRecord`), `migrations/versions/20260819_trading_orchestrator.py`,
`tests/unit/test_trading_concurrency.py`, `test_trading_persistence.py`, plus
`identity.py`, `intent.py`, `state.py`, `oms_port.py`, `db/base.py`,
`alpha_algo_contracts/risk.py`, `alpha_algo_risk_engine/approval.py`,
`context.py`, and the risk/signal migration chain.

---

## Findings

### 1. MAJOR — Non-atomic check-then-insert: concurrent duplicate insert is swallowed as a false `PERSISTENCE_FAILED`
- **File:** `services/trading_engine/alpha_algo_trading_engine/repository.py:111-128`, `service.py:187-214`
- **Evidence:**
  ```python
  # repository.py
  def persist(self, record):
      session = self._session_factory()
      try:
          existing = _find_by_orchestration_id(session, record.orchestration_id)
      finally:
          session.close()
      if existing is not None:
          return OUTCOME_DUPLICATE, existing.id
      session = self._session_factory()
      try:
          session.add(record)
          session.commit()
          return OUTCOME_INSERTED, record.id
      except Exception:      # <-- IntegrityError NOT specially handled
          session.rollback()
          raise
  ```
  ```python
  # service.py:187-214
  try:
      persist_outcome, record_id = self._repository.persist(...)
  except Exception as exc:            # <-- catches the IntegrityError as generic
      persist_outcome = "error"
      record_id = None
  ...
  else:                               # "error" falls here
      return OrchestrationResult(state=OrchestrationState.FAILED,
          reason_code="PERSISTENCE_FAILED", ...)
  ```
- **Problem:** The module docstring claims *"A concurrent duplicate insert is back-stopped by the unique constraint"*, but the backstop is never translated. The `RLock` (`service.py:93,180`) only serializes **within a single process**. Under multi-worker / multi-process deployment sharing one DB, two workers can both pass `_find_by_orchestration_id` (returns `None`), both attempt INSERT; the loser raises `sqlalchemy.exc.IntegrityError` on `uq_trading_intents_orchestration_id`, which is caught as a generic `Exception` → `persist_outcome="error"` → returned as `state=FAILED` / `PERSISTENCE_FAILED`. So a *legitimate duplicate* is reported as a *failure*. No duplicate downstream intent is emitted (the unique constraint prevents data corruption and the loser never reaches the OMS handoff), but the idempotency result contract is violated and the winner's record id is never returned to the loser.
- **Fix:** Catch `sqlalchemy.exc.IntegrityError` on the INSERT path, roll back, then re-query and return `(OUTCOME_DUPLICATE, winner_id)`. Better: replace find-then-insert entirely with a single atomic `INSERT … ON CONFLICT (orchestration_id) DO NOTHING` (with `RETURNING id`, or a follow-up SELECT) so there is exactly one round trip and no race window.

### 2. MAJOR — Concurrency test never exercises the DB backstop
- **File:** `tests/unit/test_trading_concurrency.py:15-38`
- **Evidence:** `make_orchestrator(oms_port=port)` (see `trading_test_support.py:47-64`) leaves `repository=None`. The `test_concurrent_same_signal_yields_single_intent` test therefore only exercises the in-memory `_handed_off` cache + `RLock` branch (`service.py:180-182`, then the `else` at `service.py:217-220`) — **not** the repository find-then-insert / unique-constraint path from Finding 1.
- **Problem:** The exact race that makes Finding 1 real (cross-process duplicate INSERT) has zero coverage, so the `PERSISTENCE_FAILED`-instead-of-`DUPLICATE` misbehavior would pass CI unnoticed.
- **Fix:** Add a test that wires a real `TradingIntentRepository` (or a session factory whose commit raises `IntegrityError`) and asserts the losing concurrent call returns `DUPLICATE`, not `FAILED`.

### 3. MINOR — Unbounded in-memory idempotency cache; `idempotency_capacity` is dead
- **File:** `service.py:83,91-92,202,219`
- **Evidence:** `idempotency_capacity: int = 4096` is stored as `self._capacity` but **never referenced**. `self._handed_off[identity] = trading_intent` grows without bound for the process lifetime.
- **Problem:** In a long-running trading service this is an unbounded memory leak. The `OrderedDict` was clearly intended to be capacity-bounded LRU.
- **Fix:** On insert, evict LRU when `len(self._handed_off) > self._capacity` (it is already an `OrderedDict` under `RLock`, so `move_to_end`/`popitem` is trivial). Also note the cache is never invalidated if a row is manually removed from the DB while the process lives — document/accept or add a refresh path.

### 4. MINOR — Rejection persistence bypasses the idempotency lock/cache
- **File:** `service.py:308-336` (`_reject`), esp. `service.py:334`
- **Evidence:** `_reject` calls `self._repository.persist(record)` directly, without holding `self._lock` and without checking `_handed_off`, using `compute_orchestration_identity_key(signal, intent, mode)` — the **same** key the accepted path uses.
- **Problem:** A signal evaluated concurrently by two calls whose `now` straddles approval expiry yields one `OMS_HANDOFF_READY` INSERT (under lock) and one `REJECTED` INSERT (not under lock) with the same `orchestration_id`. The rejection INSERT hits the unique constraint, the `IntegrityError` is swallowed (`except Exception` at `service.py:336`), `persisted=False`, and the caller sees `REJECTED` while the durable row is the accepted intent — an audit inconsistency (same root cause as Finding 1).
- **Fix:** Route rejection persistence through the same dedupe/atomic path, or at minimum check `_handed_off`/existing-row before inserting a rejection for an identity that is already accepted.

### 5. MINOR — Durability-before-handoff silently degrades when `repository is None`
- **File:** `service.py:217-220` (and the `repository is None` branch), `service.py:234-235`
- **Evidence:** When `self._repository is None`, the orchestrator still calls `machine.transition(OMS_HANDOFF_READY)` and then `self._oms_port.handoff(trading_intent)` with a **non-durable** intent (`persisted=False`).
- **Problem:** The phase's core invariant ("intent durable BEFORE OMS handoff notify") is enforced only when a repository happens to be injected. A misconfigured production wiring would hand off non-durable intents with no error.
- **Fix:** Fail closed — require a repository for PAPER/BACKTEST modes (raise on construction if absent in a non-test path), keeping `None` allowed only for the test harness.

### 6. MINOR — OMS handoff failure has no retry / outbox (dual-write without transactional outbox)
- **File:** `service.py:234-247`
- **Evidence:** `handoff.delivered == False` only bumps `oms_handoff_failures`; the result still returns `OMS_HANDOFF_READY` with `handoff_delivered=False` and no retry or compensation. The intent is already committed.
- **Problem:** If Phase 8 is pull-based (reads the `trading_intents` table) this is acceptable, but nothing guarantees a failed notify is ever retried, so "handoff" is not at-least-once. This is the classic DB-commit-then-external-notify gap.
- **Fix:** Document the pull-based contract explicitly (Phase 8 polls the table, `handoff_delivered` is informational), or add an outbox/retry mechanism if push delivery is required.

### 7. MINOR — Two sessions/round-trips per persist; `process_signal_many` is N×SELECT
- **File:** `repository.py:111-128`, `service.py:261-278` (`process_signal_many`)
- **Evidence:** `persist` opens a session for the SELECT, closes it, then opens a **second** session for the INSERT. `process_signal_many` loops `process_signal` per record → N idempotency SELECTs (plus N INSERTs). The SELECT is redundant with the unique constraint.
- **Fix:** Collapse into the single atomic `ON CONFLICT DO NOTHING` statement from Finding 1 (removes the redundant find and the second connection).

### 8. NIT — Metrics not thread-safe under the phase's own concurrency model
- **File:** `metrics.py:27-35`
- **Evidence:** `inc()` does `setattr(self, name, getattr(self, name) + 1)` and `record_state()` does `self.by_state[state] = self.by_state.get(state, 0) + 1` — read-modify-write on shared mutable state, called concurrently from `process_signal` without a lock (e.g. `service.py:239` after the critical section).
- **Problem:** Concurrent signals can lose increments (undercounted metrics).
- **Fix:** Guard with the same `RLock`, or use `threading`-safe counters (e.g. `itertools.count` / `collections.Counter` under lock).

### 9. NIT — Dead metric `duplicate_intents`
- **File:** `metrics.py:13`; never incremented anywhere in `service.py` (only `duplicates` is used, `service.py:225`).
- **Fix:** Either wire it or remove it to avoid a misleading zero in dashboards.

### 10. NIT — Model/migration index drift (autogenerate will emit DROP INDEX)
- **File:** `db/models/trading.py` (`TradingIntentRecord`) vs `migrations/versions/20260819_trading_orchestrator.py:92-102`
- **Evidence:** Migration creates `ix_trading_intents_signal_id`, `ix_trading_intents_strategy_id`, `ix_trading_intents_state`, but the model columns (`signal_id`, `strategy_id`, `state`) declare no `index=True`.
- **Fix:** Add `index=True` to those model columns (or a `__table_args__` `Index`) so `alembic autogenerate` stays clean.

### 11. NIT — Loose UUID columns with no FK / dropped provenance
- **File:** `db/models/trading.py` (`TradingIntentRecord.strategy_id`, `.account_id`)
- **Evidence:** `strategy_id` and `account_id` are plain `PGUUID` columns with no `ForeignKey` (consistent with the migration and with `signals.strategy_id` in Phase 5, but `account_id` has no referential integrity to `broker_accounts`/`users`). Separately, `TradingIntent.signal_identity_key` (set in `service.py:299`) is silently dropped in `to_orm_trading_intent` — there is no `signal_identity_key` column.
- **Fix:** Document the deliberate sparse-population decision; consider an FK for `account_id`; note that `signal_identity_key` is recoverable via `orchestration_id` but is not stored explicitly.

### 12. NIT — No explicit statement/lock timeout on the idempotency insert
- **File:** `repository.py:111-128`
- **Evidence:** No `statement_timeout`/`lock_timeout` is set; a long lock wait on `uq_trading_intents_orchestration_id` would hold the process-local `RLock` (`service.py:180`), serializing all other signals in that worker.
- **Fix:** Consider `SET LOCAL lock_timeout`/`statement_timeout` (or `connect_args`/`execution_options`) around the INSERT.

---

## Verified OK (no finding)

- **Migration chain:** `20260819_trading_orchestrator` → `down_revision = 20260819_risk_engine` → `20260819_signal_engine` → `20260812_timescale_market_data` — valid, no branches.
- **FK targets:** `signal_id → signals.id`, `instrument_id → instruments.id`, `strategy_run_id → strategy_runs.id` all exist (tables created in `20260812_*` migrations); `ondelete="SET NULL"` matches the model.
- **Unique constraints:** `uq_trading_intents_orchestration_id` (the idempotency backstop) and `uq_trading_intents_approval_id` both created in `upgrade()`; `approval_id` is nullable so rejection rows (NULL) do not collide.
- **Downgrade symmetry:** `downgrade()` drops the three indexes, three FKs, two unique constraints, then the table — symmetric and correctly ordered.
- **Durability ordering:** the accepted intent is `session.commit()`ed (`repository.py:124`) before `_oms_port.handoff` (`service.py:234-235`); the code and comment correctly express "durable BEFORE handoff".
- **Failed commit ≠ false success:** `repository.py:126-128` rolls back and re-raises on commit failure; `service.py` maps it to `PERSISTENCE_FAILED` (never success). Verified by `test_persist_commit_failure_rolls_back_and_raises`.
- **Approval binding:** `approval_is_usable` (`approval.py`) requires `APPROVED`, unexpired, and matching `binding_hash`; `compute_orchestration_identity_key` embeds signal identity + quantity/account/order-type/mode, so `approval_id`/`expires_at` are guaranteed non-None on the accepted path (enforced by `RiskDecision.validate_approval_state`).
- **Narrow concurrency:** the critical section is scoped to the idempotency + persist block (`service.py:180-220`), not the whole pipeline (risk evaluation / intent building happen outside the lock). No global lock.
