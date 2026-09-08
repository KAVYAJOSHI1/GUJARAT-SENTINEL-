"""
Phase 14 (4/7) -- expanded behaviour analytics: wrong-way movement +
restricted-zone entry.

Covers: positive + negative detection, thresholds, idempotency, both-kinds-
same-track, the scan dispatcher, the scan endpoint `kinds` filter, the
camera behaviour-config endpoint + RBAC, and that the existing
stopped-vehicle detector is unaffected.
"""
from datetime import datetime, timedelta

from app.models.anomaly_event import AnomalyEvent
from app.models.base import AnomalyKind
from app.services.ai.behavior import BehaviorAnalyticsService
from conftest import bearer
from sqlalchemy import select


def _track(mk, cam, plate, track_id, pts, base, *, step=20):
    """pts = [(lat, lon), ...] -> one geolocated VehicleEvent each."""
    for i, (lat, lon) in enumerate(pts):
        mk(cam, plate=plate, track_id=track_id,
           ts=base + timedelta(seconds=i * step),
           latitude=lat, longitude=lon,
           location=f"SRID=4326;POINT({lon} {lat})",
           vehicle_type="car")


# --------------------------------------------------------------------------- #
#  wrong-way
# --------------------------------------------------------------------------- #
def test_wrong_way_detected(db_session, make_camera, make_vehicle_event):
    cam = make_camera(code="CAM-WW", lat=23.0, lon=72.55, permitted_direction_deg=90.0)  # east
    base = datetime.utcnow() - timedelta(hours=1)
    # moving WEST: 72.55 -> 72.54 (~1 km) over 5 detections -> bearing ~270
    _track(make_vehicle_event, cam, "GJ18TC0450", 1,
           [(23.0, 72.550), (23.0, 72.5475), (23.0, 72.545), (23.0, 72.5425), (23.0, 72.540)], base)

    res = BehaviorAnalyticsService(db_session).scan_wrong_way()
    assert res["created"] == 1
    a = res["anomalies"][0]
    assert a.kind == AnomalyKind.WRONG_WAY
    assert 255 <= a.direction_deg <= 285          # ~west
    assert a.expected_direction_deg == 90.0
    assert a.alert_id is not None                 # flows through the alert workflow


def test_wrong_way_negative_correct_direction(db_session, make_camera, make_vehicle_event):
    cam = make_camera(code="CAM-OK", lat=23.0, lon=72.55, permitted_direction_deg=90.0)
    base = datetime.utcnow() - timedelta(hours=1)
    # moving EAST -> with the permitted direction
    _track(make_vehicle_event, cam, "GJ01AA1111", 2,
           [(23.0, 72.540), (23.0, 72.5425), (23.0, 72.545), (23.0, 72.5475), (23.0, 72.550)], base)
    assert BehaviorAnalyticsService(db_session).scan_wrong_way()["created"] == 0


def test_wrong_way_negative_short_distance(db_session, make_camera, make_vehicle_event):
    cam = make_camera(code="CAM-SH", lat=23.0, lon=72.55, permitted_direction_deg=90.0)
    base = datetime.utcnow() - timedelta(hours=1)
    # west but only ~5 m total
    _track(make_vehicle_event, cam, "GJ02BB2222", 3,
           [(23.0, 72.55000), (23.0, 72.54997), (23.0, 72.54995)], base)
    assert BehaviorAnalyticsService(db_session).scan_wrong_way()["created"] == 0


def test_wrong_way_no_config_no_scan(db_session, make_camera, make_vehicle_event):
    cam = make_camera(code="CAM-NC", lat=23.0, lon=72.55)  # no permitted_direction_deg
    base = datetime.utcnow() - timedelta(hours=1)
    _track(make_vehicle_event, cam, "GJ03CC3333", 4,
           [(23.0, 72.550), (23.0, 72.545), (23.0, 72.540)], base)
    assert BehaviorAnalyticsService(db_session).scan_wrong_way()["created"] == 0


def test_wrong_way_idempotent(db_session, make_camera, make_vehicle_event):
    cam = make_camera(code="CAM-ID", lat=23.0, lon=72.55, permitted_direction_deg=90.0)
    base = datetime.utcnow() - timedelta(hours=1)
    _track(make_vehicle_event, cam, "GJ18TC0450", 5,
           [(23.0, 72.550), (23.0, 72.547), (23.0, 72.544), (23.0, 72.541)], base)
    svc = BehaviorAnalyticsService(db_session)
    assert svc.scan_wrong_way()["created"] == 1
    r2 = svc.scan_wrong_way()
    assert r2["created"] == 0 and r2["already_flagged"] == 1


# --------------------------------------------------------------------------- #
#  restricted zone
# --------------------------------------------------------------------------- #
_ZONE = {"name": "Bus depot apron", "points": [
    [23.028, 72.578], [23.028, 72.582], [23.032, 72.582], [23.032, 72.578],
]}


def test_restricted_zone_detected(db_session, make_camera, make_vehicle_event):
    cam = make_camera(code="CAM-RZ", lat=23.03, lon=72.58, restricted_zones=[_ZONE])
    base = datetime.utcnow() - timedelta(hours=1)
    # 3 sightings inside the polygon
    _track(make_vehicle_event, cam, "GJ18TC0450", 10,
           [(23.030, 72.580), (23.0305, 72.5805), (23.031, 72.581)], base)

    res = BehaviorAnalyticsService(db_session).scan_restricted_zone()
    assert res["created"] == 1
    a = res["anomalies"][0]
    assert a.kind == AnomalyKind.RESTRICTED_ZONE
    assert a.zone_name == "Bus depot apron"
    assert a.alert_id is not None


def test_restricted_zone_negative_outside(db_session, make_camera, make_vehicle_event):
    cam = make_camera(code="CAM-OUT", lat=23.03, lon=72.58, restricted_zones=[_ZONE])
    base = datetime.utcnow() - timedelta(hours=1)
    _track(make_vehicle_event, cam, "GJ04DD4444", 11,
           [(23.050, 72.600), (23.051, 72.601), (23.052, 72.602)], base)
    assert BehaviorAnalyticsService(db_session).scan_restricted_zone()["created"] == 0


def test_restricted_zone_single_touch_below_threshold(db_session, make_camera, make_vehicle_event):
    cam = make_camera(code="CAM-1T", lat=23.03, lon=72.58, restricted_zones=[_ZONE])
    base = datetime.utcnow() - timedelta(hours=1)
    # only 1 sighting inside (ANOMALY_ZONE_MIN_INSIDE = 2)
    _track(make_vehicle_event, cam, "GJ05EE5555", 12,
           [(23.050, 72.600), (23.030, 72.580), (23.052, 72.602)], base)
    assert BehaviorAnalyticsService(db_session).scan_restricted_zone()["created"] == 0


# --------------------------------------------------------------------------- #
#  dispatcher / interplay / regression
# --------------------------------------------------------------------------- #
def test_scan_runs_all_three_kinds(db_session, make_camera, make_vehicle_event):
    ww = make_camera(code="CAM-A1", lat=23.0, lon=72.55, permitted_direction_deg=90.0)
    rz = make_camera(code="CAM-A2", lat=23.03, lon=72.58, restricted_zones=[_ZONE])
    base = datetime.utcnow() - timedelta(hours=1)
    _track(make_vehicle_event, ww, "GJ18TC0450", 20,
           [(23.0, 72.550), (23.0, 72.546), (23.0, 72.542), (23.0, 72.538)], base)
    _track(make_vehicle_event, rz, "GJ06FF6666", 21,
           [(23.030, 72.580), (23.0305, 72.5805), (23.031, 72.581)], base)
    res = BehaviorAnalyticsService(db_session).scan()
    kinds = {a.kind for a in res["anomalies"]}
    assert AnomalyKind.WRONG_WAY in kinds
    assert AnomalyKind.RESTRICTED_ZONE in kinds


def test_stopped_and_zone_same_track_no_collision(db_session, make_camera, make_vehicle_event):
    cam = make_camera(code="CAM-SZ", lat=23.03, lon=72.58, restricted_zones=[_ZONE])
    base = datetime.utcnow() - timedelta(minutes=20)
    # a stopped track sitting INSIDE the polygon: 8 detections over ~300 s, no movement
    for i in range(8):
        make_vehicle_event(cam, plate="GJ18TC0450", track_id=30,
                           ts=base + timedelta(seconds=i * 45),
                           latitude=23.030, longitude=72.580,
                           location="SRID=4326;POINT(72.580 23.030)", vehicle_type="car")
    res = BehaviorAnalyticsService(db_session).scan()
    kinds = sorted(a.kind.value for a in res["anomalies"] if a.track_id == 30)
    assert "RESTRICTED_ZONE" in kinds and "STOPPED_VEHICLE" in kinds

    rows = db_session.execute(
        select(AnomalyEvent).where(AnomalyEvent.track_id == 30)
    ).scalars().all()
    assert len(rows) == 2                          # unique index keyed on kind -> no collision


def test_stopped_vehicle_still_detected(db_session, make_camera, make_vehicle_event):
    cam = make_camera(code="CAM-ST", lat=23.03, lon=72.58)
    base = datetime.utcnow() - timedelta(minutes=20)
    for i in range(10):
        make_vehicle_event(cam, plate="GJ07GG7777", track_id=40,
                           ts=base + timedelta(seconds=i * 30),
                           latitude=23.03, longitude=72.58,
                           location="SRID=4326;POINT(72.58 23.03)")
    assert BehaviorAnalyticsService(db_session).scan_stopped_vehicles()["created"] == 1


# --------------------------------------------------------------------------- #
#  API
# --------------------------------------------------------------------------- #
def test_scan_endpoint_kinds_filter(client, officer_user, make_camera, make_vehicle_event):
    _, tok = officer_user
    cam = make_camera(code="CAM-EP", lat=23.0, lon=72.55, permitted_direction_deg=90.0)
    base = datetime.utcnow() - timedelta(hours=1)
    _track(make_vehicle_event, cam, "GJ18TC0450", 50,
           [(23.0, 72.550), (23.0, 72.546), (23.0, 72.542), (23.0, 72.538)], base)

    r = client.post("/api/v1/ai/anomalies/scan", json={"kinds": ["WRONG_WAY"]}, headers=bearer(tok))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] == 1
    a = body["anomalies"][0]
    assert a["kind"] == "WRONG_WAY"
    assert a["direction_deg"] is not None and a["expected_direction_deg"] == 90.0


def test_behavior_config_endpoint_and_rbac(client, operator_user, officer_user, make_camera):
    cam = make_camera(code="CAM-CFG", lat=23.0, lon=72.55)
    _, op_tok = operator_user
    _, off_tok = officer_user

    body = {"permitted_direction_deg": 45.0,
            "restricted_zones": [{"name": "Yard", "points": [[23.0, 72.5], [23.0, 72.6], [23.1, 72.6]]}]}
    assert client.patch(f"/api/v1/cameras/{cam.id}/behavior-config", json=body,
                        headers=bearer(op_tok)).status_code == 403

    r = client.patch(f"/api/v1/cameras/{cam.id}/behavior-config", json=body, headers=bearer(off_tok))
    assert r.status_code == 200, r.text
    assert r.json()["permitted_direction_deg"] == 45.0
    assert len(r.json()["restricted_zones"]) == 1
