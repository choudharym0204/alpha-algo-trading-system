# Alpha Algo — CI/CD (Phase 22)

Continuous integration quality gates for the monorepo. Every change must pass
all gates before merge. CI **never** enables LIVE, connects to a broker,
deploys credentials, or bypasses safety gates.

## 1. Workflow (`.github/workflows/ci.yml`)

Triggers: `push` to `main` + `pull_request`. Concurrency cancels superseded runs.

| Job | Runner | Gates |
|---|---|---|
| `lint` | ubuntu-latest | `compileall` (syntax) + `ruff check` (pyflakes F + E9) |
| `test` | ubuntu-latest | full backend regression `pytest tests/` (no DB) |
| `security` | ubuntu-latest | `scripts/security_scan.py` |
| `migration-check` | ubuntu-latest | `scripts/check_migrations.py` (offline) |
| `web-build` | ubuntu-latest | `tsc --noEmit` + `vitest` + `next build` |
| `mobile-build` | ubuntu-latest | `flutter analyze` + `flutter test` + `flutter build apk --debug` |
| `desktop-build` | windows-latest | `flutter analyze` + `flutter test` + `flutter build windows` |

## 2. Dependency pinning

- Python deps are declared in `pyproject.toml` (single source of truth).
- `requirements-dev.txt` mirrors those pins for CI `pip install` (plus
  `python-dotenv`, `websockets` runtime extras the tests/migrations import).
- No dependency was upgraded in Phase 22 except adding `ruff` to the dev extras
  (required for the lint gate). Pinning style (`>=`) is unchanged.

## 3. Lint / type / format strategy

- **Python:** `ruff` with `select = ["F", "E9"]` — pyflakes (unused imports,
  undefined names, redefinitions) + syntax errors. Full style rules
  (E501/E731/etc.) are deliberately deferred until a formatting baseline is
  established. Phase 22 fixed 115 real pyflakes findings (100 auto-fixed unused
  imports + 15 manual), with the full regression confirming zero behavior change.
- **Web:** `tsc --noEmit` (strict TypeScript) + `next build` (which re-runs type
  checking). No ESLint config exists yet (documented follow-up).
- **Flutter:** `flutter analyze` (built-in Dart lints via `flutter_lints`).

## 4. Security gate

`scripts/security_scan.py` (pure stdlib, portable) enforces:
1. no real secret patterns (GitHub/Slack/OpenAI/AWS tokens, private keys),
2. broker keys (Zerodha/Upstox) stay `replace-…` placeholders,
3. `LIVE_TRADING_ENABLED`/`GLOBAL_TRADING_HALT` stay fail-closed in config
   (docs/tests/scripts that legitimately reference the flags are skipped).

## 5. Migration gate

`scripts/check_migrations.py` validates the Alembic graph **without a database**:
single head, single base, linear chain, no broken `down_revision` links, no
orphaned revision files, and (best-effort) the full chain compiles to offline SQL.

## 6. Caching

- Python: `setup-python` `cache: pip` keyed on `requirements-dev.txt`.
- Node: `setup-node` `cache: npm` keyed on `apps/web/package-lock.json`.
- Flutter: `subosito/flutter-action` `cache: true` (pub cache).

## 7. Artifacts & failure policy

CI fails on any test/lint/type/security/build/migration failure. Artifacts
(coverage/build outputs) are not uploaded in this iteration (no sensitive data
is ever uploaded). Test parallelization is not enabled — the backend suite is
not yet proven isolated under `pytest-xdist` (documented follow-up).

## 8. LIVE safety & release boundary

Phase 22 is **CI/CD infrastructure only**. No job enables LIVE, deploys broker
credentials, executes orders, or touches real broker accounts. Phase 23 (full
system verification) and Phase 24 (LIVE rollout) are out of scope and not
implemented. Automatic production deployment is not configured.

## 9. Verification status

All **locally-runnable** gates were executed and passed (see table below).
**Remote GitHub Actions execution and Docker-based jobs are deferred** — they
cannot run in this environment (no GitHub runner, no Docker), so Phase 22 status
is **IMPLEMENTED — VERIFICATION DEFERRED** per the spec (§19).

| Gate | Local result |
|---|---|
| `compileall` (syntax) | ✅ pass |
| `ruff check` | ✅ 0 issues (after 115 fixes) |
| backend `pytest` | ✅ **1669 passed** |
| migration check | ✅ 15 revisions, single head/base, offline SQL OK |
| security scan | ✅ clean |
| web `tsc --noEmit` | ✅ pass |
| web `vitest` | ✅ 29 passed |
| web `next build` | ✅ pass |
| mobile `flutter analyze` | ✅ 0 issues |
| mobile `flutter test` | ✅ 23 passed |
| desktop `flutter analyze` | ✅ 0 issues |
| desktop `flutter test` | ✅ 29 passed |
| `ci.yml` YAML | ✅ parses (7 jobs) |
| `flutter build apk` / `flutter build windows` | ⏭ cited from Phases 18/19 (code unchanged) |
| GitHub Actions execution | ⏭ deferred (no runner) |
| `docker compose config` | ⏭ deferred (no Docker) |

## 10. Known limitations

- Remote CI + Docker jobs unverified locally (deferred).
- No ESLint for web (typecheck covers TS; lint deferred).
- Full Python style formatting (ruff format / E501) deferred.
- `pytest-xdist` parallelization deferred (isolation not yet proven).
- iOS/macOS builds excluded (no macOS/Xcode) — not claimed.
- Repo path apostrophe (`MUKESH'S PC`) breaks Flutter tooling; local Flutter
  validation uses clean-path copies (`C:\src\p22_mobile`, `C:\src\p22_desktop`).
