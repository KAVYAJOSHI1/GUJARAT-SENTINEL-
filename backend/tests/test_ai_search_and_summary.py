"""Phase 12 §2 (NL search) + §3 (AI summaries)."""
from datetime import datetime, timedelta

from sqlalchemy import select

from app.database import SessionLocal
from app.models.audit_log import AuditLog
from app.models.vehicle_event import VehicleEvent
from conftest import bearer

PLATE = "GJ18TC0450"


def test_nl_search_translates_to_existing_filters(client, officer_user, make_camera, make_vehicle_event):
    _, tok = officer_user
    cam = make_camera(code="CAM-04", lat=23.02, lon=72.57)
    late = datetime.utcnow().replace(hour=21, minute=15, second=0, microsecond=0)
    make_vehicle_event(cam, plate="GJ05WH2222", track_id=1, ts=late, vehicle_type="car")
    with SessionLocal() as db:
        ev = db.execute(select(VehicleEvent)).scalar_one()
        ev.vehicle_color = "white"; db.add(ev); db.commit()

    r = client.post("/api/v1/ai/search", json={"query": "Show white cars after 9 PM."},
                    headers=bearer(tok))
    assert r.status_code == 200
    b = r.json()
    assert b["parsed"]["vehicle_color"] == "white"
    assert b["filters"]["vehicle_color"] == "white"
    assert b["filters"]["time_from"] == "21:00"
    assert b["filters"]["vehicle_type"] == "car"
    assert b["search"]["total"] == 1
    assert b["search"]["items"][0]["plate_number_normalized"] == "GJ05WH2222"

    with SessionLocal() as db:
        assert db.execute(select(AuditLog).where(AuditLog.action == "AI_SEARCH")).first()


def test_nl_search_unknown_and_duration(client, officer_user, make_camera, make_vehicle_event):
    _, tok = officer_user
    cam = make_camera(code="CAM-05")
    base = datetime.utcnow() - timedelta(hours=1)
    # a UNKNOWN track present for 5+ minutes
    with SessionLocal() as db:
        from app.services.plate_utils import normalize_plate
        for i in range(12):
            db.add(VehicleEvent(plate_number="UNKNOWN", plate_number_normalized="UNKNOWN",
                                camera_id=cam.id, camera_code=cam.code, track_id=42,
                                timestamp=base + timedelta(seconds=i * 30), confidence_score=0.5))
        db.commit()
    r = client.post("/api/v1/ai/search",
                    json={"query": "show unknown vehicles detected for more than 5 minutes"},
                    headers=bearer(tok)).json()
    assert r["filters"]["unknown_only"] is True
    assert r["filters"]["min_duration_seconds"] == 300
    assert r["search"]["total"] >= 1


def test_nl_search_requires_auth(client):
    assert client.post("/api/v1/ai/search", json={"query": "x"}).status_code == 401


# --- AI summaries -------------------------------------------------------- #
def test_incident_summary_grounded(client, officer_user, make_camera, make_vehicle_event):
    _, tok = officer_user
    base = datetime.utcnow() - timedelta(hours=1)
    cams = [make_camera(code=f"CAM-{i:02d}", lat=23 + i * 0.02, lon=72.5 + i * 0.02) for i in (1, 2)]
    for i, c in enumerate(cams):
        make_vehicle_event(c, plate=PLATE, track_id=i + 1, ts=base + timedelta(minutes=40 * i))

    inc = client.post("/api/v1/incidents", json={"title": "hit", "plate_number": PLATE},
                      headers=bearer(tok)).json()
    s = client.post(f"/api/v1/ai/incidents/{inc['id']}/summary", headers=bearer(tok))
    assert s.status_code == 200
    b = s.json()
    assert b["subject_ref"] == inc["incident_number"]
    assert "AI-GENERATED SUMMARY" in b["disclaimer"]
    assert PLATE in b["headline"]
    labels = {sec["label"] for sec in b["sections"]}
    assert {"First detection", "Last detection", "Cameras"} <= labels
    # a 40-min gap between the two sightings -> flagged as an investigation gap
    assert any("gap" in g.lower() for g in b["investigation_gaps"])

    with SessionLocal() as db:
        assert db.execute(select(AuditLog).where(AuditLog.action == "AI_INCIDENT_SUMMARY")).first()


def test_summary_says_unavailable_when_no_data(client, officer_user):
    _, tok = officer_user
    inc = client.post("/api/v1/incidents", json={"title": "empty", "plate_number": "GJ44NO0000"},
                      headers=bearer(tok)).json()
    b = client.post(f"/api/v1/ai/incidents/{inc['id']}/summary", headers=bearer(tok)).json()
    joined = " ".join(sec["value"] for sec in b["sections"]) + b["headline"]
    assert "not available in recorded evidence" in joined.lower() or "no recorded sightings" in joined.lower()


def test_case_summary(client, officer_user, make_camera, make_vehicle_event):
    _, tok = officer_user
    cam = make_camera(code="CAM-01")
    make_vehicle_event(cam, plate=PLATE, track_id=1)
    case = client.post("/api/v1/cases", json={"title": "ring", "primary_plate_number": PLATE},
                       headers=bearer(tok)).json()
    inc = client.post("/api/v1/incidents", json={"title": "i", "plate_number": PLATE},
                      headers=bearer(tok)).json()
    client.post(f"/api/v1/cases/{case['id']}/incidents", json={"incident_id": inc["id"]},
                headers=bearer(tok))
    b = client.post(f"/api/v1/ai/cases/{case['id']}/summary", headers=bearer(tok)).json()
    assert b["subject_kind"] == "case"
    assert case["case_number"] in b["headline"]
    assert any(s["label"] == "Linked incidents" and s["value"] == "1" for s in b["sections"])
