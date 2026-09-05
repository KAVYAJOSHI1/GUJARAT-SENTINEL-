"""
Audit logging (SENTINEL_System_Audit_Report.md §10/§15 — "AuditLog model is
dead code... zero writers"). Proves rows are actually created for the
actions this hardening pass wired up, and that a broken audit write can
never take down the primary flow it's attached to.
"""
from datetime import datetime

from sqlalchemy import select

from app.config import settings
from app.core.security import hash_password
from app.database import SessionLocal
from app.models.audit_log import AuditLog
from app.models.base import UserRole
from app.models.user import User
from conftest import bearer


def _rows(action):
    """A fresh session bound to the same engine the app used -- audit rows
    are committed independently of whatever session a fixture is holding."""
    with SessionLocal() as s:
        return s.execute(select(AuditLog).where(AuditLog.action == action)).scalars().all()


def test_login_success_is_audited(client):
    user = User(
        username="audit_login",
        email="audit_login@example.test",
        hashed_password=hash_password("Password123!"),
        role=UserRole.OPERATOR,
    )
    with SessionLocal() as s:
        s.add(user)
        s.commit()
        s.refresh(user)

    resp = client.post("/api/v1/auth/login", json={"username": "audit_login", "password": "Password123!"})
    assert resp.status_code == 200

    rows = _rows("LOGIN_SUCCESS")
    assert len(rows) == 1
    assert rows[0].user_id == user.id


def test_login_failure_is_audited_without_storing_password(client):
    resp = client.post("/api/v1/auth/login", json={"username": "nobody", "password": "wrong-pw"})
    assert resp.status_code == 401

    rows = _rows("LOGIN_FAILED")
    assert len(rows) == 1
    assert "wrong-pw" not in (rows[0].detail or "")


def test_vehicle_search_is_audited(client, officer_user, make_camera, make_vehicle_event):
    _, token = officer_user
    camera = make_camera(code="cam-audit-01")
    make_vehicle_event(camera, plate="GJ01AB1234")

    resp = client.get("/api/v1/vehicles/search", params={"plate": "GJ01AB1234"}, headers=bearer(token))
    assert resp.status_code == 200
    assert _rows("VEHICLE_SEARCH")


def test_alert_ack_is_audited(client, officer_user, make_camera):
    _, token = officer_user
    camera = make_camera(code="cam-audit-02")

    client.post(
        "/api/v1/watchlist",
        json={"plate_number": "GJ11ZZ9999", "offense_category": "STOLEN"},
        headers=bearer(token),
    )
    ingest = client.post(
        "/api/v1/events/ai-detection",
        json={
            "camera_id": camera.code,
            "timestamp": datetime.utcnow().isoformat(),
            "plate_number": "GJ11ZZ9999",
            "track_id": 5,
        },
        headers={"X-Ingest-Key": settings.INGEST_API_KEY},
    )
    alert_id = ingest.json()["alert_id"]
    assert alert_id

    resp = client.patch(f"/api/v1/alerts/{alert_id}", json={"status": "ACKNOWLEDGED"}, headers=bearer(token))
    assert resp.status_code == 200
    assert _rows("ALERT_ACKNOWLEDGED")


def test_watchlist_create_and_deactivate_are_audited(client, admin_user):
    _, token = admin_user
    resp = client.post(
        "/api/v1/watchlist",
        json={"plate_number": "GJ22QQ1111", "offense_category": "TRAFFIC"},
        headers=bearer(token),
    )
    assert resp.status_code == 201
    entry_id = resp.json()["id"]
    assert _rows("WATCHLIST_CREATED")

    del_resp = client.delete(f"/api/v1/watchlist/{entry_id}", headers=bearer(token))
    assert del_resp.status_code == 204
    assert _rows("WATCHLIST_DEACTIVATED")


def test_camera_crud_is_audited(client, admin_user):
    _, token = admin_user
    create = client.post(
        "/api/v1/cameras",
        json={"name": "Test Cam", "code": "cam-audit-crud", "latitude": 23.0, "longitude": 72.5},
        headers=bearer(token),
    )
    assert create.status_code == 201
    cam_id = create.json()["id"]
    assert _rows("CAMERA_CREATED")

    upd = client.patch(f"/api/v1/cameras/{cam_id}", json={"name": "Renamed"}, headers=bearer(token))
    assert upd.status_code == 200
    assert _rows("CAMERA_UPDATED")

    delete = client.delete(f"/api/v1/cameras/{cam_id}", headers=bearer(token))
    assert delete.status_code == 204
    assert _rows("CAMERA_DELETED")


def test_camera_sync_is_audited(client, admin_user):
    _, token = admin_user
    resp = client.post(
        "/api/v1/cameras/sync",
        json=[{"code": "cam-audit-sync-01", "name": "Synced Cam"}],
        headers=bearer(token),
    )
    assert resp.status_code == 200
    assert _rows("CAMERA_SYNC")


def test_evidence_access_is_audited(client, officer_user, make_camera, make_vehicle_event):
    _, token = officer_user
    camera = make_camera(code="cam-audit-03")
    ev = make_vehicle_event(camera, plate="GJ33AA0000", snapshot_url="file:///nonexistent/does-not-exist.jpg")

    # A 404 (no real file on disk in this test) is fine -- the audit write
    # happens before the file lookup, and must survive that failure too.
    client.get(f"/api/v1/vehicles/evidence/{ev.id}", headers=bearer(token))
    assert _rows("EVIDENCE_ACCESSED")


def test_audit_write_failure_never_crashes_the_caller(client, officer_user, monkeypatch):
    """A broken AuditLog write must never surface as an error on the real
    action it's attached to -- record_audit() catches everything internally
    (app/services/audit.py). Simulate the DB write itself failing (not
    record_audit's own try/except, which is the thing under test) by making
    the AuditLog row constructor blow up."""
    _, token = officer_user

    import app.services.audit as audit_module

    class _BoomAuditLog:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("simulated audit backend failure")

    monkeypatch.setattr(audit_module, "AuditLog", _BoomAuditLog, raising=True)

    resp = client.get("/api/v1/vehicles/search", params={"plate": "GJZZZZ0000"}, headers=bearer(token))
    assert resp.status_code == 200
