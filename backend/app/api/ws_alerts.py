"""
WS /ws/alerts — native FastAPI WebSocket endpoint for real-time dashboard
alert push notifications. Requires the SAME JWT the REST API accepts
(``app.core.security.decode_access_token`` — no second auth mechanism).

SENTINEL_System_Audit_Report.md §9/§10/§15 flagged this endpoint as
accepting every connection with zero token check: any network-reachable
client could subscribe to every live alert (plate numbers, camera ids,
snapshot URLs). This module closes that gap.

Transport for the token: a browser ``WebSocket`` cannot set an
``Authorization`` header on the handshake request, so the two realistic
options are a ``?token=`` query string or the ``Sec-WebSocket-Protocol``
header (which a plain ``new WebSocket(url, [token])`` call sends). This
uses the *subprotocol* header, not the query string:

  - a query string is part of the URL -> it lands in browser history and in
    the request line most HTTP/reverse-proxy access logs capture by
    default, even ones that don't log headers.
  - a subprotocol value is only ever sent as a request HEADER during the
    handshake -- it is never part of the URL, so a default access-log
    configuration (request line + status only) never captures it.

Residual limitation (documented, not silently ignored): a log/proxy
configuration that explicitly captures request headers could still record
it, and this is still the same long-lived (8h) session JWT the REST API
uses, not a short-lived single-use ticket. Fully removing that exposure
would mean issuing scoped, short-TTL WS tickets from a dedicated endpoint
-- out of scope for this hardening pass (see final report / audit §10).

This module never logs the token itself, at any log level, in either the
success or failure path.
"""
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.security import decode_access_token
from app.database import SessionLocal
from app.models.user import User
from app.services.alert_dispatcher import connection_manager

logger = logging.getLogger("sentinel.ws")

router = APIRouter()

# Private-use WebSocket close code (RFC 6455 §7.4.2 reserves 4000-4999 for
# applications) for "authentication required/failed" -- distinguishable
# from a normal 1000/1001 close in client-side reconnect logic if needed.
WS_POLICY_VIOLATION = 4401


def _extract_token(websocket: WebSocket) -> str | None:
    """The token rides as a WebSocket subprotocol (see module docstring),
    e.g. ``new WebSocket(url, [jwt])``. Returns the first offered
    subprotocol, or None if the client didn't send one -- never reads a
    query parameter."""
    proto = websocket.headers.get("sec-websocket-protocol")
    if not proto:
        return None
    first = proto.split(",")[0].strip()
    return first or None


def _authenticate(websocket: WebSocket) -> User | None:
    """Validate the offered token exactly like the REST `get_current_user`
    dependency does (same decode + active-user DB lookup) -- returns None
    for a missing, malformed, expired, or invalid token, or an inactive/
    deleted user. Uses its own short-lived DB session since WebSocket routes
    don't participate in the usual `Depends(get_db)` request lifecycle."""
    token = _extract_token(websocket)
    if not token:
        return None
    try:
        payload = decode_access_token(token)
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
