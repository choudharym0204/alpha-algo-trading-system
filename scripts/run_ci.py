"""Local CI runner (Phase 22).

Runs the locally-executable quality gates in the same order as the GitHub
Actions workflow, so a developer can validate a change without a CI runner:

    python scripts/run_ci.py

Gates:
  1. compileall        — Python syntax check (all source trees)
  2. ruff check        — pyflakes + syntax errors
  3. pytest            — full backend regression (unit + in-memory integration)
  4. migration check   — Alembic graph validation (offline, no DB)
  5. security scan     — secrets / broker placeholders / LIVE fail-closed

Web (``npm run typecheck && npm test && npm run build``) and Flutter
(``flutter analyze && flutter test``) gates are run separately because they
require their own toolchains; see ``docs/ci-cd.md``.

Exit code 0 = all gates passed; non-zero = first failing gate.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

PYTHON = sys.executable  # reuse whatever interpreter is running this script


def _run(name: str, args: list[str], cwd: Path | None = None) -> bool:
    print(f"\n=== [{name}] {' '.join(args)} ===", flush=True)
    result = subprocess.run(args, cwd=cwd or REPO_ROOT)
    if result.returncode != 0:
        print(f"--- {name} FAILED (exit {result.returncode}) ---", flush=True)
        return False
    print(f"--- {name} OK ---", flush=True)
    return True


def main() -> int:
    gates: list[tuple[str, list[str]]] = [
        (
            "compileall",
            [
                PYTHON, "-m", "compileall", "-q",
                "apps", "packages", "services", "backtesting", "migrations", "scripts", "tests",
            ],
        ),
        ("ruff", [PYTHON, "-m", "ruff", "check", "."]),
        ("pytest", [PYTHON, "-m", "pytest", "tests/", "-q"]),
        ("migration-check", [PYTHON, "scripts/check_migrations.py"]),
        ("security-scan", [PYTHON, "scripts/security_scan.py"]),
    ]

    for name, args in gates:
        if not _run(name, args):
            print(f"\nLocal CI FAILED at gate: {name}", flush=True)
            return 1

    print("\nLocal CI: all gates passed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
