"""
Phase 12 — Investigation Copilot. All results must come from real seeded
DB rows; empty results must say so; no hallucination.
"""
from datetime import datetime, timedelta

from sqlalchemy import select

from app.database import SessionLocal
from app.models.alert import Alert
from app.models.audit_log import AuditLog
from app.models.base import PriorityLevel
from app.models.watchlist import Watchlist
from conftest import bearer

PLATE = "GJ18TC0450"


def _seed_journey(db, mk_cam, mk_ev):
    base = datetime.utcnow() - timedelta(hours=2)
    cams = [mk_cam(code=f"CAM-{i:02d}", lat=23.00 + i * 0.02, lon=72.55 + i * 0.02) for i in (1, 2, 4, 7)]
    for i, cam in enumerate(cams):
        mk_ev(cam, plate=PLATE, track_id=i + 1, ts=base + timedelta(minutes=10 * i))
    return cams


def test_vehicle_search_grounded(client, officer_user, make_camera, make_vehicle_event):
    _, tok = officer_user
    from app.models.vehicle_event import VehicleEvent
    with SessionLocal() as db:
        cams = _seed_journey(db, make_camera, make_vehicle_event)
        wl = Watchlist(plate_number=PLATE, plate_number_normalized=PLATE,
                       offense_category="STOLEN", priority_level=PriorityLevel.HIGH)
        db.add(wl); db.commit(); db.refresh(wl)
        ev0 = db.execute(
            select(VehicleEvent).order_by(VehicleEvent.timestamp.asc()).limit(1)
        ).scalar_one()
        db.add(Alert(plate_number=PLATE, plate_number_normalized=PLATE, camera_id=cams[0].id,
                     vehicle_event_id=ev0.id, watchlist_id=wl.id)); db.commit()

    r = client.post("/api/v1/ai/investigate", json={"query": f"Where was {PLATE} seen?"},
                    headers=bearer(tok))
    assert r.status_code == 200
    b = r.json()
    assert b["intent"] == "VEHICLE_SEARCH"
    assert b["parsed"]["plate"] == PLATE
    assert b["result_count"] == 4
    assert PLATE in b["answer"] and "4" in b["answer"]
    assert len(b["timeline"]) == 4
    assert len(b["map_points"]) == 4
    # every result row is a real event id present in the DB
    with SessionLocal() as db:
        from app.models.vehicle_event import VehicleEvent
        real_ids = {e for (e,) in db.execute(select(VehicleEvent.id)).all()}
    assert all(row["event_id"] in real_ids for row in b["results"])
    assert b["confidence_level"] in ("HIGH", "MEDIUM")
    assert any(rel["kind"] == "ALERT" for rel in b["related"])

    # audited
    with SessionLocal() as db:
        assert db.execute(select(AuditLog).where(AuditLog.action == "AI_INVESTIGATION")).first()


def test_journey_and_last_seen(client, officer_user, make_camera, make_vehicle_event):
    _, tok = officer_user
    with SessionLocal() as db:
        _seed_journey(db, make_camera, make_vehicle_event)

    j = client.post("/api/v1/ai/investigate", json={"query": f"Show the journey of {PLATE}."},
                    headers=bearer(tok)).json()
    assert j["intent"] == "VEHICLE_JOURNEY"
    assert "→" in j["answer"]
    ts = [t["timestamp"] for t in j["timeline"]]
    assert ts == sorted(ts)

    ls = client.post("/api/v1/ai/investigate", json={"query": f"Where was {PLATE} last seen?"},
                     headers=bearer(tok)).json()
    assert ls["intent"] == "VEHICLE_LAST_SEEN"
    assert "last seen" in ls["answer"].lower()
    assert "CAM-07" in ls["answer"]


def test_empty_result_says_not_available(client, officer_user):
    _, tok = officer_user
    r = client.post("/api/v1/ai/investigate", json={"query": "Where was GJ99ZZ9999 seen?"},
                    headers=bearer(tok)).json()
    assert r["result_count"] == 0
    assert "not available in recorded evidence" in r["answer"].lower()
    assert r["confidence_level"] == "INSUFFICIENT"


def test_no_plate_for_journey_is_handled(client, officer_user):
    _, tok = officer_user
    r = client.post("/api/v1/ai/investigate", json={"query": "show the journey"},
                    headers=bearer(tok)).json()
    assert r["result_count"] == 0
    assert "need" in r["answer"].lower() and "plate" in r["answer"].lower()


def test_time_range_search_and_filters_shown(client, officer_user, make_camera, make_vehicle_event):
    _, tok = officer_user
    cam = make_camera(code="CAM-04", lat=23.02, lon=72.57)
    late = datetime.utcnow().replace(hour=21, minute=30, second=0, microsecond=0)
    make_vehicle_event(cam, plate="GJ05WH1111", track_id=50, ts=late, vehicle_type="car")
    with SessionLocal() as db:
        from app.models.vehicle_event import VehicleEvent
        ev = db.execute(select(VehicleEvent)).scalar_one()
        ev.vehicle_color = "white"; db.add(ev); db.commit()

    r = client.post("/api/v1/ai/investigate",
                    json={"query": "Show white cars detected near CAM-04 after 9 PM."},
                    headers=bearer(tok)).json()
    assert r["tool_calls"][0]["tool"] == "search_detections"
    assert r["tool_calls"][0]["params"]["vehicle_color"] == "white"
    assert r["parsed"]["time_from"] == "21:00"


def test_watchlist_question(client, admin_user, make_camera, make_vehicle_event):
    _, tok = admin_user
    cam = make_camera(code="CAM-01")
    with SessionLocal() as db:
        wl = Watchlist(plate_number=PLATE, plate_number_normalized=PLATE,
                       offense_category="STOLEN", priority_level=PriorityLevel.CRITICAL)
        db.add(wl); db.commit()
    # ingest a detection -> real watchlist alert via the existing engine
    from app.config import settings
    client.post("/api/v1/events/ai-detection", json={
        "camera_id": "CAM-01", "plate_number": PLATE,
        "timestamp": datetime.utcnow().isoformat(), "confidence": 0.9},
        headers={"X-Ingest-Key": settings.INGEST_API_KEY})

    r = client.post("/api/v1/ai/investigate",
                    json={"query": "Show watchlist vehicles detected today."}, headers=bearer(tok)).json()
    assert r["intent"] == "WATCHLIST_SEARCH"
    assert r["result_count"] >= 1
    assert any(rel["kind"] == "ALERT" for rel in r["related"])


def test_requires_auth(client):
    assert client.post("/api/v1/ai/investigate", json={"query": "x"}).status_code == 401
