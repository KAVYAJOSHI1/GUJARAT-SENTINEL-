"""
Phase 18 Part H -- duplicate-event handling.

The AI pipeline retries POST /api/v1/events/ai-detection on ANY connection
error or 5xx (ai/pipeline.py `_post_one`), including the case where the
first attempt actually committed server-side but the response never made
it back to the caller. Without an idempotency check that redelivery
silently created a second `vehicle_events` row (and a second watchlist
alert) for one real detection.
"""
from conftest import bearer


def _ingest(client, body):
    return client.post("/api/v1/events/ai-detection", json=body,
                       headers={"X-Ingest-Key": "test-ingest-key"})


def test_same_event_id_posted_twice_creates_only_one_row(client, officer_user):
    _, tok = officer_user
    body = {
        "event_id": "evt_dedup_test_0001",
        "camera_id": "cam-dedup-1", "timestamp": "2026-09-09T10:00:00", "track_id": 1,
        "vehicle": {"type": "car", "confidence": 0.9},
        "license_plate": {"plate_detected": True, "plate_number": "GJ01AB1234", "confidence": 0.9},
    }
    r1 = _ingest(client, body)
    assert r1.status_code == 201, r1.text
    b1 = r1.json()
    assert b1["duplicate"] is False

    r2 = _ingest(client, body)
    assert r2.status_code == 201, r2.text
    b2 = r2.json()
    assert b2["duplicate"] is True
    assert b2["id"] == b1["id"]  # same underlying row, not a new one

    s = client.get("/api/v1/vehicles/search", params={"plate": "GJ01AB1234"}, headers=bearer(tok)).json()
    assert s["total_sightings"] == 1


def test_missing_event_id_is_never_deduplicated(client):
    """Older/synthetic callers that never set event_id must be completely
    unaffected -- two distinct real detections without an event_id are
    two distinct rows, never collapsed."""
    body = {
        "camera_id": "cam-dedup-2", "timestamp": "2026-09-09T10:05:00", "track_id": 2,
        "vehicle": {"type": "car", "confidence": 0.9},
        "license_plate": {"plate_detected": True, "plate_number": "GJ02CD5678", "confidence": 0.9},
    }
    r1 = _ingest(client, body)
    r2 = _ingest(client, body)
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.json()["id"] != r2.json()["id"]
    assert r2.json()["duplicate"] is False


def test_duplicate_delivery_does_not_double_the_watchlist_alert(client, db_session, officer_user):
    from app.models.base import PriorityLevel
    from app.models.watchlist import Watchlist
    _, tok = officer_user
    db_session.add(Watchlist(
        plate_number="GJ18TC0450", plate_number_normalized="GJ18TC0450",
        offense_category="STOLEN", priority_level=PriorityLevel.CRITICAL,
    ))
    db_session.commit()

    body = {
        "event_id": "evt_dedup_watchlist_0001",
        "camera_id": "cam-dedup-3", "timestamp": "2026-09-09T10:10:00", "track_id": 3,
        "vehicle": {"type": "car", "confidence": 0.9},
        "license_plate": {"plate_detected": True, "plate_number": "GJ18TC0450", "confidence": 0.95},
    }
    r1 = _ingest(client, body)
    assert r1.json()["watchlist_match"] is True
    assert r1.json()["alert_id"] is not None

    r2 = _ingest(client, body)
    assert r2.json()["duplicate"] is True

    alerts = client.get("/api/v1/alerts", headers=bearer(tok)).json()
    items = alerts["items"] if isinstance(alerts, dict) else alerts
    matching = [a for a in items if a.get("plate_number_normalized") == "GJ18TC0450"]
    assert len(matching) == 1
