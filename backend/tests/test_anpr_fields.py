"""
Phase 15B -- ANPR status / failure-reason plumbing through the backend.

The pipeline now sends an `anpr` block on the detection event; the backend
stores it on vehicle_events and surfaces it on the vehicle-search sightings.
"""
from conftest import bearer


def _ingest(client, body):
    return client.post("/api/v1/events/ai-detection", json=body,
                       headers={"X-Ingest-Key": "test-ingest-key"})


def test_unknown_plate_with_reason_is_stored(client, officer_user):
    _, tok = officer_user
    r = _ingest(client, {
        "camera_id": "cam-anpr-1", "timestamp": "2026-09-08T10:00:00", "track_id": 1,
        "vehicle": {"type": "car", "confidence": 0.9},
        "license_plate": {"plate_detected": False, "plate_number": "UNKNOWN", "confidence": 0.0},
        "anpr": {"status": "UNKNOWN", "failure_reason": "LOW_RESOLUTION",
                 "quality_score": 0.31, "plate_quality": 0.42},
    })
    assert r.status_code == 201, r.text

    s = client.get("/api/v1/vehicles/search", params={"plate": "UNKNOWN"}, headers=bearer(tok)).json()
    assert s["total_sightings"] >= 1
    sight = s["sightings"][0]
    assert sight["anpr_status"] == "UNKNOWN"
    assert sight["anpr_failure_reason"] == "LOW_RESOLUTION"
    assert sight["anpr_quality_score"] == 0.31


def test_readable_plate_defaults_to_ok(client, officer_user):
    _, tok = officer_user
    r = _ingest(client, {
        "camera_id": "cam-anpr-2", "timestamp": "2026-09-08T10:05:00", "track_id": 2,
        "vehicle": {"type": "car", "confidence": 0.9},
        "license_plate": {"plate_detected": True, "plate_number": "GJ18TC0450", "confidence": 0.94},
    })
    assert r.status_code == 201
    s = client.get("/api/v1/vehicles/search", params={"plate": "GJ18TC0450"}, headers=bearer(tok)).json()
    sight = s["sightings"][0]
    assert sight["anpr_status"] == "OK"
    assert sight["anpr_failure_reason"] is None


def test_unknown_without_explicit_block_gets_a_reason(client, officer_user):
    _, tok = officer_user
    r = _ingest(client, {
        "camera_id": "cam-anpr-3", "timestamp": "2026-09-08T10:10:00", "track_id": 3,
        "vehicle": {"type": "truck", "confidence": 0.8},
        "plate_number": "UNKNOWN",
    })
    assert r.status_code == 201
    s = client.get("/api/v1/vehicles/search", params={"plate": "UNKNOWN"}, headers=bearer(tok)).json()
    reasons = {x["anpr_failure_reason"] for x in s["sightings"]}
    # every UNKNOWN sighting has SOME reason, never a bare null+unknown
    assert all(x["anpr_status"] == "OK" or x["anpr_failure_reason"] for x in s["sightings"])
    assert "LOW_CONFIDENCE" in reasons
