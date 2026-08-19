"""Programmatic Alembic migration runner.

Usage::

    python scripts/migrate.py upgrade head
    python scripts/migrate.py current
    python scripts/migrate.py downgrade -1

This mirrors the ``alembic`` CLI but bootstraps the repo's ``sys.path`` and
``.env`` so it works from a clean checkout without manual ``PYTHONPATH`` setup.
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]

# Ensure the repo root, the shared package, and the migrations package are
# importable before Alembic runs env.py (which relies on these paths).
for candidate in (REPO_ROOT, REPO_ROOT / "apps" / "api", REPO_ROOT / "packages" / "shared"):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

load_dotenv(REPO_ROOT / ".env")

from alembic import command  # noqa: E402  (import after sys.path bootstrap)
from alembic.config import Config  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python scripts/migrate.py <upgrade|downgrade|current|heads|history> [args...]")
        raise SystemExit(2)

    action = sys.argv[1]
    args = sys.argv[2:]

    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "migrations"))

    if action == "upgrade":
        command.upgrade(config, args[0] if args else "head")
    elif action == "downgrade":
        command.downgrade(config, args[0] if args else "-1")
    elif action == "current":
        command.current(config)
    elif action == "heads":
        command.heads(config)
    elif action == "history":
        command.history(config)
    else:
        print(f"unknown action: {action}")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
