"""
Notification center (phase brief FEATURE 12).

Rules proven here:
  * notifications are produced only by REAL backend events (an alert row
    actually created via the ingest path) -- never fabricated / never on a
    timer;
  * broadcast vs directed visibility;
  * read / read-all / unread-count.
"""
from datetime import datetime

from sqlalchemy import select

from app.database import SessionLocal
from app.models.base import PriorityLevel
from app.models.notification import Notification
from app.models.watchlist import Watchlist
from conftest import bearer


def test_no_events_means_no_notifications(client, operator_user):
    _, token = operator_user
    body = client.get("/api/v1/notifications", headers=bearer(token)).json()
    assert body["total"] == 0
    assert body["unread"] == 0
    assert client.get("/api/v1/notifications/unread-count", headers=bearer(token)).json()["unread"] == 0


def test_watchlist_match_creates_one_notification(client, admin_user, make_camera):
    _, token = admin_user
    cam = make_camera(code="cam04")
    with SessionLocal() as s:
        s.add(Watchlist(plate_number="GJ18TC0450", plate_number_normalized="GJ18TC0450",
                        offense_category="STOLEN", priority_level=PriorityLevel.CRITICAL))
        s.commit()

    payload = {
        "camera_id": "cam04",
        "plate_number": "GJ18TC0450",
        "timestamp": datetime.utcnow().isoformat(),
        "confidence": 0.95,
    }
    r = client.post("/api/v1/events/ai-detection", json=payload,
                    headers={"X-Ingest-Key": "test-ingest-key"})
    assert r.status_code == 201, r.text
    assert r.json()["watchlist_match"] is True

    with SessionLocal() as s:
        rows = s.execute(
            select(Notification).where(Notification.type == "WATCHLIST_MATCH")
        ).scalars().all()
    assert len(rows) == 1
    assert rows[0].severity.value == "CRITICAL"
    assert rows[0].resource == "alert"

    body = client.get("/api/v1/notifications", headers=bearer(token)).json()
    assert body["unread"] == 1


def test_directed_notification_only_visible_to_target(client, admin_user, officer_user):
    _, admin_token = admin_user
    officer, officer_token = officer_user
    inc = client.post("/api/v1/incidents", json={"title": "x"}, headers=bearer(admin_token)).json()
    client.post(f"/api/v1/incidents/{inc['id']}/assign", json={"user_id": officer.id},
                headers=bearer(admin_token))

    seen_by_officer = client.get("/api/v1/notifications", headers=bearer(officer_token)).json()
    assert any(n["type"] == "INCIDENT_ASSIGNED" for n in seen_by_officer["items"])

    # a different operator must not see the officer's directed notification
    seen_by_admin = client.get("/api/v1/notifications", headers=bearer(admin_token)).json()
    assert not any(n["type"] == "INCIDENT_ASSIGNED" for n in seen_by_admin["items"])


def test_mark_read_and_read_all(client, admin_user, officer_user):
    _, admin_token = admin_user
    officer, _ = officer_user
    for i in range(3):
        client.post("/api/v1/incidents", json={"title": f"i{i}", "priority_level": "CRITICAL"},
                    headers=bearer(admin_token))
    body = client.get("/api/v1/notifications", headers=bearer(admin_token)).json()
    assert body["unread"] >= 3
    first = body["items"][0]["id"]

    r = client.post(f"/api/v1/notifications/{first}/read", headers=bearer(admin_token))
    assert r.json()["read"] is True and r.json()["read_at"] is not None

    r = client.post("/api/v1/notifications/read-all", headers=bearer(admin_token))
    assert r.json()["unread"] == 0
    assert client.get("/api/v1/notifications/unread-count",
                      headers=bearer(admin_token)).json()["unread"] == 0


def test_notifications_require_auth(client):
    assert client.get("/api/v1/notifications").status_code == 401
