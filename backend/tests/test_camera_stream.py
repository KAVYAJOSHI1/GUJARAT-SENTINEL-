"""
Phase 15A -- camera playback abstraction.

Covers: LIVE / DEGRADED / RECORDED / OFFLINE mode resolution, the
webrtc -> hls -> recorded -> snapshot fallback order, "a snapshot is never
a live feed", the /stream endpoint + auth, and hls_url/webrtc_url plumbing
through create / update / read.
"""
from datetime import datetime, timedelta

from app.models.base import CameraStatus
from app.services.camera_stream import CameraStreamService
from conftest import bearer


def _fresh(db, cam, *, fps=25.0):
    cam.health_updated_at = datetime.utcnow()
    cam.status = CameraStatus.ONLINE
    cam.stream_fps = fps
    db.add(cam)
    db.commit()


def test_live_when_realtime_source_and_fresh(db_session, make_camera):
    cam = make_camera(code="CAM-L", status=CameraStatus.ONLINE,
                      webrtc_url="https://gw.local/whep/cam-l")
    _fresh(db_session, cam)
    p = CameraStreamService(db_session).profile(cam)
    assert p["mode"] == "LIVE"
    assert p["primary_source"] == "webrtc"
    assert p["sources"][0]["realtime"] is True


def test_degraded_when_stale_health(db_session, make_camera):
    cam = make_camera(code="CAM-D", status=CameraStatus.ONLINE,
                      hls_url="https://gw.local/hls/cam-d.m3u8")
    cam.health_updated_at = datetime.utcnow() - timedelta(minutes=3)
    cam.stream_fps = 25.0
    db_session.add(cam)
    db_session.commit()
    p = CameraStreamService(db_session).profile(cam)
    assert p["mode"] == "DEGRADED"
    assert any("stalled" in r or "health" in r for r in p["mode_reasons"])


def test_degraded_when_low_fps(db_session, make_camera):
    cam = make_camera(code="CAM-LF", status=CameraStatus.ONLINE,
                      hls_url="https://gw.local/hls/cam-lf.m3u8")
    _fresh(db_session, cam, fps=3.0)
    p = CameraStreamService(db_session).profile(cam)
    assert p["mode"] == "DEGRADED"


def test_recorded_when_only_mock_clip(db_session, make_camera):
    cam = make_camera(code="MOCK_CAM09", status=CameraStatus.ONLINE)
    _fresh(db_session, cam)
    p = CameraStreamService(db_session).profile(cam)
    assert p["mode"] == "RECORDED"
    assert p["primary_source"] == "recorded"
    assert p["is_mock"] is True
    assert any("recorded" in r or "real-time" in r for r in p["mode_reasons"])


def test_offline_camera_with_no_source(db_session, make_camera):
    cam = make_camera(code="CAM-OFF", status=CameraStatus.OFFLINE)
    p = CameraStreamService(db_session).profile(cam)
    assert p["mode"] == "OFFLINE"
    assert p["sources"] == []
    assert "never a live feed" in p["note"] or "never" in p["note"].lower()


def test_snapshot_is_never_labelled_live(db_session, make_camera, make_vehicle_event):
    cam = make_camera(code="CAM-SNAP", status=CameraStatus.ONLINE)
    _fresh(db_session, cam)
    ev = make_vehicle_event(cam, plate="GJ01AB1234")
    ev.snapshot_url = "file:///evidence/x.jpg"
    db_session.add(ev)
    db_session.commit()
    p = CameraStreamService(db_session).profile(cam)
    snap = [s for s in p["sources"] if s["kind"] == "snapshot"]
    assert snap and snap[0]["realtime"] is False
    # online + only a snapshot (no realtime) -> RECORDED, not LIVE
    assert p["mode"] == "RECORDED"


def test_fallback_order(db_session, make_camera, make_vehicle_event):
    cam = make_camera(code="MOCK_CAM10", status=CameraStatus.ONLINE,
                      webrtc_url="w://x", hls_url="h://x")
    _fresh(db_session, cam)
    ev = make_vehicle_event(cam, plate="GJ01AB0000")
    ev.snapshot_url = "file:///e/y.jpg"
    db_session.add(ev)
    db_session.commit()
    kinds = [s["kind"] for s in CameraStreamService(db_session).profile(cam)["sources"]]
    assert kinds == ["webrtc", "hls", "recorded", "snapshot"]


# ---- API ---------------------------------------------------------------- #
def test_stream_endpoint(client, db_session, officer_user, make_camera):
    _, tok = officer_user
    cam = make_camera(code="CAM-EP", status=CameraStatus.ONLINE,
                      hls_url="https://gw/hls/ep.m3u8")
    _fresh(db_session, cam)
    r = client.get(f"/api/v1/cameras/{cam.id}/stream", headers=bearer(tok))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] in ("LIVE", "DEGRADED")
    assert body["camera_code"] == "CAM-EP"


def test_stream_endpoint_requires_auth(client, make_camera):
    cam = make_camera(code="CAM-NA")
    assert client.get(f"/api/v1/cameras/{cam.id}/stream").status_code == 401


def test_stream_urls_roundtrip_create_update_read(client, admin_user):
    _, tok = admin_user
    r = client.post("/api/v1/cameras", headers=bearer(tok), json={
        "name": "GW cam", "code": "CAM-GW", "latitude": 23.0, "longitude": 72.5,
        "hls_url": "https://gw/hls/gw.m3u8", "webrtc_url": "https://gw/whep/gw",
    })
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    assert r.json()["hls_url"] == "https://gw/hls/gw.m3u8"

    r2 = client.patch(f"/api/v1/cameras/{cid}", headers=bearer(tok),
                      json={"webrtc_url": "https://gw/whep/gw2"})
    assert r2.status_code == 200
    assert r2.json()["webrtc_url"] == "https://gw/whep/gw2"
