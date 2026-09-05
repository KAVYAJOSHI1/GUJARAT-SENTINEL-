"""
Watchlist expiry enforcement (SENTINEL_System_Audit_Report.md §12/§15 —
"watchlist.expires_at never enforced... an 'expired' entry keeps matching
forever"). Covers the matching engine directly and the end-to-end
ingest -> alert path, plus the investigation search's is_watchlisted flag.
"""
from datetime import datetime, timedelta

from app.config import settings
from app.models.base import PriorityLevel
from app.models.watchlist import Watchlist
from app.services.plate_utils import normalize_plate
from app.services.watchlist_engine import find_watchlist_match
from conftest import bearer


def _entry(db_session, plate, *, active=True, expires_at=None):
    norm = normalize_plate(plate)
    entry = Watchlist(
        plate_number=plate,
        plate_number_normalized=norm,
        offense_category="STOLEN",
        priority_level=PriorityLevel.HIGH,
        active=active,
        expires_at=expires_at,
    )
    db_session.add(entry)
    db_session.commit()
    db_session.refresh(entry)
    return entry


def test_active_non_expiring_plate_matches(db_session):
    _entry(db_session, "GJ18XX1234", expires_at=None)
    match = find_watchlist_match(db_session, "GJ18XX1234")
    assert match is not None


def test_active_future_expiring_plate_matches(db_session):
    future = datetime.utcnow() + timedelta(days=1)
    _entry(db_session, "GJ18XX1235", expires_at=future)
    match = find_watchlist_match(db_session, "GJ18XX1235")
    assert match is not None


def test_expired_plate_does_not_match(db_session):
    past = datetime.utcnow() - timedelta(days=1)
    _entry(db_session, "GJ18XX1236", expires_at=past)
    match = find_watchlist_match(db_session, "GJ18XX1236")
    assert match is None


def test_inactive_plate_does_not_match(db_session):
    _entry(db_session, "GJ18XX1237", active=False, expires_at=None)
    match = find_watchlist_match(db_session, "GJ18XX1237")
    assert match is None


def test_duplicate_watchlist_entry_rejected(client, admin_user):
    _, token = admin_user
    payload = {"plate_number": "GJ09YY4321", "offense_category": "WARRANT"}
    first = client.post("/api/v1/watchlist", json=payload, headers=bearer(token))
    assert first.status_code == 201
    second = client.post("/api/v1/watchlist", json=payload, headers=bearer(token))
    assert second.status_code == 409


def test_alert_generated_only_for_currently_valid_entry(client, admin_user, make_camera):
    """End-to-end: an expired watchlist plate passing a camera must NOT
    raise an alert, while an otherwise-identical active entry does."""
    _, token = admin_user
    camera = make_camera(code="cam-expiry-01")

    past = (datetime.utcnow() - timedelta(days=1)).isoformat()
    future = (datetime.utcnow() + timedelta(days=1)).isoformat()

    client.post(
        "/api/v1/watchlist",
        json={"plate_number": "GJ00EXPIRED", "offense_category": "STOLEN", "expires_at": past},
        headers=bearer(token),
    )
    client.post(
        "/api/v1/watchlist",
        json={"plate_number": "GJ00ACTIVE9", "offense_category": "STOLEN", "expires_at": future},
        headers=bearer(token),
    )

    ingest_expired = client.post(
        "/api/v1/events/ai-detection",
        json={
            "camera_id": camera.code,
            "timestamp": datetime.utcnow().isoformat(),
            "plate_number": "GJ00EXPIRED",
            "track_id": 10,
        },
        headers={"X-Ingest-Key": settings.INGEST_API_KEY},
    )
    assert ingest_expired.status_code == 201
    body_expired = ingest_expired.json()
    assert body_expired["watchlist_match"] is False
    assert body_expired["alert_id"] is None

    ingest_active = client.post(
        "/api/v1/events/ai-detection",
        json={
            "camera_id": camera.code,
            "timestamp": datetime.utcnow().isoformat(),
            "plate_number": "GJ00ACTIVE9",
            "track_id": 11,
        },
        headers={"X-Ingest-Key": settings.INGEST_API_KEY},
    )
    assert ingest_active.status_code == 201
    body_active = ingest_active.json()
    assert body_active["watchlist_match"] is True
    assert body_active["alert_id"] is not None


def test_investigation_search_hides_expired_watchlist_flag(client, officer_user, make_camera, make_vehicle_event, db_session):
    _, token = officer_user
    camera = make_camera(code="cam-expiry-02")
    make_vehicle_event(camera, plate="GJ00STALE1")
    past = datetime.utcnow() - timedelta(days=1)
    _entry(db_session, "GJ00STALE1", expires_at=past)

    resp = client.get("/api/v1/vehicles/search", params={"plate": "GJ00STALE1"}, headers=bearer(token))
    assert resp.status_code == 200
    assert resp.json()["is_watchlisted"] is False
