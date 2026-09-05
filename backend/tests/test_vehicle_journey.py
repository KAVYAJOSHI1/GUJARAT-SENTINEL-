"""
Phase 5 -- vehicle search / journey (GET /api/v1/vehicles/search).

Covers: chronological ordering, vehicle_type stored + returned, the journey
summary block, single-sighting handling, no-coordinate sighting still
returned, unknown-plate behaviour, and the watchlist flag.
"""
from datetime import datetime, timedelta

from conftest import bearer


def _search(client, token, plate):
    return client.get(f"/api/v1/vehicles/search?plate={plate}", headers=bearer(token))


def test_sightings_are_chronological_ascending(client, officer_user, make_camera, make_vehicle_event):
    _, token = officer_user
    c1 = make_camera(code="cam-j-1", lat=23.01, lon=72.51)
    c2 = make_camera(code="cam-j-2", lat=23.05, lon=72.55)
    base = datetime.utcnow() - timedelta(hours=3)
    # insert out of order
    make_vehicle_event(c2, plate="GJ01JRNY01", track_id=2, ts=base + timedelta(minutes=40), vehicle_type="car")
    make_vehicle_event(c1, plate="GJ01JRNY01", track_id=1, ts=base, vehicle_type="car")
    make_vehicle_event(c1, plate="GJ01JRNY01", track_id=1, ts=base + timedelta(minutes=10), vehicle_type="car")

    resp = _search(client, token, "GJ01JRNY01")
    assert resp.status_code == 200
    body = resp.json()
    ts = [s["timestamp"] for s in body["sightings"]]
    assert ts == sorted(ts)
    assert body["total_sightings"] == 3


def test_vehicle_type_stored_and_returned(client, officer_user, make_camera, make_vehicle_event):
    _, token = officer_user
    cam = make_camera(code="cam-j-3")
    make_vehicle_event(cam, plate="GJ02TYPE01", vehicle_type="motorcycle")
    body = _search(client, token, "GJ02TYPE01").json()
    assert body["sightings"][0]["vehicle_type"] == "motorcycle"
    assert body["journey"]["vehicle_types"] == ["motorcycle"]


def test_vehicle_type_canonicalised_on_ingest(client, officer_user, make_camera):
    """A flat-form 'motorbike' from the pipeline is stored as 'motorcycle'."""
    _, token = officer_user
    cam = make_camera(code="cam-j-ingest")
    ingest = client.post(
        "/api/v1/events/ai-detection",
        json={
            "camera_id": cam.code,
            "timestamp": datetime.utcnow().isoformat(),
            "plate_number": "GJ03CANON1",
            "track_id": 5,
            "vehicle_type": "MotorBike",
            "confidence_score": 0.9,
        },
        headers={"X-Ingest-Key": "test-ingest-key"},
    )
    assert ingest.status_code == 201
    body = _search(client, token, "GJ03CANON1").json()
    assert body["sightings"][0]["vehicle_type"] == "motorcycle"


def test_journey_summary_multi_sighting(client, officer_user, make_camera, make_vehicle_event):
    _, token = officer_user
    c1 = make_camera(code="cam-j-4", lat=23.01, lon=72.51)
    c2 = make_camera(code="cam-j-5", lat=23.09, lon=72.59)
    base = datetime.utcnow() - timedelta(hours=2)
    make_vehicle_event(c1, plate="GJ04SUMM01", ts=base, vehicle_type="car")
    make_vehicle_event(c2, plate="GJ04SUMM01", ts=base + timedelta(minutes=30), vehicle_type="car")

    j = _search(client, token, "GJ04SUMM01").json()["journey"]
    assert j["distinct_cameras"] == 2
    assert j["geolocated_sightings"] == 2
    assert j["span_seconds"] == 1800
    assert j["is_single_sighting"] is False
    assert j["has_journey"] is True


def test_single_sighting_has_no_plottable_journey(client, officer_user, make_camera, make_vehicle_event):
    _, token = officer_user
    cam = make_camera(code="cam-j-6", lat=23.02, lon=72.52)
    make_vehicle_event(cam, plate="GJ05SINGLE", vehicle_type="truck")
    j = _search(client, token, "GJ05SINGLE").json()["journey"]
    assert j["is_single_sighting"] is True
    assert j["has_journey"] is False
    assert j["span_seconds"] == 0
    assert j["first_seen"] == j["last_seen"]


def test_sighting_without_coordinates_is_still_returned(client, officer_user, make_camera, make_vehicle_event):
    _, token = officer_user
    geo_cam = make_camera(code="cam-j-geo", lat=23.03, lon=72.53)
    no_geo_cam = make_camera(code="cam-j-nogeo", lat=None, lon=None)
    base = datetime.utcnow() - timedelta(hours=1)
    make_vehicle_event(no_geo_cam, plate="GJ06NOGEO1", ts=base, vehicle_type="car")
    make_vehicle_event(geo_cam, plate="GJ06NOGEO1", ts=base + timedelta(minutes=5), vehicle_type="car")

    body = _search(client, token, "GJ06NOGEO1").json()
    assert body["total_sightings"] == 2
    by_cam = {s["camera_code"]: s for s in body["sightings"]}
    assert by_cam["cam-j-nogeo"]["has_location"] is False
    assert by_cam["cam-j-nogeo"]["latitude"] is None
    assert by_cam["cam-j-geo"]["has_location"] is True
    j = body["journey"]
    assert j["geolocated_sightings"] == 1
    assert j["has_journey"] is False  # only one geolocated camera


def test_unknown_plate_search_returns_empty_journey(client, officer_user):
    _, token = officer_user
    body = _search(client, token, "UNKNOWN").json()
    assert body["total_sightings"] == 0
    assert body["sightings"] == []
    assert body["journey"]["has_journey"] is False
    assert body["journey"]["first_seen"] is None


def test_confidence_score_present_in_sighting(client, officer_user, make_camera, make_vehicle_event):
    _, token = officer_user
    cam = make_camera(code="cam-j-conf")
    make_vehicle_event(cam, plate="GJ07CONF01", vehicle_type="car")  # fixture sets 0.9
    s = _search(client, token, "GJ07CONF01").json()["sightings"][0]
    assert s["confidence_score"] is not None
    assert abs(s["confidence_score"] - 0.9) < 1e-6


def test_search_requires_auth(client):
    assert client.get("/api/v1/vehicles/search?plate=GJ01AB1234").status_code == 401
