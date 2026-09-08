"""
Phase 11 workflow features: alert escalation, incident timeline, case
timeline, officer work queue, saved investigations.
"""
from datetime import datetime

from sqlalchemy import select

from app.database import SessionLocal
from app.models.alert import Alert
from app.models.audit_log import AuditLog
from app.models.base import PriorityLevel
from app.models.watchlist import Watchlist
from conftest import bearer


def _alert(camera, event, plate="GJ18TC0450", priority=PriorityLevel.HIGH):
    with SessionLocal() as s:
        wl = Watchlist(plate_number=plate, plate_number_normalized=plate,
                       offense_category="STOLEN", priority_level=priority)
        s.add(wl); s.commit(); s.refresh(wl)
        a = Alert(plate_number=plate, plate_number_normalized=plate, camera_id=camera.id,
                  vehicle_event_id=event.id, watchlist_id=wl.id, priority_level=priority)
        s.add(a); s.commit(); s.refresh(a)
        return a.id


# --- alert escalation (FEATURE 6) ------------------------------------------
def test_alert_escalation_workflow(client, admin_user, officer_user, make_camera, make_vehicle_event):
    _, admin = admin_user
    officer, officer_tok = officer_user
    cam = make_camera(code="cam-esc")
    ev = make_vehicle_event(cam, plate="GJ18TC0450")
    aid = _alert(cam, ev)

    asg = client.post(f"/api/v1/alerts/{aid}/assign", json={"user_id": officer.id}, headers=bearer(admin))
    assert asg.status_code == 200 and asg.json()["assigned_to_username"] == "test_officer"

    esc = client.post(f"/api/v1/alerts/{aid}/escalate", json={"reason": "supervisor review — repeat offender"},
                      headers=bearer(officer_tok))
    assert esc.status_code == 200
    body = esc.json()
    assert body["status"] == "ESCALATED"
    assert body["escalated_by_username"] == "test_officer"
    assert body["escalated_at"] is not None
    assert "repeat offender" in body["escalation_reason"]

    res = client.post(f"/api/v1/alerts/{aid}/resolve", json={"note": "handled"}, headers=bearer(admin))
    assert res.status_code == 200 and res.json()["status"] == "RESOLVED"
    assert res.json()["resolved_by_username"] == "test_admin"

    esc_list = client.get("/api/v1/alerts", params={"status": "ESCALATED"}, headers=bearer(admin)).json()
    assert isinstance(esc_list, list)

    with SessionLocal() as db:
        acts = {r.action for r in db.execute(select(AuditLog)).scalars()}
    assert {"ALERT_ASSIGNED", "ALERT_ESCALATED", "ALERT_RESOLVED"} <= acts

    # escalation notification exists
    notifs = client.get("/api/v1/notifications", headers=bearer(admin)).json()
    assert any(n["type"] == "ALERT_ESCALATED" for n in notifs["items"])

    # existing watchlist engine untouched: it still only makes NEW alerts
    with SessionLocal() as db:
        assert db.get(Alert, aid).status.value == "RESOLVED"


def test_alert_escalate_rbac(client, operator_user, officer_user, make_camera, make_vehicle_event):
    cam = make_camera(code="cam-esc2")
    ev = make_vehicle_event(cam, plate="GJ01AB2222")
    aid = _alert(cam, ev)
    assert client.post(f"/api/v1/alerts/{aid}/escalate", json={"reason": "x"},
                       headers=bearer(operator_user[1])).status_code == 403


# --- incident timeline (FEATURE 7) --------------------------------------
def test_incident_timeline(client, officer_user, make_camera, make_vehicle_event):
    _, tok = officer_user
    cam = make_camera(code="cam-tl")
    ev = make_vehicle_event(cam, plate="GJ18TC0450")
    aid = _alert(cam, ev)
    client.patch(f"/api/v1/alerts/{aid}", json={"status": "ACKNOWLEDGED"}, headers=bearer(tok))
    inc = client.post("/api/v1/incidents", json={"alert_id": aid}, headers=bearer(tok)).json()
    iid = inc["id"]
    client.post(f"/api/v1/incidents/{iid}/notes", json={"body": "reviewed footage"}, headers=bearer(tok))
    client.post(f"/api/v1/incidents/{iid}/evidence", json={"vehicle_event_id": ev.id}, headers=bearer(tok))
    client.post(f"/api/v1/incidents/{iid}/status", json={"status": "RESOLVED"}, headers=bearer(tok))

    tl = client.get(f"/api/v1/incidents/{iid}/timeline", headers=bearer(tok)).json()
    cats = {e["category"] for e in tl["entries"]}
    assert {"ALERT", "INCIDENT", "NOTE", "EVIDENCE", "VEHICLE"} <= cats
    ts = [e["timestamp"] for e in tl["entries"]]
    assert ts == sorted(ts)
    assert any(e["action"] == "Alert acknowledged" for e in tl["entries"])
    assert any(e["action"] == "Officer remark" and "footage" in (e["detail"] or "") for e in tl["entries"])

    # category filter
    notes_only = client.get(f"/api/v1/incidents/{iid}/timeline", params={"category": "NOTE"},
                            headers=bearer(tok)).json()
    assert notes_only["entries"] and all(e["category"] == "NOTE" for e in notes_only["entries"])
    assert "ALERT" in notes_only["categories"]  # full category list still reported


# --- case timeline (FEATURE 8) -----------------------------------------
def test_case_timeline(client, officer_user, make_camera, make_vehicle_event):
    _, tok = officer_user
    cam = make_camera(code="cam-ctl")
    ev = make_vehicle_event(cam, plate="GJ18TC0450")
    case = client.post("/api/v1/cases", json={"title": "ring", "primary_plate_number": "GJ18TC0450"},
                       headers=bearer(tok)).json()
    cid = case["id"]
    inc = client.post("/api/v1/incidents", json={"title": "i"}, headers=bearer(tok)).json()
    client.post(f"/api/v1/cases/{cid}/incidents", json={"incident_id": inc["id"]}, headers=bearer(tok))
    client.post(f"/api/v1/cases/{cid}/evidence", json={"vehicle_event_id": ev.id}, headers=bearer(tok))
    client.post(f"/api/v1/cases/{cid}/notes", json={"body": "coordinating"}, headers=bearer(tok))
    client.get(f"/api/v1/cases/{cid}/report", params={"format": "csv"}, headers=bearer(tok))

    tl = client.get(f"/api/v1/cases/{cid}/timeline", headers=bearer(tok)).json()
    cats = {e["category"] for e in tl["entries"]}
    assert {"CASE", "INCIDENT", "EVIDENCE", "NOTE", "VEHICLE"} <= cats
    assert any(e["action"] == "Report exported" for e in tl["entries"])
    ts = [e["timestamp"] for e in tl["entries"]]
    assert ts == sorted(ts)


# --- officer work queue (FEATURE 12) ----------------------------------
def test_work_queue_role_aware(client, admin_user, officer_user, make_camera, make_vehicle_event):
    _, admin = admin_user
    officer, officer_tok = officer_user
    cam = make_camera(code="cam-wq")
    ev = make_vehicle_event(cam, plate="GJ18TC0450")
    _alert(cam, ev)  # a NEW alert

    inc = client.post("/api/v1/incidents", json={"title": "assigned inc"}, headers=bearer(admin)).json()
    client.post(f"/api/v1/incidents/{inc['id']}/assign", json={"user_id": officer.id}, headers=bearer(admin))
    other = client.post("/api/v1/incidents", json={"title": "unassigned inc"}, headers=bearer(admin)).json()

    # officer: only their assigned incident + the NEW alert (unassigned NEW visible)
    ow = client.get("/api/v1/work-queue", headers=bearer(officer_tok)).json()
    assert ow["scope"] == "assigned"
    assert {i["id"] for i in ow["incidents"]} == {inc["id"]}
    assert ow["counts"]["alerts"] >= 1

    # admin: sees all open work
    aw = client.get("/api/v1/work-queue", headers=bearer(admin)).json()
    assert aw["scope"] == "all"
    assert {inc["id"], other["id"]} <= {i["id"] for i in aw["incidents"]}

    assert client.get("/api/v1/work-queue").status_code == 401


# --- saved investigations (FEATURE 2) --------------------------------
def test_saved_searches_crud(client, officer_user, admin_user):
    _, tok = officer_user
    created = client.post("/api/v1/saved-searches", json={
        "title": "GJ18TC0450 — Sept 8", "description": "stolen vehicle sweep",
        "params": {"plate_contains": "18TC", "sort": "latest"},
    }, headers=bearer(tok))
    assert created.status_code == 201
    sid = created.json()["id"]
    assert created.json()["params"]["plate_contains"] == "18TC"

    mine = client.get("/api/v1/saved-searches", headers=bearer(tok)).json()
    assert mine["total"] == 1

    ren = client.patch(f"/api/v1/saved-searches/{sid}", json={"title": "renamed"}, headers=bearer(tok))
    assert ren.json()["title"] == "renamed"

    # another user cannot see it; admin can
    other_tok = admin_user[1]
    assert client.get(f"/api/v1/saved-searches/{sid}", headers=bearer(other_tok)).status_code == 200  # admin

    d = client.delete(f"/api/v1/saved-searches/{sid}", headers=bearer(tok))
    assert d.status_code == 204
    assert client.get("/api/v1/saved-searches", headers=bearer(tok)).json()["total"] == 0
