"""Minimal HS256 JWT implementation using only the Python standard library.

Intentionally dependency-free so that token issuance and verification are
fully self-contained and testable. Tokens carry an explicit ``type`` claim
(``access`` vs ``refresh``) to prevent access/refresh token confusion.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass

ALGORITHM = "HS256"


class TokenError(Exception):
    """Raised when a token is malformed, invalid, or expired."""


@dataclass(frozen=True)
class TokenPayload:
    subject: str
    permissions: frozenset[str]
    token_type: str
    issued_at: int
    expires_at: int
    jti: str


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _sign(header_b64: str, payload_b64: str, secret: str) -> str:
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    digest = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return _b64url_encode(digest)


def create_token(
    *,
    subject: str,
    permissions: list[str] | frozenset[str],
    token_type: str,
    ttl_seconds: int,
    secret: str,
    issuer: str,
    audience: str,
) -> str:
    """Issue a signed JWT."""
    now = int(time.time())
    header = {"alg": ALGORITHM, "typ": "JWT"}
    payload = {
        "sub": subject,
        "permissions": sorted(set(permissions)),
        "type": token_type,
        "iss": issuer,
        "aud": audience,
        "iat": now,
        "exp": now + ttl_seconds,
        "jti": uuid.uuid4().hex,
    }
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _sign(header_b64, payload_b64, secret)
    return f"{header_b64}.{payload_b64}.{signature}"


def decode_token(
    token: str,
    *,
    secret: str,
    issuer: str,
    audience: str,
    expected_type: str | None = None,
) -> TokenPayload:
    """Verify and decode a JWT, enforcing signature, expiry, issuer, audience, and type."""
    parts = token.split(".")
    if len(parts) != 3:
        raise TokenError("malformed token")

    header_b64, payload_b64, signature = parts
    expected_signature = _sign(header_b64, payload_b64, secret)
    if not hmac.compare_digest(signature, expected_signature):
        raise TokenError("invalid signature")

    try:
        header = json.loads(_b64url_decode(header_b64))
        payload = json.loads(_b64url_decode(payload_b64))
    except (ValueError, UnicodeDecodeError) as exc:
        raise TokenError("invalid token encoding") from exc

    if header.get("alg") != ALGORITHM:
        raise TokenError("unsupported algorithm")

    now = int(time.time())
    if int(payload.get("exp", 0)) <= now:
        raise TokenError("expired token")
    if payload.get("iss") != issuer:
        raise TokenError("invalid issuer")
    if payload.get("aud") != audience:
        raise TokenError("invalid audience")
    if expected_type is not None and payload.get("type") != expected_type:
        raise TokenError("invalid token type")

    return TokenPayload(
        subject=str(payload.get("sub", "")),
        permissions=frozenset(payload.get("permissions", [])),
        token_type=str(payload.get("type", "")),
        issued_at=int(payload.get("iat", 0)),
        expires_at=int(payload.get("exp", 0)),
        jti=str(payload.get("jti", "")),
    )
