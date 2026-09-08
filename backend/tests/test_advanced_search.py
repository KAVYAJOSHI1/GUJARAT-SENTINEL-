"""Unified Advanced Search + Global Quick Search (Phase 11 FEATURE 1 / 14)."""
from datetime import datetime, timedelta

from sqlalchemy import select

from app.database import SessionLocal
from app.models.alert import Alert
from app.models.audit_log import AuditLog
from app.models.base import PriorityLevel
from app.models.watchlist import Watchlist
from conftest import bearer


def _seed(db, camera, plate, *, ts=None, vtype="car", conf=0.9):
    from app.models.vehicle_event import VehicleEvent
    from app.services.plate_utils import normalize_plate
    ev = VehicleEvent(
        plate_number=plate, plate_number_normalized=normalize_plate(plate),
        camera_id=camera.id, camera_code=camera.code, vehicle_type=vtype,
        confidence_score=conf, timestamp=ts or datetime.utcnow(),
    )
    db.add(ev); db.commit(); db.refresh(ev)
    return ev


def test_exact_and_partial_plate_search(client, officer_user, make_camera):
    _, tok = officer_user
    cam = make_camera(code="cam-s1")
    with SessionLocal() as db:
        _seed(db, cam, "GJ18TC0450")
        _seed(db, cam, "GJ18TC9999")
        _seed(db, cam, "GJ01AB1234")

    exact = client.post("/api/v1/search/vehicles", json={"plate": "gj18tc0450"}, headers=bearer(tok)).json()
    assert exact["total"] == 1 and exact["items"][0]["plate_number_normalized"] == "GJ18TC0450"

    partial = client.post("/api/v1/search/vehicles", json={"plate_contains": "18TC"}, headers=bearer(tok)).json()
    assert partial["total"] == 2

    assert client.post("/api/v1/search/vehicles", json={}).status_code == 401


def test_filters_sort_pagination_and_relationships(
    client, admin_user, officer_user, make_camera
):
    _, admin = admin_user
    cam1 = make_camera(code="cam-s2", lat=23.0, lon=72.5)
    cam2 = make_camera(code="MOCK_CAM77", lat=23.1, lon=72.6)
    base = datetime.utcnow() - timedelta(hours=3)
    with SessionLocal() as db:
        db.add(Watchlist(plate_number="GJ18TC0450", plate_number_normalized="GJ18TC0450",
                         offense_category="STOLEN", priority_level=PriorityLevel.HIGH))
        db.commit()
        e1 = _seed(db, cam1, "GJ18TC0450", ts=base, conf=0.99, vtype="car")
        _seed(db, cam2, "GJ99XX1111", ts=base + timedelta(minutes=30), conf=0.4, vtype="truck")
        # an alert on e1
        db.add(Alert(plate_number="GJ18TC0450", plate_number_normalized="GJ18TC0450",
                     camera_id=cam1.id, vehicle_event_id=e1.id,
                     watchlist_id=db.execute(select(Watchlist.id)).scalar()))
        db.commit()

    # watchlist_only
    wl = client.post("/api/v1/search/vehicles", json={"watchlist_only": True}, headers=bearer(admin)).json()
    assert wl["total"] == 1 and wl["items"][0]["is_watchlisted"] is True
    assert wl["items"][0]["alert_id"] is not None

    # source filter
    mock = client.post("/api/v1/search/vehicles", json={"source": "MOCK"}, headers=bearer(admin)).json()
    assert mock["total"] == 1 and mock["items"][0]["is_mock_camera"] is True
    real = client.post("/api/v1/search/vehicles", json={"source": "REAL"}, headers=bearer(admin)).json()
    assert real["total"] == 1 and real["items"][0]["is_mock_camera"] is False

    # confidence + vehicle_type
    hi = client.post("/api/v1/search/vehicles",
                     json={"min_confidence": 0.9, "vehicle_type": "car"}, headers=bearer(admin)).json()
    assert hi["total"] == 1

    # has_alert
    assert client.post("/api/v1/search/vehicles", json={"has_alert": True}, headers=bearer(admin)).json()["total"] == 1
    assert client.post("/api/v1/search/vehicles", json={"has_alert": False}, headers=bearer(admin)).json()["total"] == 1

    # sort + pagination
    p = client.post("/api/v1/search/vehicles", json={"sort": "confidence", "limit": 1}, headers=bearer(admin)).json()
    assert p["items"][0]["confidence_score"] == 0.99 and p["limit"] == 1 and p["total"] == 2

    # audited
    with SessionLocal() as db:
        assert db.execute(select(AuditLog).where(AuditLog.action == "ADVANCED_SEARCH")).first()


def test_global_search_groups(client, officer_user, make_camera):
    _, tok = officer_user
    cam = make_camera(code="cam-glob-1", name="Paldi Circle")
    with SessionLocal() as db:
        _seed(db, cam, "GJ18TC0450")
    inc = client.post("/api/v1/incidents", json={"title": "x", "plate_number": "GJ18TC0450"},
                      headers=bearer(tok)).json()
    case = client.post("/api/v1/cases", json={"title": "Paldi case"}, headers=bearer(tok)).json()

    r = client.get("/api/v1/search/global", params={"q": "GJ18TC0450"}, headers=bearer(tok)).json()
    assert any(h["kind"] == "VEHICLE" for h in r["groups"]["VEHICLES"])
    assert any(h["id"] == inc["id"] for h in r["groups"]["INCIDENTS"])

    r2 = client.get("/api/v1/search/global", params={"q": "Paldi"}, headers=bearer(tok)).json()
    assert any(h["kind"] == "CAMERA" for h in r2["groups"]["CAMERAS"])
    assert any(h["id"] == case["id"] for h in r2["groups"]["CASES"])

    assert client.get("/api/v1/search/global", params={"q": "x"}).status_code == 401
