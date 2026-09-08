"""
Phase 12 §4 — stopped/loitering vehicle anomaly detection.
Runs on stored ByteTrack events; feeds the EXISTING alert architecture.
"""
from datetime import datetime, timedelta

from sqlalchemy import select

from app.database import SessionLocal
from app.models.alert import Alert
from app.models.anomaly_event import AnomalyEvent
from app.models.audit_log import AuditLog
from app.models.base import AlertSource
from app.models.notification import Notification
from app.models.vehicle_event import VehicleEvent
from app.services.ai.behavior import BehaviorAnalyticsService
from app.services.plate_utils import normalize_plate
from conftest import bearer


def _track(db, _mk_ev, cam, *, track_id, n, start, step_s, dlat=0.0, dlon=0.0, plate="GJ01AB1234"):
    norm = normalize_plate(plate)
    for i in range(n):
        lat = 23.02 + i * dlat
        lon = 72.57 + i * dlon
        db.add(VehicleEvent(
            plate_number=plate, plate_number_normalized=norm,
            camera_id=cam.id, camera_code=cam.code, track_id=track_id,
            timestamp=start + timedelta(seconds=i * step_s),
            confidence_score=0.9, latitude=lat, longitude=lon,
            location=f"SRID=4326;POINT({lon} {lat})",
        ))
    db.commit()


def test_stopped_vehicle_flagged_and_alert_created(client, officer_user, make_camera, make_vehicle_event):
    _, tok = officer_user
    cam = make_camera(code="CAM-04", lat=23.02, lon=72.57)
    start = datetime.utcnow() - timedelta(minutes=30)
    with SessionLocal() as db:
        # 15 detections over 210s, barely moving -> STOPPED
        _track(db, make_vehicle_event, cam, track_id=777, n=15, start=start, step_s=15)
        res = BehaviorAnalyticsService(db).scan_stopped_vehicles()
        assert res["created"] == 1
        a = res["anomalies"][0]
        anomaly_id = a.id
        assert a.kind.value == "STOPPED_VEHICLE"
        assert a.duration_seconds >= 120
        assert a.detection_count == 15
        assert a.confidence_level.value in ("HIGH", "MEDIUM", "LOW")
        assert "AI-assisted anomaly" in a.reasoning

    with SessionLocal() as db:
        alert = db.execute(select(Alert).where(Alert.anomaly_event_id == anomaly_id)).scalar_one()
        assert alert.source == AlertSource.ANOMALY
        assert alert.watchlist_id is None
        notifs = db.execute(select(Notification).where(Notification.type == "ANOMALY_STOPPED_VEHICLE")).all()
        assert len(notifs) == 1

    # re-scan is idempotent
    with SessionLocal() as db:
        res2 = BehaviorAnalyticsService(db).scan_stopped_vehicles()
    assert res2["created"] == 0 and res2["already_flagged"] == 1

    # the ANOMALY alert shows in the normal alert feed (regression: AlertRead
    # must tolerate watchlist_id = NULL)
    feed = client.get("/api/v1/alerts", headers=bearer(tok))
    assert feed.status_code == 200
    anon = next((x for x in feed.json() if x["source"] == "ANOMALY"), None)
    assert anon is not None and anon["watchlist_id"] is None
    assert anon["anomaly_event_id"] == anomaly_id


def test_moving_vehicle_not_flagged(client, make_camera, make_vehicle_event):
    cam = make_camera(code="CAM-09", lat=23.02, lon=72.57)
    start = datetime.utcnow() - timedelta(minutes=20)
    with SessionLocal() as db:
        # 15 detections over 210s but travelling ~1.3 km -> NOT stopped
        _track(db, make_vehicle_event, cam, track_id=888, n=15, start=start, step_s=15,
               dlat=0.0008, dlon=0.0008, plate="GJ02CD5678")
        res = BehaviorAnalyticsService(db).scan_stopped_vehicles()
    assert res["created"] == 0


def test_short_dwell_not_flagged(client, make_camera, make_vehicle_event):
    cam = make_camera(code="CAM-10", lat=23.02, lon=72.57)
    start = datetime.utcnow() - timedelta(minutes=5)
    with SessionLocal() as db:
        # 8 detections over only 56s -> below the duration threshold
        _track(db, make_vehicle_event, cam, track_id=999, n=8, start=start, step_s=8,
               plate="GJ03EF9012")
        res = BehaviorAnalyticsService(db).scan_stopped_vehicles()
    assert res["created"] == 0


def test_scan_endpoint_rbac_and_review(client, admin_user, officer_user, operator_user,
                                       make_camera, make_vehicle_event):
    _, admin = admin_user
    cam = make_camera(code="CAM-11", lat=23.02, lon=72.57)
    start = datetime.utcnow() - timedelta(minutes=25)
    with SessionLocal() as db:
        _track(db, make_vehicle_event, cam, track_id=1234, n=12, start=start, step_s=20,
               plate="GJ07GH3456")

    assert client.post("/api/v1/ai/anomalies/scan", json={}, headers=bearer(operator_user[1])).status_code == 403
    r = client.post("/api/v1/ai/anomalies/scan", json={}, headers=bearer(admin))
    assert r.status_code == 200 and r.json()["created"] == 1
    anomaly_id = r.json()["anomalies"][0]["id"]

    lst = client.get("/api/v1/ai/anomalies", headers=bearer(officer_user[1])).json()
    assert lst["total"] == 1 and lst["items"][0]["camera_code"] == "CAM-11"

    rev = client.post(f"/api/v1/ai/anomalies/{anomaly_id}/review", json={"status": "DISMISSED"},
                      headers=bearer(admin))
    assert rev.status_code == 200 and rev.json()["status"] == "DISMISSED"
    assert rev.json()["reviewed_by_username"] == "test_admin"

    with SessionLocal() as db:
        acts = {x.action for x in db.execute(select(AuditLog)).scalars()}
    assert {"AI_ANOMALY_SCAN", "AI_ANOMALY_REVIEW"} <= acts
