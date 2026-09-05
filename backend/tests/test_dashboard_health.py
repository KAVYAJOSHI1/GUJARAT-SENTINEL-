"""
Phase 7 -- GET /api/v1/dashboard/health command-center observability aggregate.

Covers: DB probe, camera online/degraded/offline/stale counts, AI-pipeline
status (unknown / online / stale), event-flow freshness, alert counts.
Every value is a real measurement or NULL -- never a placeholder.
"""
from datetime import datetime, timedelta

from app.models.base import AlertStatus, CameraStatus, PriorityLevel
from app.models.alert import Alert
from app.models.watchlist import Watchlist
from conftest import bearer


def _health(client, token):
    r = client.get("/api/v1/dashboard/health", headers=bearer(token))
    assert r.status_code == 200
    return r.json()


def test_requires_auth(client):
    assert client.get("/api/v1/dashboard/health").status_code == 401


def test_shape_and_db_probe(client, operator_user):
    _, token = operator_user
    b = _health(client, token)
    assert b["backend"]["status"] == "ok"
    assert b["database"]["status"] == "ok"
    assert b["database"]["latency_ms"] is not None and b["database"]["latency_ms"] >= 0
    assert b["ai_pipeline"]["status"] == "unknown"  # nothing reported yet
    assert b["ai_pipeline"]["processed_fps"] is None
    assert b["cameras"]["total"] == 0
    assert b["alerts"]["total"] == 0


def test_camera_counts_by_effective_status(client, operator_user, make_camera, db_session):
    _, token = operator_user
    now = datetime.utcnow()
    # fresh ONLINE
    c1 = make_camera(code="cam-h-1", status=CameraStatus.ONLINE)
    c1.health_updated_at = now
    # fresh DEGRADED
    c2 = make_camera(code="cam-h-2", status=CameraStatus.DEGRADED)
    c2.health_updated_at = now
    # ONLINE but STALE health -> effective OFFLINE + counted stale
    c3 = make_camera(code="cam-h-3", status=CameraStatus.ONLINE)
    c3.health_updated_at = now - timedelta(minutes=5)
    # never reported
    make_camera(code="cam-h-4", status=CameraStatus.OFFLINE)
    db_session.add_all([c1, c2, c3])
    db_session.commit()

    cams = _health(client, token)["cameras"]
    assert cams["total"] == 4
    assert cams["online"] == 1
    assert cams["degraded"] == 1
    assert cams["offline"] == 2          # c3 (stale->offline) + c4 (never, offline)
    assert cams["stale"] == 1            # c3
    assert cams["never_reported"] == 1   # c4


def test_ai_pipeline_status_online_then_stale(client, operator_user, db_session):
    _, token = operator_user
    from app.models.pipeline_status import PipelineStatus

    # fresh report -> "online"
    db_session.add(PipelineStatus(service_id="default", reported_at=datetime.utcnow(),
                                  processed_fps=1.4, events_generated=10))
    db_session.commit()
    ap = _health(client, token)["ai_pipeline"]
    assert ap["status"] == "online"
    assert ap["processed_fps"] == 1.4

    # old report -> "stale"
    row = db_session.get(PipelineStatus, "default")
    row.reported_at = datetime.utcnow() - timedelta(minutes=2)
    db_session.add(row)
    db_session.commit()
    assert _health(client, token)["ai_pipeline"]["status"] == "stale"


def test_event_flow_and_alert_counts(client, officer_user, make_camera, make_vehicle_event, db_session):
    _, token = officer_user
    cam = make_camera(code="cam-h-ev")
    make_vehicle_event(cam, plate="GJ01FRESH1", track_id=1, ts=datetime.utcnow())
    make_vehicle_event(cam, plate="UNKNOWN", track_id=2, ts=datetime.utcnow())
    make_vehicle_event(cam, plate="GJ01OLD001", track_id=3, ts=datetime.utcnow() - timedelta(hours=2))

    ev = make_vehicle_event(cam, plate="GJ01WANT01", track_id=9, ts=datetime.utcnow())
    wl = Watchlist(plate_number="GJ01WANT01", plate_number_normalized="GJ01WANT01",
                   offense_category="STOLEN", priority_level=PriorityLevel.HIGH)
    db_session.add(wl); db_session.commit(); db_session.refresh(wl)
    db_session.add(Alert(plate_number="GJ01WANT01", plate_number_normalized="GJ01WANT01",
                         camera_id=cam.id, vehicle_event_id=ev.id, watchlist_id=wl.id,
                         status=AlertStatus.NEW, priority_level=PriorityLevel.HIGH))
    db_session.commit()

    b = _health(client, token)
    assert b["events"]["events_last_15min"] == 3     # 2 fresh + the alert event; the 2h-old one excluded
    assert b["events"]["readable_last_15min"] == 2
    assert b["events"]["unknown_last_15min"] == 1
    assert b["events"]["last_event_age_seconds"] is not None
    assert b["alerts"]["total"] == 1
    assert b["alerts"]["active"] == 1
    assert b["alerts"]["high_or_critical_active"] == 1
