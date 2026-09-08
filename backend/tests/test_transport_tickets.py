"""
Phase 4 -- short-lived, single-purpose transport tickets (WS handshake +
media <img>/<video> src), so the long-lived session JWT never appears in a
URL query string or a WS subprotocol.

Covers: ticket issuance requires a valid JWT; tickets carry the right
purpose + a short TTL; the session JWT is NOT accepted as ?token= on the
evidence endpoint; a media ticket IS accepted; a ws ticket is not usable
for media and vice-versa; expired tickets are rejected.
"""
from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from app.config import settings
from app.core.security import create_scoped_ticket
from conftest import bearer, media_ticket


def test_ws_ticket_requires_auth(client):
    assert client.post("/api/v1/auth/ws-ticket").status_code == 401


def test_media_ticket_requires_auth(client):
    assert client.post("/api/v1/auth/media-ticket").status_code == 401


def test_ws_ticket_shape(client, operator_user):
    _, token = operator_user
    resp = client.post("/api/v1/auth/ws-ticket", headers=bearer(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["purpose"] == "ws"
    assert 0 < body["expires_in"] <= 300
    claims = jwt.decode(body["ticket"], settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    assert claims["purpose"] == "ws"
    ttl = claims["exp"] - claims["iat"]
    assert ttl <= settings.WS_TICKET_TTL_SECONDS + 2


def test_media_ticket_shape(client, operator_user):
    _, token = operator_user
    resp = client.post("/api/v1/auth/media-ticket", headers=bearer(token))
    assert resp.status_code == 200
    assert resp.json()["purpose"] == "media"


def test_evidence_rejects_session_jwt_as_query_token(client, officer_user, make_camera, make_vehicle_event):
    _, token = officer_user
    cam = make_camera(code="cam-ev-1")
    ev = make_vehicle_event(cam, plate="GJ01AB1111")
    # the long-lived session JWT must NOT work as ?token=
    r = client.get(f"/api/v1/vehicles/evidence/{ev.id}?token={token}")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "INVALID_MEDIA_TICKET"


def test_evidence_accepts_media_ticket_as_query_token(client, officer_user, make_camera, make_vehicle_event):
    _, token = officer_user
    cam = make_camera(code="cam-ev-2")
    ev = make_vehicle_event(cam, plate="GJ01AB2222")  # no snapshot_url -> 404, but auth passes first
    ticket = media_ticket(client, token)
    r = client.get(f"/api/v1/vehicles/evidence/{ev.id}?token={ticket}")
    # auth OK -> falls through to the "no snapshot" placeholder (200), not 401
    assert r.status_code == 200


def test_evidence_still_accepts_bearer_header(client, officer_user, make_camera, make_vehicle_event):
    _, token = officer_user
    cam = make_camera(code="cam-ev-3")
    ev = make_vehicle_event(cam, plate="GJ01AB3333")
    r = client.get(f"/api/v1/vehicles/evidence/{ev.id}", headers=bearer(token))
    assert r.status_code == 200  # auth passed; no snapshot -> placeholder


def test_ws_ticket_not_usable_for_media(client, officer_user, make_camera, make_vehicle_event):
    _, token = officer_user
    cam = make_camera(code="cam-ev-4")
    ev = make_vehicle_event(cam, plate="GJ01AB4444")
    ws = client.post("/api/v1/auth/ws-ticket", headers=bearer(token)).json()["ticket"]
    r = client.get(f"/api/v1/vehicles/evidence/{ev.id}?token={ws}")
    assert r.status_code == 401


def test_expired_media_ticket_rejected(client, officer_user, make_camera, make_vehicle_event):
    _, token = officer_user
    cam = make_camera(code="cam-ev-5")
    ev = make_vehicle_event(cam, plate="GJ01AB5555")
    expired = jwt.encode(
        {"sub": "u", "purpose": "media", "exp": datetime.now(timezone.utc) - timedelta(seconds=5)},
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    r = client.get(f"/api/v1/vehicles/evidence/{ev.id}?token={expired}")
    assert r.status_code == 401


def test_scoped_ticket_not_accepted_as_api_session(client, officer_user):
    """A media/ws ticket must never authenticate a normal REST call."""
    ticket = create_scoped_ticket(subject="u", purpose="media", ttl_seconds=60)
    r = client.get("/api/v1/watchlist", headers={"Authorization": f"Bearer {ticket}"})
    assert r.status_code == 401
