"""Secret handling helpers.

Centralizes detection of placeholder/unsafe secrets so that the runtime can
fail closed instead of silently operating with a committed default.
"""

from __future__ import annotations

import os

# Substrings that indicate a value is a placeholder, not a real secret.
_PLACEHOLDER_MARKERS = (
    "change-me",
    "change_me",
    "changeme",
    "replace",
    "insecure",
    "dev-only",
    "dev_only",
    "placeholder",
    "example",
)


def is_placeholder(value: str | None) -> bool:
    """Return True when *value* is empty or looks like a placeholder."""
    if value is None:
        return True
    stripped = value.strip()
    if not stripped:
        return True
    lowered = stripped.lower()
    return any(marker in lowered for marker in _PLACEHOLDER_MARKERS)


def require_real_secret(value: str | None, *, name: str) -> str:
    """Return *value* if it is a real secret, otherwise raise ValueError.

    This is the fail-closed guard used for security-critical settings.
    """
    if is_placeholder(value):
        raise ValueError(
            f"{name} must be set to a real secret; refusing to run with a placeholder value."
        )
    return value.strip()  # type: ignore[return-value]


def secret_from_env(name: str, default: str | None = None) -> str | None:
    """Read a secret from the environment, never from a committed default."""
    return os.getenv(name, default)
