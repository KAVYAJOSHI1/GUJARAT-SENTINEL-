"""
Phase 14 (6/7) -- Camera Reliability Intelligence.

Covers: health-score computation, reliability label, degradation flag,
disconnect counting, recovery-time, stale heartbeat, FPS degradation,
never-reported camera, endpoints + ranking + auth.

NOT failure prediction -- the service only summarises recent stability.
"""
from datetime import datetime, timedelta

from app.models.base import CameraStatus
from app.models.camera_health_history import CameraHealthHistory
from app.services.ai.camera_reliability import CameraReliabilityService
from conftest import bearer


def _hist(db, cam, status, prev, when, *, fps=None, source="staleness_watcher"):
    db.add(CameraHealthHistory(
        camera_id=cam.id, status=status, previous_status=prev,
        detected_at=when, stream_fps=fps, source=source,
    ))


def _fresh(db, cam, *, fps=25.0, reconnects=0):
    cam.health_updated_at = datetime.utcnow()
    cam.status = CameraStatus.ONLINE
    cam.stream_fps = fps
    cam.reconnect_count = reconnects
    db.add(cam)
    db.commit()


# --------------------------------------------------------------------------- #
def test_healthy_camera_high_score(db_session, make_camera):
    cam = make_camera(code="CAM-OK", status=CameraStatus.ONLINE)
    _fresh(db_session, cam)
    a = CameraReliabilityService(db_session).assess_one("CAM-OK")
    assert a["reliability_score"] == "HIGH"
    assert a["health_score"] >= 80
    assert a["degradation_indicator"] is False


def test_disconnects_lower_score_and_flag_degradation(db_session, make_camera):
    cam = make_camera(code="CAM-FLAKY", status=CameraStatus.ONLINE)
    _fresh(db_session, cam)
    now = datetime.utcnow()
    for k in range(3):
        t = now - timedelta(hours=k + 1)
        _hist(db_session, cam, CameraStatus.OFFLINE, CameraStatus.ONLINE, t)
        _hist(db_session, cam, CameraStatus.ONLINE, CameraStatus.OFFLINE, t + timedelta(seconds=90))
    db_session.commit()

    a = CameraReliabilityService(db_session).assess_one("CAM-FLAKY")
    assert a["disconnect_count"] == 3
    assert a["health_score"] < 80
    assert a["reliability_score"] in ("LOW", "MEDIUM")
    assert a["degradation_indicator"] is True
    assert any("disconnect" in o for o in a["observations"])
    assert a["mean_recovery_seconds"] and 60 <= a["mean_recovery_seconds"] <= 120


def test_never_reported_camera_is_unknown(db_session, make_camera):
    make_camera(code="CAM-NEW", status=CameraStatus.OFFLINE)   # health_updated_at stays None
    a = CameraReliabilityService(db_session).assess_one("CAM-NEW")
    assert a["reliability_score"] == "UNKNOWN"
    assert a["health_score"] is None
    assert a["degradation_indicator"] is False


def test_stale_heartbeat_penalised(db_session, make_camera):
    cam = make_camera(code="CAM-STALE", status=CameraStatus.ONLINE)
    cam.health_updated_at = datetime.utcnow() - timedelta(minutes=5)
    cam.stream_fps = 25.0
    db_session.add(cam)
    db_session.commit()
    a = CameraReliabilityService(db_session).assess_one("CAM-STALE")
    assert a["heartbeat_stale"] is True
    assert any("heartbeat" in o for o in a["observations"])
    assert a["health_score"] <= 80


def test_fps_degraded(db_session, make_camera):
    cam = make_camera(code="CAM-SLOWFPS", status=CameraStatus.ONLINE)
    _fresh(db_session, cam, fps=2.0)
    a = CameraReliabilityService(db_session).assess_one("CAM-SLOWFPS")
    assert a["fps_degraded"] is True
    assert any("FPS" in o for o in a["observations"])


def test_assess_all_ranked_worst_first(db_session, make_camera):
    good = make_camera(code="CAM-G", status=CameraStatus.ONLINE)
    bad = make_camera(code="CAM-B", status=CameraStatus.ONLINE)
    make_camera(code="CAM-UNREP", status=CameraStatus.OFFLINE)   # never reported -> score None
    _fresh(db_session, good)
    _fresh(db_session, bad, fps=1.0, reconnects=9)
    now = datetime.utcnow()
    for k in range(4):
        t = now - timedelta(hours=k + 1)
        _hist(db_session, bad, CameraStatus.OFFLINE, CameraStatus.ONLINE, t)
    db_session.commit()

    res = CameraReliabilityService(db_session).assess_all()
    codes = [c["camera_code"] for c in res["cameras"]]
    assert codes.index("CAM-B") < codes.index("CAM-G")           # worst first
    assert codes.index("CAM-G") < codes.index("CAM-UNREP")       # never-reported last
    assert res["degraded_count"] >= 1


# ---- API ---------------------------------------------------------------- #
def test_camera_intelligence_endpoint(client, db_session, officer_user, make_camera):
    _, tok = officer_user
    cam = make_camera(code="CAM-EP1", status=CameraStatus.ONLINE)
    _fresh(db_session, cam)
    _hist(db_session, cam, CameraStatus.OFFLINE, CameraStatus.ONLINE,
          datetime.utcnow() - timedelta(hours=2))
    db_session.commit()

    r = client.get("/api/v1/ai/camera-intelligence", headers=bearer(tok))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["camera_count"] >= 1
    assert "NOT a failure prediction" in body["note"]

    r2 = client.get("/api/v1/ai/camera-intelligence/CAM-EP1", headers=bearer(tok))
    assert r2.status_code == 200
    assert r2.json()["transitions"] is not None


def test_camera_intelligence_unknown_404(client, officer_user):
    _, tok = officer_user
    assert client.get("/api/v1/ai/camera-intelligence/NOPE", headers=bearer(tok)).status_code == 404


def test_camera_intelligence_requires_auth(client):
    assert client.get("/api/v1/ai/camera-intelligence").status_code == 401
