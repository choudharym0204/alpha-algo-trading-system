from __future__ import annotations

import pytest

from alpha_algo_api.security.tokens import TokenError, create_token, decode_token

SECRET = "test-secret-key"
ISSUER = "test-issuer"
AUDIENCE = "test-audience"


def _make(**overrides):
    kwargs = dict(
        subject="u1",
        permissions=["a", "b"],
        token_type="access",
        ttl_seconds=3600,
        secret=SECRET,
        issuer=ISSUER,
        audience=AUDIENCE,
    )
    kwargs.update(overrides)
    return create_token(**kwargs)


def test_roundtrip() -> None:
    token = _make()
    payload = decode_token(
        token, secret=SECRET, issuer=ISSUER, audience=AUDIENCE, expected_type="access"
    )
    assert payload.subject == "u1"
    assert payload.permissions == frozenset({"a", "b"})
    assert payload.token_type == "access"
    assert payload.expires_at > payload.issued_at


def test_wrong_secret_rejected() -> None:
    token = _make()
    with pytest.raises(TokenError):
        decode_token(token, secret="***", issuer=ISSUER, audience=AUDIENCE)


def test_tampered_signature_rejected() -> None:
    token = _make()
    head, _payload, _sig = token.split(".")
    with pytest.raises(TokenError):
        decode_token(
            f"{head}.{'A' * 40}.{'B' * 43}",
            secret=SECRET,
            issuer=ISSUER,
            audience=AUDIENCE,
        )


def test_expired_token_rejected() -> None:
    token = _make(ttl_seconds=-1)
    with pytest.raises(TokenError):
        decode_token(token, secret=SECRET, issuer=ISSUER, audience=AUDIENCE)


def test_wrong_type_rejected() -> None:
    token = _make(token_type="refresh")
    with pytest.raises(TokenError):
        decode_token(
            token, secret=SECRET, issuer=ISSUER, audience=AUDIENCE, expected_type="access"
        )


def test_wrong_audience_rejected() -> None:
    token = _make()
    with pytest.raises(TokenError):
        decode_token(token, secret=SECRET, issuer=ISSUER, audience="other-audience")


def test_wrong_issuer_rejected() -> None:
    token = _make()
    with pytest.raises(TokenError):
        decode_token(token, secret=SECRET, issuer="other-issuer", audience=AUDIENCE)


def test_malformed_token_rejected() -> None:
    with pytest.raises(TokenError):
        decode_token("not-a-jwt", secret=SECRET, issuer=ISSUER, audience=AUDIENCE)
