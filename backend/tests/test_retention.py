"""
Phase 4 -- vehicle_events data retention.

Covers: old events purged; recent events kept; an event referenced by an
alert is NEVER purged regardless of age; watchlist / alerts / audit_logs
untouched; retention_days<=0 disables; the admin endpoint is admin-only and
audit-logged.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.models.alert import Alert
from app.models.audit_log import AuditLog
from app.models.vehicle_event import VehicleEvent
from app.models.watchlist import Watchlist
from app.models.base import PriorityLevel
from app.services.retention import purge_old_vehicle_events
from conftest import bearer


def _count(db, model):
    return db.execute(select(func.count()).select_from(model)).scalar_one()


def test_purges_old_keeps_recent(db_session, make_camera, make_vehicle_event):
    cam = make_camera(code="cam-ret-1")
    old_id = make_vehicle_event(cam, plate="GJ01OLD001", track_id=1,
                                ts=datetime.utcnow() - timedelta(days=45)).id
    recent_id = make_vehicle_event(cam, plate="GJ01NEW001", track_id=2,
                                   ts=datetime.utcnow() - timedelta(days=5)).id

    deleted = purge_old_vehicle_events(db_session, retention_days=30)
    assert deleted == 1

    db_session.expire_all()
    remaining = db_session.execute(select(VehicleEvent.id)).scalars().all()
    assert recent_id in remaining
    assert old_id not in remaining


def test_alert_referenced_event_is_never_purged(db_session, make_camera, make_vehicle_event):
    cam = make_camera(code="cam-ret-2")
    ev = make_vehicle_event(cam, plate="GJ01WANTED1", track_id=3,
                            ts=datetime.utcnow() - timedelta(days=400))
    wl = Watchlist(plate_number="GJ01WANTED1", plate_number_normalized="GJ01WANTED1",
                   offense_category="STOLEN", priority_level=PriorityLevel.HIGH)
    db_session.add(wl)
    db_session.commit()
    db_session.refresh(wl)
    alert = Alert(
        plate_number="GJ01WANTED1", plate_number_normalized="GJ01WANTED1",
        camera_id=cam.id, vehicle_event_id=ev.id, watchlist_id=wl.id,
    )
    db_session.add(alert)
    db_session.commit()

    deleted = purge_old_vehicle_events(db_session, retention_days=30)
    assert deleted == 0  # the 400-day-old event is protected by its alert

    assert db_session.get(VehicleEvent, ev.id) is not None
    assert db_session.get(Alert, alert.id) is not None
    assert db_session.get(Watchlist, wl.id) is not None


def test_disabled_when_retention_days_zero(db_session, make_camera, make_vehicle_event):
    cam = make_camera(code="cam-ret-3")
    make_vehicle_event(cam, plate="GJ01OLD777", ts=datetime.utcnow() - timedelta(days=999))
    assert purge_old_vehicle_events(db_session, retention_days=0) == 0
    assert _count(db_session, VehicleEvent) == 1


def test_audit_logs_untouched_by_purge(db_session, make_camera, make_vehicle_event):
    cam = make_camera(code="cam-ret-4")
    make_vehicle_event(cam, plate="GJ01OLD888", ts=datetime.utcnow() - timedelta(days=90))
    db_session.add(AuditLog(action="LOGIN_SUCCESS", resource="auth"))
    db_session.commit()
    before = _count(db_session, AuditLog)
    purge_old_vehicle_events(db_session, retention_days=30)
    assert _count(db_session, AuditLog) == before


def test_admin_purge_endpoint_requires_admin(client, officer_user):
    _, token = officer_user
    assert client.post("/api/v1/admin/retention/purge", headers=bearer(token)).status_code == 403


def test_admin_purge_endpoint_runs_and_audits(client, admin_user, db_session, make_camera, make_vehicle_event):
    _, token = admin_user
    cam = make_camera(code="cam-ret-5")
    make_vehicle_event(cam, plate="GJ01OLD999", ts=datetime.utcnow() - timedelta(days=120))

    resp = client.post("/api/v1/admin/retention/purge", headers=bearer(token))
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 1

    actions = db_session.execute(select(AuditLog.action)).scalars().all()
    assert "RETENTION_PURGE" in actions
