"""Portable secret + safety scanner (pure stdlib — no external deps).

Equivalent to the CI ``security`` gate, runnable locally and on any runner.
Scans the repository for:

1. real secret patterns (GitHub/Slack/OpenAI/AWS tokens, private keys),
2. accidental broker secrets (Zerodha/Upstox keys must stay "replace-…" placeholders),
3. fail-closed LIVE flags (no ``LIVE_TRADING_ENABLED=true`` or
   ``GLOBAL_TRADING_HALT=false`` committed).

Exit code 0 = clean; non-zero = findings.

Usage::

    python scripts/security_scan.py
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

REAL_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("GitHub token", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("Slack token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("OpenAI/Stripe key", re.compile(r"sk-[A-Za-z0-9]{16,}")),
    ("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("Private key", re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----")),
]

BROKER_KEY_RE = re.compile(
    r"(ZERODHA|UPSTOX)_(API_KEY|API_SECRET|ACCESS_TOKEN)\s*=\s*(.+)$", re.IGNORECASE
)

LIVE_ENABLED_RE = re.compile(r"LIVE_TRADING_ENABLED\s*=\s*true", re.IGNORECASE)
GLOBAL_HALT_RE = re.compile(r"GLOBAL_TRADING_HALT\s*=\s*false", re.IGNORECASE)

SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".next",
    "build",
    "dist",
    ".dart_tool",
    "windows",
    "linux",
    "macos",
    "ios",
    "android",
    "outputs",
}

SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf",
    ".zip", ".gz", ".tar", ".woff", ".woff2", ".ttf", ".eot",
    ".exe", ".dll", ".so", ".dylib", ".jar", ".apk", ".aab",
    ".lock", ".map",
}


def _iter_text_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        parts = rel.parts
        if any(p in SKIP_DIRS for p in parts):
            continue
        if path.suffix.lower() in SKIP_EXTENSIONS:
            continue
        yield path


def _is_live_safety_checkable(rel: str) -> bool:
    """LIVE-safety scan skips docs/tests/scripts/workflows (they legitimately
    reference the flags to document or *test* fail-closed behaviour)."""
    if rel.endswith(".md"):
        return False
    if rel.startswith(("tests/", "scripts/", ".github/")):
        return False
    return True


def scan(root: Path = REPO_ROOT) -> list[str]:
    findings: list[str] = []
    for path in _iter_text_files(root):
        rel = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            for label, pattern in REAL_SECRET_PATTERNS:
                if pattern.search(line):
                    findings.append(f"{rel}:{line_no}: {label} pattern found")
            broker = BROKER_KEY_RE.search(line)
            if broker:
                value = broker.group(3).strip().strip('"').strip("'")
                if value and not value.lower().startswith("replace"):
                    findings.append(
                        f"{rel}:{line_no}: broker secret {broker.group(1)}_{broker.group(2)} "
                        f"is not a placeholder"
                    )
            # LIVE safety flags (fail-closed) — skip docs/tests/scripts/workflows.
            if _is_live_safety_checkable(rel):
                if LIVE_ENABLED_RE.search(line):
                    findings.append(f"{rel}:{line_no}: LIVE_TRADING_ENABLED=true (fail-closed violated)")
                if GLOBAL_HALT_RE.search(line):
                    findings.append(f"{rel}:{line_no}: GLOBAL_TRADING_HALT=false (fail-closed violated)")
    return findings


def main() -> int:
    findings = scan()
    if findings:
        print("SECURITY SCAN FAILED:")
        for f in findings:
            print(f"  - {f}")
        return 1
    print("security scan: OK (no real secrets, broker placeholders, LIVE fail-closed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
