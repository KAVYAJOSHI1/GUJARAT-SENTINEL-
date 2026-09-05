"""
WS /ws/alerts authentication.

Phase 4: the WS handshake credential is a short-lived, single-purpose
ticket (`POST /api/v1/auth/ws-ticket`, `purpose="ws"`, ~60s) -- NOT the
long-lived session JWT. A session JWT offered as the subprotocol is
rejected.

Covers: valid/missing/invalid/expired ticket, session-JWT-not-accepted, a
valid client actually receiving a real alert broadcast, and an
unauthenticated client receiving nothing.
"""
from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt
from starlette.websockets import WebSocketDisconnect

from app.config import settings
from app.core.security import create_scoped_ticket
from conftest import bearer, ws_ticket


def _expired_ws_ticket(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "purpose": "ws",
        "exp": datetime.now(timezone.utc) - timedelta(minutes=5),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def test_valid_ticket_accepted(client, operator_user):
    _, token = operator_user
    ticket = ws_ticket(client, token)
    with client.websocket_connect("/ws/alerts", subprotocols=[ticket]) as ws:
        assert ws is not None


def test_missing_token_rejected(client):
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws/alerts"):
            pass
    assert exc_info.value.code == 4401


def test_invalid_token_rejected(client):
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws/alerts", subprotocols=["not-a-real-jwt"]):
            pass
    assert exc_info.value.code == 4401


def test_expired_ticket_rejected(client, operator_user):
    user, _ = operator_user
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws/alerts", subprotocols=[_expired_ws_ticket(user.id)]):
            pass
    assert exc_info.value.code == 4401


def test_session_jwt_not_accepted_as_ws_ticket(client, operator_user):
    """The long-lived session JWT must NOT work as a WS credential -- it has
    no `purpose="ws"` claim."""
    _, token = operator_user
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws/alerts", subprotocols=[token]):
            pass
    assert exc_info.value.code == 4401


def test_media_ticket_not_accepted_for_ws(client, operator_user):
    """A media-purpose ticket must not open the alert socket."""
    _, token = operator_user
    media = create_scoped_ticket(subject="u", purpose="media", ttl_seconds=60)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/alerts", subprotocols=[media]):
            pass


def test_authenticated_client_receives_real_alert(client, officer_user, make_camera):
    # OFFICER (not OPERATOR) because this test also has to create the
    # watchlist entry via the real REST endpoint, which is RBAC-gated to
    # ADMIN/OFFICER -- WS auth itself doesn't care about role, any active
    # user's token is accepted (see test_valid_token_accepted, OPERATOR).
    _, token = officer_user
    camera = make_camera(code="cam-ws-01")

    # Seed an active, non-expiring watchlist entry for the plate we're about
    # to "detect".
    watchlist_resp = client.post(
        "/api/v1/watchlist",
        json={"plate_number": "GJ18XX1234", "offense_category": "STOLEN"},
        headers=bearer(token),
    )
    assert watchlist_resp.status_code == 201

    with client.websocket_connect("/ws/alerts", subprotocols=[ws_ticket(client, token)]) as ws:
        ingest_resp = client.post(
            "/api/v1/events/ai-detection",
            json={
                "camera_id": camera.code,
                "timestamp": datetime.utcnow().isoformat(),
                "plate_number": "GJ18XX1234",
                "track_id": 1,
                "confidence_score": 0.95,
            },
            headers={"X-Ingest-Key": settings.INGEST_API_KEY},
        )
        assert ingest_resp.status_code == 201
        body = ingest_resp.json()
        assert body["watchlist_match"] is True
        assert body["alert_id"] is not None

        message = ws.receive_json()
        assert message["type"] == "ALERT"
        assert message["plate_number"] == "GJ18XX1234"
        assert message["alert_id"] == body["alert_id"]


def test_unauthenticated_client_receives_nothing(client, officer_user, make_camera):
    """An unauthenticated connection attempt is rejected outright (never
    joins the connection manager), so it can never receive an alert that a
    concurrently-connected authenticated client does."""
    _, token = officer_user
    camera = make_camera(code="cam-ws-02")

    client.post(
        "/api/v1/watchlist",
        json={"plate_number": "GJ05CD5678", "offense_category": "WARRANT"},
        headers=bearer(token),
    )

    with client.websocket_connect("/ws/alerts", subprotocols=[ws_ticket(client, token)]) as authed_ws:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/alerts"):
                pass

        ingest_resp = client.post(
            "/api/v1/events/ai-detection",
            json={
                "camera_id": camera.code,
                "timestamp": datetime.utcnow().isoformat(),
                "plate_number": "GJ05CD5678",
                "track_id": 2,
                "confidence_score": 0.95,
            },
            headers={"X-Ingest-Key": settings.INGEST_API_KEY},
        )
        assert ingest_resp.status_code == 201

        # The authenticated client still gets it -- proves the unauth'd
        # attempt above never registered with the connection manager rather
        # than the broadcast silently going nowhere for everyone.
        message = authed_ws.receive_json()
        assert message["type"] == "ALERT"
        assert message["plate_number"] == "GJ05CD5678"
