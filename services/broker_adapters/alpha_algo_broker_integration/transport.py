"""HTTP transport abstraction (Phase 10).

Separates network I/O from adapter logic so tests can inject a deterministic
``FakeTransport`` (no real network / no credentials). The real ``HttpxTransport``
never logs or returns credential values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class TransportResponse:
    status_code: int
    body: dict[str, Any] | None = None
    text: str | None = None
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    @property
    def retry_after(self) -> float | None:
        value = self.headers.get("retry-after")
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


class BrokerHttpTransport(Protocol):
    """Minimal async HTTP surface adapters need."""

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> TransportResponse: ...


class HttpxTransport:
    """Real HTTP transport backed by httpx (credentials handled by callers)."""

    def __init__(self, base_url: str, *, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client = None

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> TransportResponse:
        import httpx

        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout
            )
        resp = await self._client.request(
            method, path, params=params, json=json, headers=headers
        )
        body = None
        try:
            body = resp.json()
        except Exception:  # noqa: BLE001 — non-JSON response
            body = None
        return TransportResponse(
            status_code=resp.status_code,
            body=body,
            text=resp.text,
            headers=dict(resp.headers),
        )


class FakeTransport:
    """Deterministic, scripted transport for automated tests (no network)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any] | None, dict[str, Any] | None]] = []
        self._responses: dict[tuple[str, str], TransportResponse] = {}
        self._default = TransportResponse(status_code=200, body={})

    def script(self, method: str, path: str, response: TransportResponse) -> None:
        self._responses[(method.upper(), path)] = response

    def set_default(self, response: TransportResponse) -> None:
        self._default = response

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> TransportResponse:
        self.calls.append((method.upper(), path, params, json))
        return self._responses.get((method.upper(), path), self._default)
