import asyncio
import os

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.events import subscribe, unsubscribe

router = APIRouter(tags=["WebSocket"])

_WS_TOKEN = os.environ.get("HYSTRON_WS_TOKEN", "")


@router.websocket("/ws/events")
async def ws_events(websocket: WebSocket):
    if not _WS_TOKEN:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    token = websocket.query_params.get("token", "")
    if token != _WS_TOKEN:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    queue = await subscribe()

    await websocket.send_json({"event": "connected", "data": {}})

    try:
        while True:
            try:
                message = await asyncio.wait_for(queue.get(), timeout=30.0)
                await websocket.send_text(message)
            except asyncio.TimeoutError:
                await websocket.send_json({"event": "ping", "data": {}})
    except WebSocketDisconnect:
        pass
    finally:
        await unsubscribe(queue)
