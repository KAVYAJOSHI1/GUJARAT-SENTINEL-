"""
End-to-end demo acceptance flow (phase brief "DEMO ACCEPTANCE FLOW").

GJ18TC0450 detected -> watchlist match -> alert -> acknowledge -> create
incident -> assign officer -> (trace vehicle) -> attach evidence -> create
case -> attach incident -> attach evidence -> add note -> generate case
report -> resolve incident -> close case.

Everything is real persisted backend state -- the test never fabricates a
row, it drives the same endpoints the UI does.
"""
from datetime import datetime, timedelta

from conftest import bearer
from app.database import SessionLocal
from app.models.base import PriorityLevel
from app.models.watchlist import Watchlist

PLATE = "GJ18TC0450"


def test_full_demo_flow(client, admin_user, officer_user, make_camera):
    _, admin = admin_user
    officer, officer_tok = officer_user

    # demo watchlist entry (the protected GJ18TC0450 demo vehicle)
    with SessionLocal() as s:
        s.add(Watchlist(plate_number=PLATE, plate_number_normalized=PLATE,
                        offense_category="STOLEN", priority_level=PriorityLevel.CRITICAL))
        s.commit()

    cam1 = make_camera(code="cam01", lat=23.03, lon=72.58)
    cam2 = make_camera(code="cam02", lat=23.05, lon=72.60)
    cam3 = make_camera(code="cam03", lat=23.07, lon=72.62)

    # --- detections across 3 cameras (ANPR ingest path) ---
    base = datetime.utcnow() - timedelta(minutes=20)
    event_ids = []
    for i, cam in enumerate((cam1, cam2, cam3)):
        r = client.post("/api/v1/events/ai-detection", json={
            "camera_id": cam.code, "plate_number": PLATE,
            "timestamp": (base + timedelta(minutes=6 * i)).isoformat(), "confidence": 0.93,
        }, headers={"X-Ingest-Key": "test-ingest-key"})
        assert r.status_code == 201, r.text
        event_ids.append(r.json()["id"])
    # first detection creates the alert; later ones are cooldown-suppressed
    assert client.post("/api/v1/events/ai-detection", json={
        "camera_id": cam1.code, "plate_number": PLATE,
        "timestamp": datetime.utcnow().isoformat(), "confidence": 0.9,
    }, headers={"X-Ingest-Key": "test-ingest-key"}).json()["watchlist_match"] is True

    # --- alert exists ---
    alerts = client.get("/api/v1/alerts", headers=bearer(officer_tok)).json()
    assert alerts and alerts[0]["plate_number_normalized"] == PLATE
    alert_id = alerts[0]["id"]

    # --- acknowledge alert ---
    ack = client.patch(f"/api/v1/alerts/{alert_id}", json={"status": "ACKNOWLEDGED"},
                       headers=bearer(officer_tok))
    assert ack.status_code == 200 and ack.json()["status"] == "ACKNOWLEDGED"

    # --- create incident from the alert ---
    inc = client.post("/api/v1/incidents", json={"alert_id": alert_id}, headers=bearer(officer_tok))
    assert inc.status_code == 201, inc.text
    incident = inc.json()
    assert incident["plate_number_normalized"] == PLATE
    incident_id = incident["id"]

    # --- assign officer ---
    asg = client.post(f"/api/v1/incidents/{incident_id}/assign", json={"user_id": officer.id},
                      headers=bearer(admin))
    assert asg.json()["assigned_to_username"] == "test_officer"

    # --- trace vehicle (camera-sighting journey) ---
    trace = client.get("/api/v1/vehicles/search", params={"plate": PLATE}, headers=bearer(officer_tok))
    assert trace.status_code == 200
    body = trace.json()
    assert body["total_sightings"] >= 3
    assert body["is_watchlisted"] is True
    assert body["journey"]["has_journey"] is True  # >=2 geolocated cameras

    # --- attach evidence to the incident ---
    ev = client.post(f"/api/v1/incidents/{incident_id}/evidence",
                     json={"vehicle_event_id": event_ids[0], "note": "first sighting"},
                     headers=bearer(officer_tok))
    assert ev.status_code == 201

    # --- add an officer remark ---
    client.post(f"/api/v1/incidents/{incident_id}/notes", json={"body": "Vehicle confirmed stolen"},
                headers=bearer(officer_tok))

    # --- create case ---
    case = client.post("/api/v1/cases", json={"title": f"Stolen {PLATE}", "primary_plate_number": PLATE,
                       "priority_level": "CRITICAL"}, headers=bearer(officer_tok))
    assert case.status_code == 201
    case_id = case.json()["id"]

    # --- attach incident + evidence + note to the case ---
    client.post(f"/api/v1/cases/{case_id}/incidents", json={"incident_id": incident_id},
                headers=bearer(officer_tok))
    for eid in event_ids:
        client.post(f"/api/v1/cases/{case_id}/evidence", json={"vehicle_event_id": eid},
                    headers=bearer(officer_tok))
    client.post(f"/api/v1/cases/{case_id}/notes", json={"body": "Coordinating with local station"},
                headers=bearer(officer_tok))

    detail = client.get(f"/api/v1/cases/{case_id}", headers=bearer(officer_tok)).json()
    assert detail["incident_count"] == 1
    assert detail["evidence_count"] == 3
    assert detail["sighting_count"] >= 3
    assert incident["incident_number"] in [i["incident_number"] for i in detail["incidents"]]

    # --- generate case report (CSV) ---
    rep = client.get(f"/api/v1/cases/{case_id}/report", params={"format": "csv"},
                     headers=bearer(officer_tok))
    assert rep.status_code == 200 and PLATE in rep.text

    # --- resolve incident ---
    res = client.post(f"/api/v1/incidents/{incident_id}/status", json={"status": "RESOLVED"},
                      headers=bearer(officer_tok))
    assert res.json()["status"] == "RESOLVED" and res.json()["resolved_by_username"] == "test_officer"

    # --- close case ---
    clo = client.patch(f"/api/v1/cases/{case_id}", json={"status": "CLOSED"}, headers=bearer(officer_tok))
    assert clo.json()["status"] == "CLOSED"

    # --- the whole chain is on the audit trail ---
    audit = client.get("/api/v1/admin/audit", params={"limit": 500}, headers=bearer(admin)).json()
    actions = {r["action"] for r in audit["items"]}
    for expected in {"ALERT_ACKNOWLEDGED", "INCIDENT_CREATE", "INCIDENT_ASSIGN", "VEHICLE_SEARCH",
                     "INCIDENT_EVIDENCE_ADD", "INCIDENT_NOTE_ADD", "CASE_CREATE", "CASE_INCIDENT_ADD",
                     "CASE_EVIDENCE_ADD", "CASE_REPORT_EXPORT", "INCIDENT_STATUS", "CASE_UPDATE"}:
        assert expected in actions, f"missing audit action {expected}"
