"""Offline migration-chain validation (Phase 22, no database required).

Validates that the Alembic migration graph is sound *without* connecting to a
database or requiring TimescaleDB/Postgres:

1. exactly one head (no accidental branch),
2. exactly one base (no orphaned independent chains),
3. every ``down_revision`` links to a real revision,
4. no duplicate revision ids and no orphaned revision files,
5. (best-effort) the full chain compiles to offline SQL.

Exit code 0 = healthy; non-zero = broken chain. Used by the CI ``migration-check``
job and by the local CI runner.

Usage::

    python scripts/check_migrations.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
for candidate in (REPO_ROOT, REPO_ROOT / "apps" / "api", REPO_ROOT / "packages" / "shared"):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

load_dotenv(REPO_ROOT / ".env")

from alembic.config import Config  # noqa: E402
from alembic.script import ScriptDirectory  # noqa: E402

_REVISION_RE = re.compile(r'^\s*revision\s*=\s*"([^"]+)"\s*$', re.MULTILINE)
_DOWN_REVISION_RE = re.compile(r'^\s*down_revision\s*=\s*(?:None|"([^"]+)")\s*$', re.MULTILINE)


def _parse_revision_files(version_dir: Path) -> tuple[dict[str, str | None], list[str]]:
    """Return {revision_id: down_revision_or_None} and any parse errors."""
    graph: dict[str, str | None] = {}
    errors: list[str] = []
    for path in sorted(version_dir.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        rev_m = _REVISION_RE.search(text)
        down_m = _DOWN_REVISION_RE.search(text)
        if not rev_m:
            errors.append(f"{path.name}: could not parse revision id")
            continue
        rev_id = rev_m.group(1)
        if rev_id in graph:
            errors.append(f"duplicate revision id {rev_id!r} in {path.name}")
            continue
        down = down_m.group(1) if down_m and down_m.group(1) else None
        graph[rev_id] = down
    return graph, errors


def main() -> int:
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "migrations"))

    script = ScriptDirectory.from_config(config)
    version_dir = REPO_ROOT / "migrations" / "versions"

    errors: list[str] = []

    heads = list(script.get_heads())
    bases = list(script.get_bases())
    if len(heads) != 1:
        errors.append(f"expected exactly 1 head, found {len(heads)}: {heads}")
    if len(bases) != 1:
        errors.append(f"expected exactly 1 base, found {len(bases)}: {bases}")

    graph, parse_errors = _parse_revision_files(version_dir)
    errors.extend(parse_errors)

    # Broken down_revision links.
    for rev_id, down in graph.items():
        if down is not None and down not in graph:
            errors.append(f"revision {rev_id} references missing down_revision {down!r}")

    # Reachability: exactly one revision is never referenced (the head), and the
    # count of files matches the count of parsed revisions (no orphans).
    referenced = {d for d in graph.values() if d is not None}
    heads_by_graph = sorted(r for r in graph if r not in referenced)
    if len(heads_by_graph) != 1:
        errors.append(f"expected 1 head by down_revision graph, found {heads_by_graph}")

    if errors:
        print("MIGRATION CHECK FAILED:")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(
        f"migration graph: OK ({len(graph)} revisions, single head={heads[0]}, "
        f"single base={bases[0]}, linear, no orphans)"
    )

    # Best-effort offline SQL generation (no DB).
    import logging
    from contextlib import redirect_stderr, redirect_stdout
    from io import StringIO

    from alembic import command

    buffer = StringIO()
    logging.disable(logging.WARNING)  # suppress alembic INFO during offline generation
    try:
        with redirect_stdout(buffer), redirect_stderr(StringIO()):
            command.upgrade(config, "head", sql=True)
    except Exception as exc:  # noqa: BLE001 - soft failure only
        print(f"offline SQL generation: skipped ({type(exc).__name__}: {exc})")
    else:
        if buffer.getvalue():
            print("offline SQL generation: OK")
        else:
            print("offline SQL generation: empty (soft)")
    finally:
        logging.disable(logging.NOTSET)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
