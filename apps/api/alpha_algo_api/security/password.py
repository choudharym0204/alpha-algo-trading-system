"""Password hashing using Argon2id (memory-hard, OWASP-recommended)."""

from __future__ import annotations

import argon2
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# OWASP-recommended minimum parameters for Argon2id.
_TIME_COST = 2
_MEMORY_COST = 19456  # KiB (19 MiB)
_PARALLELISM = 1
_HASH_LEN = 32
_SALT_LEN = 16

_hasher = PasswordHasher(
    time_cost=_TIME_COST,
    memory_cost=_MEMORY_COST,
    parallelism=_PARALLELISM,
    hash_len=_HASH_LEN,
    salt_len=_SALT_LEN,
    type=argon2.Type.ID,
)


def hash_password(password: str) -> str:
    """Hash a plaintext password and return an encoded Argon2id hash string."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against an encoded Argon2id hash.

    Returns False on any verification or decoding failure; never raises.
    """
    try:
        return _hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """Return True when *password_hash* does not use current parameters."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True
