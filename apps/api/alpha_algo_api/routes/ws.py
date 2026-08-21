from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from alpha_algo_api.auth import Permissions, authenticate_token
from alpha_algo_api.errors import ApiError
from alpha_algo_api.observability import record_ws_connect, record_ws_disconnect

router = APIRouter(tags=["websocket"])


@router.websocket("/api/v1/ws")
async def websocket_gateway(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token")
    try:
        user = authenticate_token(token)
        if not user.has_permission(Permissions.SYSTEM_READ):
            raise ApiError(
                code="FORBIDDEN",
                message="Required permission is missing.",
                status_code=403,
            )
    except ApiError:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    record_ws_connect()
    try:
        await websocket.send_json(
            {
                "type": "HEALTH_UPDATE",
                "payload": {
                    "service": "alpha-algo-api",
                    "status": "connected",
                    "live_trading": "disabled",
                },
            }
        )

        try:
            await websocket.receive_text()
        except WebSocketDisconnect:
            return
        await websocket.close(code=1000)
    finally:
        record_ws_disconnect()

