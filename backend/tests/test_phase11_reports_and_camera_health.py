"""Phase 11: Reports Center (FEATURE 9) + Camera Health History (FEATURE 5/13)."""
from datetime import datetime, timedelta

from sqlalchemy import select

from app.database import SessionLocal
from app.models.base import CameraStatus, NotificationSeverity
from app.models.camera_health_history import CameraHealthHistory
from app.models.notification import Notification
from app.services.camera_health import record_transition_if_changed
from conftest import bearer


# --- Reports Center --------------------------------------------------------
def test_reports_list_and_csv_exports(client, officer_user, make_camera, make_vehicle_event):
    _, tok = officer_user
    cam = make_camera(code="cam-rep")
    for i in range(3):
        make_vehicle_event(cam, plate="GJ18TC0450", track_id=i,
                           ts=datetime.utcnow() - timedelta(hours=i))

    listed = client.get("/api/v1/reports", headers=bearer(tok)).json()
    keys = {r["key"] for r in listed}
    assert {"vehicle-detections", "watchlist-matches", "alerts", "incidents", "cases",
            "camera-activity", "camera-health", "vehicle-journey", "daily-summary"} <= keys

    for key in ("vehicle-detections", "camera-activity", "daily-summary", "incidents",
                "cases", "alerts", "watchlist-matches", "camera-health"):
        r = client.get(f"/api/v1/reports/{key}.csv", headers=bearer(tok))
        assert r.status_code == 200, (key, r.text)
        assert r.headers["content-type"].startswith("text/csv")

    dj = client.get("/api/v1/reports/vehicle-journey.csv", params={"plate": "GJ18TC0450"},
                    headers=bearer(tok))
    assert dj.status_code == 200 and "GJ18TC0450" in dj.text
    # journey without plate -> 400
    assert client.get("/api/v1/reports/vehicle-journey.csv", headers=bearer(tok)).status_code == 400
    # unknown report -> 404
    assert client.get("/api/v1/reports/not-a-report.csv", headers=bearer(tok)).status_code == 404
    assert client.get("/api/v1/reports/incidents.csv").status_code == 401

    with SessionLocal() as db:
        from app.models.audit_log import AuditLog
        assert db.execute(select(AuditLog).where(AuditLog.action == "REPORT_EXPORT")).first()


# --- Camera Health History + transitions ---------------------------------
def test_camera_health_transition_records_and_notifies(client, admin_user, make_camera):
    _, tok = admin_user
    cam = make_camera(code="cam-hh", status=CameraStatus.ONLINE)

    with SessionLocal() as db:
        c = db.get(type(cam), cam.id)
        # first ONLINE observation
        record_transition_if_changed(db, c, CameraStatus.ONLINE, source="test")
        # goes offline
        record_transition_if_changed(db, c, CameraStatus.OFFLINE, source="test")
        # stays offline -> no new row
        record_transition_if_changed(db, c, CameraStatus.OFFLINE, source="test")
        # recovers
        record_transition_if_changed(db, c, CameraStatus.ONLINE, source="test")

    with SessionLocal() as db:
        rows = db.execute(
            select(CameraHealthHistory).where(CameraHealthHistory.camera_id == cam.id)
            .order_by(CameraHealthHistory.detected_at)
        ).scalars().all()
        assert [r.status.value for r in rows] == ["ONLINE", "OFFLINE", "ONLINE"]
        assert rows[1].previous_status.value == "ONLINE"

        notifs = db.execute(select(Notification)).scalars().all()
        types = {n.type for n in notifs}
        assert "CAMERA_OFFLINE" in types
        assert "CAMERA_RECOVERED" in types

    hist = client.get(f"/api/v1/cameras/{cam.id}/health/history", headers=bearer(tok)).json()
    assert hist["total"] == 3
    assert hist["current_status"] in ("ONLINE", "OFFLINE", "DEGRADED")
    assert len(hist["transitions"]) == 3

    assert client.get(f"/api/v1/cameras/{cam.id}/health/history").status_code == 401


def test_health_history_unknown_camera_404(client, officer_user):
    assert client.get("/api/v1/cameras/nope/health/history",
                      headers=bearer(officer_user[1])).status_code == 404
