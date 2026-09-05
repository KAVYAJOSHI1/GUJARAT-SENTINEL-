"""
WS /ws/alerts — native FastAPI WebSocket endpoint for real-time dashboard
alert push notifications. Requires the SAME JWT the REST API accepts
(``app.core.security.decode_access_token`` — no second auth mechanism).

SENTINEL_System_Audit_Report.md §9/§10/§15 flagged this endpoint as
accepting every connection with zero token check: any network-reachable
client could subscribe to every live alert (plate numbers, camera ids,
snapshot URLs). This module closes that gap.

Transport for the credential: a browser ``WebSocket`` cannot set an
``Authorization`` header on the handshake, so the credential rides as a
``Sec-WebSocket-Protocol`` value (``new WebSocket(url, [ticket])``), never
a ``?token=`` query string -- a subprotocol is only ever a request HEADER,
so a default access-log config (request line + status) never captures it,
whereas a query string lands in the URL, browser history, and most
request-line logs.

**Phase 4**: the credential is now a short-lived, single-purpose **WS
ticket** (``purpose="ws"``, ~60s TTL), issued from
``POST /api/v1/auth/ws-ticket`` against a valid session JWT -- NOT the
long-lived session JWT itself. So even a header-capturing proxy only ever
sees a value that is useless in seconds and useless for anything but this
one endpoint. A normal session JWT offered here is rejected (it has no
``purpose`` claim).

This module never logs the ticket itself, at any log level, in either the
success or failure path.
"""
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.security import decode_scoped_ticket
from app.database import SessionLocal
from app.models.user import User
from app.services.alert_dispatcher import connection_manager

logger = logging.getLogger("sentinel.ws")

router = APIRouter()

# Private-use WebSocket close code (RFC 6455 §7.4.2 reserves 4000-4999 for
# applications) for "authentication required/failed" -- distinguishable
# from a normal 1000/1001 close in client-side reconnect logic if needed.
WS_POLICY_VIOLATION = 4401


def _extract_ticket(websocket: WebSocket) -> str | None:
    """The WS ticket rides as a WebSocket subprotocol (see module
    docstring), e.g. ``new WebSocket(url, [ticket])``. Returns the first
    offered subprotocol, or None -- never reads a query parameter."""
    proto = websocket.headers.get("sec-websocket-protocol")
    if not proto:
        return None
    first = proto.split(",")[0].strip()
    return first or None


def _authenticate(websocket: WebSocket) -> User | None:
    """Validate the offered short-lived WS ticket (``purpose="ws"``, ~60s):
    signature, expiry, purpose, then an active-user DB lookup. Returns None
    for anything missing/malformed/expired/wrong-purpose (including a normal
    session JWT) or an inactive/deleted user. Uses its own short-lived DB
    session since WebSocket routes don't join the usual `Depends(get_db)`
    lifecycle."""
    ticket = _extract_ticket(websocket)
    if not ticket:
        return None
    try:
        payload = decode_scoped_ticket(ticket, "ws")
    except ValueError:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    db = SessionLocal()
    try:
        user = db.get(User, user_id)
    finally:
        db.close()
    if user is None or not user.is_active:
        return None
    return user


@router.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    user = _authenticate(websocket)
    if user is None:
        # Reject BEFORE accept(): the socket is never registered with
        # connection_manager and receives no alert data. Closing without
        # ever accepting is how a WebSocket handshake is refused in ASGI.
        await websocket.close(code=WS_POLICY_VIOLATION)
        return

    # Deliberately accept with no negotiated subprotocol: the client's
    # token was already consumed above for auth, and per RFC 6455 §4.2.2 a
    # server may omit Sec-WebSocket-Protocol entirely, so the token is never
    # echoed back in a response header either.
    await connection_manager.connect(websocket)
    try:
        while True:
            # Dashboard clients don't need to send anything; keep the
            # connection alive and simply drain/ignore inbound frames
            # (e.g. client-side pings).
            await websocket.receive_text()
    except WebSocketDisconnect:
        await connection_manager.disconnect(websocket)
