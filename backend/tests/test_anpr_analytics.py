"""
Phase 15H §10 -- ANPR performance dashboard data + §12 feed-source flags.
"""
from datetime import datetime, timedelta

from app.services.feed_source import feed_source
from conftest import bearer


def _seed(mk, db, cam, n_ok, n_fail, base, reason="BLUR"):
    for i in range(n_ok):
        ev = mk(cam, plate=f"GJ01AB{1000+i}", track_id=i + 1, ts=base + timedelta(minutes=i))
        ev.confidence_score = 0.85
        ev.anpr_quality_score = 0.8
        db.add(ev)
    for i in range(n_fail):
        ev = mk(cam, plate="UNKNOWN", track_id=100 + i, ts=base + timedelta(minutes=i))
        ev.anpr_status = "UNKNOWN"
        ev.anpr_failure_reason = reason
        ev.anpr_quality_score = 0.3
        db.add(ev)
    db.commit()


def test_anpr_analytics_summary(client, db_session, officer_user, make_camera, make_vehicle_event):
    _, tok = officer_user
    a = make_camera(code="CAM-A")
    b = make_camera(code="CAM-B")
    now = datetime.utcnow()
    _seed(make_vehicle_event, db_session, a, 8, 2, now - timedelta(minutes=30))
    _seed(make_vehicle_event, db_session, b, 2, 8, now - timedelta(minutes=20), reason="LOW_RESOLUTION")

    r = client.get("/api/v1/analytics/anpr", params={"window_hours": 6}, headers=bearer(tok))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["total_vehicles"] == 20
    assert d["readable_plates"] == 10
    assert d["success_rate"] == 0.5
    assert d["failure_reasons"]["BLUR"] == 2
    assert d["failure_reasons"]["LOW_RESOLUTION"] == 8
    assert d["low_quality_frames"] == 10
    # worst camera is CAM-B (20% success), best is CAM-A (80%)
    assert d["worst_cameras"][0]["camera_code"] == "CAM-B"
    assert d["top_cameras"][0]["camera_code"] == "CAM-A"
    assert len(d["confidence_distribution"]) == 10
    assert any(h["total"] > 0 for h in d["by_hour"])
    assert "NOT an accuracy measurement" in d["disclaimer"]


def test_anpr_analytics_camera_filter(client, db_session, officer_user, make_camera, make_vehicle_event):
    _, tok = officer_user
    a = make_camera(code="CAM-F1")
    b = make_camera(code="CAM-F2")
    now = datetime.utcnow()
    _seed(make_vehicle_event, db_session, a, 5, 0, now - timedelta(minutes=10))
    _seed(make_vehicle_event, db_session, b, 0, 5, now - timedelta(minutes=10))
    d = client.get("/api/v1/analytics/anpr", params={"camera_code": "CAM-F1"}, headers=bearer(tok)).json()
    assert d["total_vehicles"] == 5
    assert d["success_rate"] == 1.0


def test_anpr_analytics_requires_auth(client):
    assert client.get("/api/v1/analytics/anpr").status_code == 401


# ---- §12 feed source ---------------------------------------------------- #
def test_feed_source_derivation():
    assert feed_source(is_demo=True, code="CAM-01") == "DEMO"
    assert feed_source(is_demo=False, code="mockcam01") == "MOCK"
    assert feed_source(is_demo=False, code="MOCK_CAM02") == "MOCK"
    assert feed_source(is_demo=False, code="cam04") == "REAL"
    assert feed_source(is_demo=True, code="mockcam01") == "DEMO"   # demo wins


def test_camera_read_carries_feed_source(client, db_session, admin_user, make_camera):
    _, tok = admin_user
    cam = make_camera(code="cam-real-x")
    cam.is_demo = False
    db_session.add(cam)
    db_session.commit()
    cams = client.get("/api/v1/cameras", headers=bearer(tok)).json()
    row = next(c for c in cams if c["code"] == "cam-real-x")
    assert row["feed_source"] == "REAL"
    assert row["is_demo"] is False

    cam.is_demo = True
    db_session.add(cam)
    db_session.commit()
    cams = client.get("/api/v1/cameras", headers=bearer(tok)).json()
    row = next(c for c in cams if c["code"] == "cam-real-x")
    assert row["feed_source"] == "DEMO"


def test_stream_profile_carries_feed_source(client, db_session, officer_user, make_camera):
    _, tok = officer_user
    cam = make_camera(code="MOCK_CAM77")
    r = client.get(f"/api/v1/cameras/{cam.id}/stream", headers=bearer(tok)).json()
    assert r["feed_source"] == "MOCK"
