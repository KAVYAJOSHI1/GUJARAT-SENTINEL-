"""
Phase 13 — journey-intelligence + camera-management polish. Additive,
derived-only; CONFIRMED (observed) vs INFERRED (transition) distinction;
never fabricate distance/speed without coordinates.
"""
from datetime import datetime, timedelta

from app.database import SessionLocal
from app.models.vehicle_event import VehicleEvent
from app.services.plate_utils import normalize_plate
from conftest import bearer

PLATE = "GJ18TC0450"


def _ev(db, cam, plate, ts, *, track_id=1, lat=None, lon=None, vtype="car", color=None):
    db.add(VehicleEvent(
        plate_number=plate, plate_number_normalized=normalize_plate(plate),
        camera_id=cam.id, camera_code=cam.code, track_id=track_id, timestamp=ts,
        vehicle_type=vtype, vehicle_color=color, confidence_score=0.9,
        latitude=lat, longitude=lon,
        location=(f"SRID=4326;POINT({lon} {lat})" if lat is not None and lon is not None else None),
    ))


def test_journey_transitions_confirmed_vs_inferred(client, officer_user, make_camera):
    _, tok = officer_user
    base = datetime.utcnow() - timedelta(hours=1)
    c1 = make_camera(code="CAM-01", lat=23.00, lon=72.55)
    c2 = make_camera(code="CAM-02", lat=23.02, lon=72.57)   # ~2.9 km from c1
    c3 = make_camera(code="CAM-03", lat=None, lon=None)     # no geometry
    with SessionLocal() as db:
        _ev(db, c1, PLATE, base, lat=23.00, lon=72.55, color="white")
        _ev(db, c2, PLATE, base + timedelta(minutes=6), lat=23.02, lon=72.57, color="white")
        _ev(db, c3, PLATE, base + timedelta(minutes=90))
        db.commit()

    j = client.get("/api/v1/vehicles/search", params={"plate": PLATE}, headers=bearer(tok)).json()
    assert j["total_sightings"] == 3
    # sightings are CONFIRMED facts, carry colour + is_mock
    assert all(s["kind"] == "CONFIRMED" for s in j["sightings"])
    assert j["sightings"][0]["vehicle_color"] == "white"
    assert all(s["is_mock"] is False for s in j["sightings"])

    tr = j["journey"]["transitions"]
    assert j["journey"]["confirmed_sightings"] == 3
    assert j["journey"]["inferred_transitions"] == len(tr) == 2
    assert all(t["kind"] == "INFERRED" for t in tr)

    # CAM-01 -> CAM-02: geolocated, 6 min, ~2.9 km -> distance + plausible speed
    t01 = tr[0]
    assert t01["from_camera_code"] == "CAM-01" and t01["to_camera_code"] == "CAM-02"
    assert 2000 < t01["distance_meters"] < 4000
    assert t01["estimated_speed_kmh"] is not None and 0 < t01["estimated_speed_kmh"] <= 200
    assert t01["confidence_level"] in ("HIGH", "MEDIUM")

    # CAM-02 -> CAM-03: CAM-03 has no coords -> NO distance/speed, note says so, low confidence (90 min gap)
    t23 = tr[1]
    assert t23["distance_meters"] is None and t23["estimated_speed_kmh"] is None
    assert any("coordinates unavailable" in n for n in t23["notes"])
    assert t23["confidence_level"] == "LOW"


def test_transition_implausible_speed_not_reported(client, officer_user, make_camera):
    _, tok = officer_user
    base = datetime.utcnow() - timedelta(hours=1)
    c1 = make_camera(code="CAM-11", lat=23.00, lon=72.55)
    c2 = make_camera(code="CAM-12", lat=23.50, lon=73.10)  # ~75 km away
    with SessionLocal() as db:
        _ev(db, c1, PLATE, base, lat=23.00, lon=72.55)
        _ev(db, c2, PLATE, base + timedelta(minutes=2), lat=23.50, lon=73.10)  # 75 km in 2 min
        db.commit()
    j = client.get("/api/v1/vehicles/search", params={"plate": PLATE}, headers=bearer(tok)).json()
    t = j["journey"]["transitions"][0]
    assert t["distance_meters"] is not None       # distance IS a fact
    assert t["estimated_speed_kmh"] is None        # speed is not reported
    assert any("implausible" in n for n in t["notes"])


def test_camera_list_has_mock_and_last_detection(client, officer_user, make_camera):
    _, tok = officer_user
    real = make_camera(code="CAM-04")
    mock = make_camera(code="MOCK_CAM01")
    with SessionLocal() as db:
        _ev(db, real, "GJ01AB1234", datetime.utcnow() - timedelta(minutes=3))
        db.commit()
    cams = client.get("/api/v1/cameras", headers=bearer(tok)).json()
    by_code = {c["code"]: c for c in cams}
    assert by_code["CAM-04"]["is_mock"] is False
    assert by_code["MOCK_CAM01"]["is_mock"] is True
    assert by_code["CAM-04"]["last_detection_at"] is not None
    assert by_code["MOCK_CAM01"]["last_detection_at"] is None


def test_single_sighting_has_no_transitions(client, officer_user, make_camera):
    _, tok = officer_user
    c1 = make_camera(code="CAM-21", lat=23.0, lon=72.5)
    with SessionLocal() as db:
        _ev(db, c1, PLATE, datetime.utcnow(), lat=23.0, lon=72.5)
        db.commit()
    j = client.get("/api/v1/vehicles/search", params={"plate": PLATE}, headers=bearer(tok)).json()
    assert j["journey"]["transitions"] == []
    assert j["journey"]["is_single_sighting"] is True
