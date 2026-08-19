from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from alpha_algo_api import create_app
from alpha_algo_api.auth import Permissions, issue_access_token


def test_websocket_gateway_requires_authentication() -> None:
    client = TestClient(create_app())

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/api/v1/ws"):
            pass

    assert exc_info.value.code == 1008


def test_websocket_gateway_rejects_missing_permission() -> None:
    client = TestClient(create_app())
    token = issue_access_token("ws-no-read", [Permissions.TRADING_VIEW])

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/api/v1/ws?token={token}"):
            pass

    assert exc_info.value.code == 1008


def test_websocket_gateway_sends_health_update_for_authorized_client() -> None:
    client = TestClient(create_app())
    token = issue_access_token("ws-user", [Permissions.SYSTEM_READ])

    with client.websocket_connect(f"/api/v1/ws?token={token}") as websocket:
        message = websocket.receive_json()
        websocket.send_text("close")

    assert message == {
        "type": "HEALTH_UPDATE",
        "payload": {
            "service": "alpha-algo-api",
            "status": "connected",
            "live_trading": "disabled",
        },
    }
