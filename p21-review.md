# Phase 21 — Event Architecture — Adversarial Review

Inline four-axis review. No independent review agent is available at the
model/provider layer; this is a transparent inline review, not claimed as
independent (Phase 21 §63 pattern).

---

## Review 1 — Architecture

| # | Level | Finding | Disposition |
|---|---|---|---|
| 1.1 | NOTE | Unified envelope + bus are additive; the tested synchronous pipeline is unchanged. | Correct per "do not modify completed phases" rule. |
| 1.2 | NOTE | Broker/streaming eventing deferred (no scale justification). | Documented (§2 scope). |
| 1.3 | NOTE | In-process bus only (no persistence/cross-process/replay). | Documented limitation. |

**Verdict:** PASS — 0 BLOCKER / 0 MAJOR / 0 MINOR / 3 NOTE.

## Review 2 — Runtime / Concurrency

| # | Level | Finding | Disposition |
|---|---|---|---|
| 2.1 | PASS | Thread-safe subscription registry (RLock); dispatch snapshots the handler list outside the lock. | Verified. |
| 2.2 | PASS | Deterministic FIFO ordering (subscription order + list order). | Tested. |
| 2.3 | MINOR | `self._failures` was initialized with `field(default_factory=list)` inside a non-dataclass `__init__`, producing a `Field` object (AttributeError on first failure). | FIXED — plain list; tests now cover handler failure. |

**Verdict:** PASS — 0 BLOCKER / 0 MAJOR / 1 MINOR (fixed) / 2 PASS.

## Review 3 — Operational Correctness

| # | Level | Finding | Disposition |
|---|---|---|---|
| 3.1 | PASS | Envelope validation: tz-aware, safe event_type, non-empty source, dict payload, str→str domain_ids, no self-causation. | Tested. |
| 3.2 | PASS | Causation chain via `derive()` preserves correlation + trace + domain ids. | Tested. |
| 3.3 | PASS | Full pipeline flow is reconstructable end-to-end (ordering, causation, correlation, domain ids). | Integration-tested. |
| 3.4 | PASS | Handler failure isolation: healthy subscribers still receive; failures recorded. | Tested. |

**Verdict:** PASS — 0 BLOCKER / 0 MAJOR / 0 MINOR / 4 PASS.

## Review 4 — Security / LIVE Safety

| # | Level | Finding | Disposition |
|---|---|---|---|
| 4.1 | PASS | Secrets rejected at envelope construction (recursive `validate_no_secrets`). | Tested (password/token/nested api_key). |
| 4.2 | PASS | Legit keys (`identity_key`, `order_id`) are not over-rejected. | Tested. |
| 4.3 | PASS | Events are append-only facts; no path to enable LIVE or modify state. | Confirmed. |
| 4.4 | PASS | No external broker/network/credentials introduced. | Confirmed. |

**Verdict:** PASS — 0 BLOCKER / 0 MAJOR / 0 MINOR / 4 PASS.

---

## Summary

- **0 BLOCKER / 0 MAJOR / 1 MINOR (fixed) / 3 NOTE.**
- Fixed: bus `_failures` init (dataclass `field` misuse).
- **Evidence:** 21 new event-architecture tests; full backend regression
  **1669 passed** (1648 baseline, zero regressions).
- **LIVE remains disabled and fail-closed throughout.**
- No independent reviewer is claimed — inline adversarial review, recorded.
