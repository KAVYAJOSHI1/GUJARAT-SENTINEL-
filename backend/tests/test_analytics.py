"""
Phase 5 -- GET /api/v1/analytics/overview.

Covers: real aggregates (by type / by camera / top plates), UNKNOWN
exclusion from top plates, watchlist-match counts, auth required, and an
empty database returning zeros rather than erroring.
"""
from datetime import datetime, timedelta

from app.models.base import PriorityLevel
from app.models.watchlist import Watchlist
from app.models.alert import Alert
from conftest import bearer


def _overview(client, token, **params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    url = "/api/v1/analytics/overview" + (f"?{q}" if q else "")
    return client.get(url, headers=bearer(token))


def test_requires_auth(client):
    assert client.get("/api/v1/analytics/overview").status_code == 401


def test_empty_db_returns_zeros_not_error(client, officer_user):
    _, token = officer_user
    resp = _overview(client, token)
    assert resp.status_code == 200
    b = resp.json()
    assert b["total_events"] == 0
    assert b["detections_by_type"] == []
    assert b["detections_by_camera"] == []
    assert b["top_plates"] == []
    assert b["watchlist_matches_total"] == 0


def test_detections_by_type_and_camera(client, officer_user, make_camera, make_vehicle_event):
    _, token = officer_user
    c1 = make_camera(code="cam-an-1")
    c2 = make_camera(code="cam-an-2")
    now = datetime.utcnow()
    for i in range(3):
        make_vehicle_event(c1, plate=f"GJ10CAR{i:02d}", track_id=i, ts=now, vehicle_type="car")
    make_vehicle_event(c2, plate="GJ10BUS01", track_id=9, ts=now, vehicle_type="bus")

    b = _overview(client, token).json()
    by_type = {r["label"]: r["count"] for r in b["detections_by_type"]}
    assert by_type["car"] == 3
    assert by_type["bus"] == 1

    by_cam = {r["label"]: r["count"] for r in b["detections_by_camera"]}
    assert by_cam["cam-an-1"] == 3
    assert by_cam["cam-an-2"] == 1


def test_top_plates_excludes_unknown(client, officer_user, make_camera, make_vehicle_event):
    _, token = officer_user
    cam = make_camera(code="cam-an-3")
    now = datetime.utcnow()
    for i in range(4):
        make_vehicle_event(cam, plate="GJ11SEEN01", track_id=i, ts=now)
    for i in range(6):
        make_vehicle_event(cam, plate="UNKNOWN", track_id=100 + i, ts=now)

    b = _overview(client, token).json()
    labels = [r["label"] for r in b["top_plates"]]
    assert "GJ11SEEN01" in labels
    assert "UNKNOWN" not in labels
    top = next(r for r in b["top_plates"] if r["label"] == "GJ11SEEN01")
    assert top["count"] == 4
    assert b["unknown_reads_in_window"] == 6
    assert b["readable_reads_in_window"] == 4


def test_watchlist_match_counts(client, officer_user, make_camera, make_vehicle_event, db_session):
    _, token = officer_user
    cam = make_camera(code="cam-an-4")
    ev = make_vehicle_event(cam, plate="GJ12WANT01")
    wl = Watchlist(plate_number="GJ12WANT01", plate_number_normalized="GJ12WANT01",
                   offense_category="STOLEN", priority_level=PriorityLevel.HIGH)
    db_session.add(wl)
    db_session.commit()
    db_session.refresh(wl)
    db_session.add(Alert(
        plate_number="GJ12WANT01", plate_number_normalized="GJ12WANT01",
        camera_id=cam.id, vehicle_event_id=ev.id, watchlist_id=wl.id,
    ))
    db_session.commit()

    b = _overview(client, token).json()
    assert b["watchlist_matches_total"] == 1
    assert b["watchlist_matches_in_window"] == 1
    assert b["active_alerts"] == 1


def test_window_filter_excludes_old_events(client, officer_user, make_camera, make_vehicle_event):
    _, token = officer_user
    cam = make_camera(code="cam-an-5")
    make_vehicle_event(cam, plate="GJ13OLD001", track_id=1, ts=datetime.utcnow() - timedelta(days=10))
    make_vehicle_event(cam, plate="GJ13NEW001", track_id=2, ts=datetime.utcnow())

    b = _overview(client, token, window_hours=24).json()
    assert b["total_events"] == 2               # all-time
    assert b["total_events_in_window"] == 1     # windowed
    labels = [r["label"] for r in b["top_plates"]]
    assert labels == ["GJ13NEW001"]
