"""
Incident management (phase brief FEATURE 1).

Covers: create-from-alert + standalone, list/filter/pagination, status
lifecycle + accountability stamps, assignment, notes, evidence linking,
RBAC, and audit coverage. Every incident links back to its source rows
by FK -- no denormalised alert/vehicle/camera state.
"""
from sqlalchemy import select

from app.database import SessionLocal
from app.models.alert import Alert
from app.models.audit_log import AuditLog
from app.models.base import PriorityLevel
from app.models.watchlist import Watchlist
from conftest import bearer


def _make_alert(camera, event, plate="GJ18TC0450", priority=PriorityLevel.HIGH):
    with SessionLocal() as s:
        wl = Watchlist(
            plate_number=plate,
            plate_number_normalized=plate,
            offense_category="STOLEN",
            priority_level=priority,
        )
        s.add(wl)
        s.commit()
        s.refresh(wl)
        a = Alert(
            plate_number=plate,
            plate_number_normalized=plate,
            camera_id=camera.id,
            vehicle_event_id=event.id,
            watchlist_id=wl.id,
            priority_level=priority,
        )
        s.add(a)
        s.commit()
        s.refresh(a)
        return a.id


def _audit(action):
    with SessionLocal() as s:
        return s.execute(select(AuditLog).where(AuditLog.action == action)).scalars().all()


def test_create_incident_from_alert_links_source_rows(
    client, officer_user, make_camera, make_vehicle_event
):
    _, token = officer_user
    cam = make_camera(code="cam-inc-01")
    ev = make_vehicle_event(cam, plate="GJ18TC0450")
    alert_id = _make_alert(cam, ev)

    resp = client.post("/api/v1/incidents", json={"alert_id": alert_id}, headers=bearer(token))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["incident_number"].startswith("INC-")
    assert body["alert_id"] == alert_id
    assert body["vehicle_event_id"] == ev.id
    assert body["camera_id"] == cam.id
    assert body["camera_code"] == "cam-inc-01"
    assert body["plate_number_normalized"] == "GJ18TC0450"
    assert body["priority_level"] == "HIGH"
    assert body["status"] == "NEW"
    assert body["created_by_username"] == "test_officer"
    assert _audit("INCIDENT_CREATE")


def test_promoting_same_alert_twice_is_conflict(
    client, officer_user, make_camera, make_vehicle_event
):
    _, token = officer_user
    cam = make_camera(code="cam-inc-02")
    ev = make_vehicle_event(cam, plate="GJ01AB1111")
    alert_id = _make_alert(cam, ev)
    r1 = client.post("/api/v1/incidents", json={"alert_id": alert_id}, headers=bearer(token))
    assert r1.status_code == 201
    r2 = client.post("/api/v1/incidents", json={"alert_id": alert_id}, headers=bearer(token))
    assert r2.status_code == 409


def test_standalone_incident_without_alert(client, officer_user):
    _, token = officer_user
    resp = client.post(
        "/api/v1/incidents",
        json={"title": "Suspicious parking", "category": "SUSPICIOUS",
              "priority_level": "LOW", "plate_number": "gj 5 cd 9090"},
        headers=bearer(token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["alert_id"] is None
    assert body["plate_number_normalized"] == "GJ5CD9090"
    assert body["category"] == "SUSPICIOUS"


def test_status_lifecycle_stamps_accountability(client, officer_user):
    _, token = officer_user
    inc = client.post("/api/v1/incidents", json={"title": "T"}, headers=bearer(token)).json()
    iid = inc["id"]

    r = client.post(f"/api/v1/incidents/{iid}/status", json={"status": "ACKNOWLEDGED"},
                    headers=bearer(token))
    assert r.json()["acknowledged_by_username"] == "test_officer"
    assert r.json()["acknowledged_at"] is not None

    r = client.post(f"/api/v1/incidents/{iid}/status", json={"status": "RESOLVED"},
                    headers=bearer(token))
    assert r.json()["resolved_by_username"] == "test_officer"
    assert r.json()["resolved_at"] is not None
    assert _audit("INCIDENT_STATUS")


def test_assign_incident_notifies_and_acknowledges(client, admin_user, officer_user):
    _, admin_token = admin_user
    officer, _ = officer_user
    inc = client.post("/api/v1/incidents", json={"title": "Assign me"},
                      headers=bearer(admin_token)).json()
    r = client.post(f"/api/v1/incidents/{inc['id']}/assign", json={"user_id": officer.id},
                    headers=bearer(admin_token))
    assert r.status_code == 200
    assert r.json()["assigned_to_username"] == "test_officer"
    assert r.json()["status"] == "ACKNOWLEDGED"
    assert _audit("INCIDENT_ASSIGN")

    # officer sees a directed notification
    officer_token = officer_user[1]
    notifs = client.get("/api/v1/notifications", headers=bearer(officer_token)).json()
    assert any(n["type"] == "INCIDENT_ASSIGNED" for n in notifs["items"])


def test_notes_and_evidence_linking(client, officer_user, make_camera, make_vehicle_event):
    _, token = officer_user
    cam = make_camera(code="cam-inc-ev")
    ev = make_vehicle_event(cam, plate="GJ18TC0450")
    inc = client.post("/api/v1/incidents", json={"title": "N", "plate_number": "GJ18TC0450"},
                      headers=bearer(token)).json()
    iid = inc["id"]

    rn = client.post(f"/api/v1/incidents/{iid}/notes", json={"body": "Reviewed footage"},
                     headers=bearer(token))
    assert rn.status_code == 201
    assert rn.json()["author_username"] == "test_officer"

    re_ = client.post(f"/api/v1/incidents/{iid}/evidence",
                      json={"vehicle_event_id": ev.id, "note": "plate crop"}, headers=bearer(token))
    assert re_.status_code == 201
    link_id = re_.json()["id"]
    assert re_.json()["camera_code"] == "cam-inc-ev"

    # duplicate attach -> 409
    dup = client.post(f"/api/v1/incidents/{iid}/evidence", json={"vehicle_event_id": ev.id},
                      headers=bearer(token))
    assert dup.status_code == 409

    detail = client.get(f"/api/v1/incidents/{iid}", headers=bearer(token)).json()
    assert detail["note_count"] == 1
    assert detail["evidence_count"] == 1
    assert detail["related_sighting_count"] == 1

    d = client.delete(f"/api/v1/incidents/{iid}/evidence/{link_id}", headers=bearer(token))
    assert d.status_code == 204
    assert _audit("INCIDENT_EVIDENCE_REMOVE")


def test_list_filters_and_pagination(client, officer_user):
    _, token = officer_user
    for i in range(5):
        client.post("/api/v1/incidents",
                    json={"title": f"case {i}", "priority_level": "CRITICAL" if i == 0 else "LOW"},
                    headers=bearer(token))
    page = client.get("/api/v1/incidents", params={"limit": 2, "offset": 0}, headers=bearer(token))
    body = page.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2

    crit = client.get("/api/v1/incidents", params={"priority": "CRITICAL"}, headers=bearer(token))
    assert crit.json()["total"] == 1


def test_operator_cannot_mutate_but_can_view(client, operator_user, officer_user):
    officer_tok = officer_user[1]
    inc = client.post("/api/v1/incidents", json={"title": "RBAC"}, headers=bearer(officer_tok)).json()
    op_tok = operator_user[1]

    assert client.get("/api/v1/incidents", headers=bearer(op_tok)).status_code == 200
    assert client.get(f"/api/v1/incidents/{inc['id']}", headers=bearer(op_tok)).status_code == 200
    assert client.post("/api/v1/incidents", json={"title": "x"},
                       headers=bearer(op_tok)).status_code == 403
    assert client.post(f"/api/v1/incidents/{inc['id']}/notes", json={"body": "no"},
                       headers=bearer(op_tok)).status_code == 403


def test_incidents_require_auth(client):
    assert client.get("/api/v1/incidents").status_code == 401
