"""
Case management (phase brief FEATURE 2).

Covers: create, unified detail view (incidents + evidence + notes +
derived timeline + live sighting count), incident/evidence attach+detach,
notes, assignment + notification, CSV/JSON report export, RBAC, audit.
"""
from sqlalchemy import select

from app.database import SessionLocal
from app.models.audit_log import AuditLog
from conftest import bearer


def _audit(action):
    with SessionLocal() as s:
        return s.execute(select(AuditLog).where(AuditLog.action == action)).scalars().all()


def test_create_case_generates_number_and_normalises_plate(client, officer_user):
    _, token = officer_user
    r = client.post("/api/v1/cases",
                    json={"title": "Stolen GJ18TC0450 ring", "primary_plate_number": "gj18 tc 0450"},
                    headers=bearer(token))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["case_number"].startswith("CASE-")
    assert body["primary_plate_normalized"] == "GJ18TC0450"
    assert body["status"] == "OPEN"
    assert _audit("CASE_CREATE")


def test_unified_case_view(client, officer_user, make_camera, make_vehicle_event):
    _, token = officer_user
    cam = make_camera(code="cam-case-01")
    ev1 = make_vehicle_event(cam, plate="GJ18TC0450", track_id=1)
    ev2 = make_vehicle_event(cam, plate="GJ18TC0450", track_id=2)

    case = client.post("/api/v1/cases",
                       json={"title": "Ring", "primary_plate_number": "GJ18TC0450"},
                       headers=bearer(token)).json()
    cid = case["id"]

    inc = client.post("/api/v1/incidents",
                      json={"title": "hit", "plate_number": "GJ18TC0450"},
                      headers=bearer(token)).json()

    ra = client.post(f"/api/v1/cases/{cid}/incidents", json={"incident_id": inc["id"]},
                     headers=bearer(token))
    assert ra.status_code == 201
    assert _audit("CASE_INCIDENT_ADD")

    for ev in (ev1, ev2):
        rr = client.post(f"/api/v1/cases/{cid}/evidence", json={"vehicle_event_id": ev.id},
                         headers=bearer(token))
        assert rr.status_code == 201

    client.post(f"/api/v1/cases/{cid}/notes", json={"body": "Vehicle seen at 3 cameras"},
                headers=bearer(token))

    detail = client.get(f"/api/v1/cases/{cid}", headers=bearer(token)).json()
    assert detail["incident_count"] == 1
    assert detail["evidence_count"] == 2
    assert detail["note_count"] == 1
    assert detail["sighting_count"] == 2  # live count for GJ18TC0450
    assert len(detail["incidents"]) == 1
    assert detail["incidents"][0]["incident_number"] == inc["incident_number"]
    kinds = {e["kind"] for e in detail["timeline"]}
    assert {"CASE_CREATED", "INCIDENT", "EVIDENCE", "NOTE"} <= kinds
    # timeline is chronological
    ts = [e["timestamp"] for e in detail["timeline"]]
    assert ts == sorted(ts)


def test_duplicate_incident_link_conflicts(client, officer_user):
    _, token = officer_user
    case = client.post("/api/v1/cases", json={"title": "c"}, headers=bearer(token)).json()
    inc = client.post("/api/v1/incidents", json={"title": "i"}, headers=bearer(token)).json()
    a = client.post(f"/api/v1/cases/{case['id']}/incidents", json={"incident_id": inc["id"]},
                    headers=bearer(token))
    assert a.status_code == 201
    b = client.post(f"/api/v1/cases/{case['id']}/incidents", json={"incident_id": inc["id"]},
                    headers=bearer(token))
    assert b.status_code == 409
    d = client.delete(f"/api/v1/cases/{case['id']}/incidents/{inc['id']}", headers=bearer(token))
    assert d.status_code == 204


def test_case_incident_link_is_reflected_on_incident_detail(client, officer_user):
    _, token = officer_user
    case = client.post("/api/v1/cases", json={"title": "c"}, headers=bearer(token)).json()
    inc = client.post("/api/v1/incidents", json={"title": "i"}, headers=bearer(token)).json()
    client.post(f"/api/v1/cases/{case['id']}/incidents", json={"incident_id": inc["id"]},
                headers=bearer(token))
    detail = client.get(f"/api/v1/incidents/{inc['id']}", headers=bearer(token)).json()
    assert case["case_number"] in detail["case_numbers"]


def test_assign_case_notifies_officer(client, admin_user, officer_user):
    _, admin_token = admin_user
    officer, officer_token = officer_user
    case = client.post("/api/v1/cases", json={"title": "assign"}, headers=bearer(admin_token)).json()
    r = client.post(f"/api/v1/cases/{case['id']}/assign", json={"user_id": officer.id},
                    headers=bearer(admin_token))
    assert r.json()["assigned_to_username"] == "test_officer"
    assert _audit("CASE_ASSIGN")
    notifs = client.get("/api/v1/notifications", headers=bearer(officer_token)).json()
    assert any(n["type"] == "CASE_ASSIGNED" for n in notifs["items"])


def test_case_report_export_json_and_csv(client, officer_user, make_camera, make_vehicle_event):
    _, token = officer_user
    cam = make_camera(code="cam-rep")
    ev = make_vehicle_event(cam, plate="GJ18TC0450")
    case = client.post("/api/v1/cases", json={"title": "Report case",
                       "primary_plate_number": "GJ18TC0450"}, headers=bearer(token)).json()
    client.post(f"/api/v1/cases/{case['id']}/evidence", json={"vehicle_event_id": ev.id},
                headers=bearer(token))

    j = client.get(f"/api/v1/cases/{case['id']}/report", headers=bearer(token))
    assert j.status_code == 200
    assert j.json()["case_number"] == case["case_number"]

    c = client.get(f"/api/v1/cases/{case['id']}/report", params={"format": "csv"},
                   headers=bearer(token))
    assert c.status_code == 200
    assert c.headers["content-type"].startswith("text/csv")
    assert "SENTINEL Case Report" in c.text
    assert "GJ18TC0450" in c.text
    assert _audit("CASE_REPORT_EXPORT")


def test_case_rbac(client, operator_user, officer_user):
    officer_token = officer_user[1]
    case = client.post("/api/v1/cases", json={"title": "x"}, headers=bearer(officer_token)).json()
    op_token = operator_user[1]
    assert client.get("/api/v1/cases", headers=bearer(op_token)).status_code == 200
    assert client.get(f"/api/v1/cases/{case['id']}", headers=bearer(op_token)).status_code == 200
    assert client.get(f"/api/v1/cases/{case['id']}/report", headers=bearer(op_token)).status_code == 200
    assert client.post("/api/v1/cases", json={"title": "no"},
                       headers=bearer(op_token)).status_code == 403
    assert client.post(f"/api/v1/cases/{case['id']}/notes", json={"body": "no"},
                       headers=bearer(op_token)).status_code == 403


def test_cases_require_auth(client):
    assert client.get("/api/v1/cases").status_code == 401
