from __future__ import annotations

from alpha_algo_api.security.password import hash_password, needs_rehash, verify_password


def test_hash_and_verify_roundtrip() -> None:
    hashed = hash_password("correct horse battery staple")

    assert hashed.startswith("$argon2id$")
    assert verify_password("correct horse battery staple", hashed) is True
    assert verify_password("wrong password", hashed) is False


def test_verify_rejects_malformed_hash() -> None:
    assert verify_password("anything", "not-a-real-hash") is False


def test_needs_rehash_false_for_fresh_hash() -> None:
    hashed = hash_password("password123")
    assert needs_rehash(hashed) is False


def test_hash_is_salted() -> None:
    first = hash_password("same-password")
    second = hash_password("same-password")
    assert first != second
    assert verify_password("same-password", first) is True
    assert verify_password("same-password", second) is True
