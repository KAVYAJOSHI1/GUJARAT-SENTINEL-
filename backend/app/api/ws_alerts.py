"""
WS /ws/alerts — native FastAPI WebSocket endpoint for real-time dashboard
alert push notifications. Clients connect and passively receive broadcast
alert JSON payloads from `services.alert_dispatcher.connection_manager`.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.alert_dispatcher import connection_manager

router = APIRouter()


@router.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    await connection_manager.connect(websocket)
    try:
        while True:
            # Dashboard clients don't need to send anything; keep the
            # connection alive and simply drain/ignore inbound frames
            # (e.g. client-side pings).
            await websocket.receive_text()
    except WebSocketDisconnect:
        await connection_manager.disconnect(websocket)
