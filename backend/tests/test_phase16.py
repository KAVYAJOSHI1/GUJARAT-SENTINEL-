"""
Phase 16 -- Command Center & investigation UX.

Covers the read-only aggregations / routing contracts the redesigned
frontend relies on:
  * /command-center/summary completeness (KPIs, investigations, cameras)
  * global search routes vehicles/evidence to the unified /workspace
  * vehicle profile exposes clickable related entities
  * sighting feed_source labels provenance (DEMO / MOCK / REAL) everywhere
  * the evidence endpoint serves an honest placeholder (200) instead of 404
  * the operator work queue stays role-aware and priority-ordered
"""
from datetime import datetime, timedelta

from app.database import SessionLocal
from app.models.alert import Alert
from app.models.base import AlertStatus, CameraStatus, PriorityLevel
from app.models.case import Case
from app.models.incident import Incident
from app.models.watchlist import Watchlist
from conftest import bearer, media_ticket


def _watchlisted_alert(cam, ev, plate="GJ18TC0450", priority=PriorityLevel.HIGH,
                       status=AlertStatus.NEW):
    with SessionLocal() as s:
        wl = Watchlist(plate_number=plate, plate_number_normalized=plate,
                       offense_category="STOLEN", priority_level=priority)
        s.add(wl); s.commit(); s.refresh(wl)
        a = Alert(plate_number=plate, plate_number_normalized=plate, camera_id=cam.id,
                  vehicle_event_id=ev.id, watchlist_id=wl.id, priority_level=priority,
                  status=status)
        s.add(a); s.commit(); s.refresh(a)
        return a.id


# ── /command-center/summary ──────────────────────────────────────────────
def test_command_center_summary_is_one_call_with_everything(client, officer_user,
                                                            make_camera, make_vehicle_event):
    _, tok = officer_user
    cam = make_camera(code="CAM-P16A", status=CameraStatus.ONLINE)
    ev = make_vehicle_event(cam, plate="GJ18TC0450")
    _watchlisted_alert(cam, ev)

    b = client.get("/api/v1/command-center/summary", headers=bearer(tok)).json()
    # all 10 KPIs
    assert set(b["kpis"]) >= {
        "active_alerts", "escalated", "open_incidents", "open_cases",
        "cameras_online", "cameras_degraded", "cameras_offline",
        "cameras_poor_video", "vehicles_today", "anomalies_today",
    }
    assert b["kpis"]["active_alerts"] >= 1
    assert isinstance(b["active_alerts"], list) and b["active_alerts"]
    assert b["active_alerts"][0]["investigate_href"].startswith("/workspace?plate=")
    assert any(c["code"] == "CAM-P16A" for c in b["cameras"])


def test_command_center_summary_ranks_escalated_first(client, officer_user,
                                                      make_camera, make_vehicle_event):
    _, tok = officer_user
    cam = make_camera(code="CAM-P16B", status=CameraStatus.ONLINE)
    ev = make_vehicle_event(cam, plate="GJ01AA1111")
    _watchlisted_alert(cam, ev, plate="GJ01AA1111", priority=PriorityLevel.LOW)
    ev2 = make_vehicle_event(cam, plate="GJ01ZZ9999")
    _watchlisted_alert(cam, ev2, plate="GJ01ZZ9999", priority=PriorityLevel.MEDIUM,
                       status=AlertStatus.ESCALATED)

    b = client.get("/api/v1/command-center/summary", headers=bearer(tok)).json()
    assert b["active_alerts"][0]["severity"] == "ESCALATED"


# ── global search routing ────────────────────────────────────────────────
def test_global_search_routes_vehicle_to_workspace(client, officer_user,
                                                   make_camera, make_vehicle_event):
    _, tok = officer_user
    cam = make_camera(code="CAM-P16S")
    make_vehicle_event(cam, plate="GJ05SR4321")
    r = client.get("/api/v1/search/global", params={"q": "GJ05SR4321"}, headers=bearer(tok))
    assert r.status_code == 200
    groups = r.json()["groups"]
    vhits = groups.get("VEHICLES") or []
    assert vhits and vhits[0]["href"] == "/workspace?plate=GJ05SR4321"


# ── vehicle profile: clickable related entities ──────────────────────────
def test_vehicle_profile_related_entities_are_linkable(client, officer_user,
                                                       make_camera, make_vehicle_event):
    _, tok = officer_user
    cam = make_camera(code="CAM-P16R")
    ev = make_vehicle_event(cam, plate="GJ18TC0450")
    _watchlisted_alert(cam, ev)
    with SessionLocal() as s:
        s.add(Incident(incident_number="INC-2026-7777", title="t",
                       plate_number_normalized="GJ18TC0450"))
        s.add(Case(case_number="CASE-2026-7777", title="t",
                   primary_plate_normalized="GJ18TC0450"))
        s.commit()

    b = client.get("/api/v1/vehicles/profile", params={"plate": "GJ18TC0450"},
                   headers=bearer(tok)).json()
    kinds = {r["kind"]: r["href"] for r in b["related"]}
    assert kinds["INCIDENT"].startswith("/incidents/")
    assert kinds["CASE"].startswith("/cases/")
    assert kinds["ALERT"].startswith("/alerts")


# ── honest provenance everywhere ─────────────────────────────────────────
def test_feed_source_present_in_search_and_recent_events(client, officer_user,
                                                        make_camera, make_vehicle_event):
    _, tok = officer_user
    demo = make_camera(code="CAM-P16DEMO", is_demo=True)
    make_vehicle_event(demo, plate="GJ07DS0001")

    search = client.get("/api/v1/vehicles/search", params={"plate": "GJ07DS0001"},
                        headers=bearer(tok)).json()
    assert search["sightings"][0]["feed_source"] == "DEMO"

    recent = client.get("/api/v1/vehicles/events/recent", headers=bearer(tok)).json()
    assert all("feed_source" in s for s in recent)


# ── evidence endpoint: honest placeholder, never a 404 in the UI ─────────
def test_evidence_serves_placeholder_for_unresolvable_snapshot(client, officer_user,
                                                               make_camera, make_vehicle_event):
    _, tok = officer_user
    cam = make_camera(code="CAM-P16E")
    ev = make_vehicle_event(cam, plate="GJ09EV0001",
                            snapshot_url="file:///demo/evidence/nope.jpg")
    ticket = media_ticket(client, tok)
    r = client.get(f"/api/v1/vehicles/evidence/{ev.id}?token={ticket}")
    assert r.status_code == 200
    assert r.headers.get("X-Evidence-Status") in {"unavailable", "no-snapshot"}
    assert r.headers["content-type"].startswith("image/svg")


def test_evidence_unknown_event_still_404(client, officer_user):
    _, tok = officer_user
    ticket = media_ticket(client, tok)
    r = client.get(f"/api/v1/vehicles/evidence/00000000-0000-0000-0000-000000000000?token={ticket}")
    assert r.status_code == 404


# ── operator work queue stays role-aware + ordered ──────────────────────
def test_work_queue_priority_order_and_operator_scope(client, operator_user, admin_user,
                                                      make_camera, make_vehicle_event):
    _, op_tok = operator_user
    _, admin_tok = admin_user
    cam = make_camera(code="CAM-P16WQ")
    ev = make_vehicle_event(cam, plate="GJ11WQ0001")
    _watchlisted_alert(cam, ev, plate="GJ11WQ0001", priority=PriorityLevel.LOW)
    ev2 = make_vehicle_event(cam, plate="GJ11WQ0002")
    _watchlisted_alert(cam, ev2, plate="GJ11WQ0002", priority=PriorityLevel.CRITICAL)

    op = client.get("/api/v1/work-queue", headers=bearer(op_tok)).json()
    assert op["scope"] == "assigned"

    adm = client.get("/api/v1/work-queue", params={"sort": "priority"},
                     headers=bearer(admin_tok)).json()
    assert adm["scope"] == "all"
    alerts = adm["alerts"]
    if len(alerts) >= 2:
        ranks = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        seq = [ranks.get(a["priority"], 9) for a in alerts]
        assert seq == sorted(seq)


def test_work_queue_requires_auth(client):
    assert client.get("/api/v1/work-queue").status_code == 401


# ── command center: KPI correctness ─────────────────────────────────────
def test_command_center_excludes_resolved_alert(client, db_session, officer_user,
                                                make_camera, make_vehicle_event):
    _, tok = officer_user
    cam = make_camera(code="CAM-P16RES", status=CameraStatus.ONLINE)
    ev = make_vehicle_event(cam, plate="GJ22RS0001")
    db_session.add(Alert(plate_number="GJ22RS0001", plate_number_normalized="GJ22RS0001",
                         camera_id=cam.id, vehicle_event_id=ev.id,
                         status=AlertStatus.RESOLVED, priority_level=PriorityLevel.HIGH))
    db_session.commit()
    b = client.get("/api/v1/command-center/summary", headers=bearer(tok)).json()
    assert not any(a["plate"] == "GJ22RS0001" for a in b["active_alerts"])


def test_command_center_open_case_is_an_active_investigation(client, db_session, officer_user):
    _, tok = officer_user
    db_session.add(Case(case_number="CASE-2026-8888", title="active",
                        primary_plate_normalized="GJ33CS0001"))
    db_session.commit()
    b = client.get("/api/v1/command-center/summary", headers=bearer(tok)).json()
    hit = [i for i in b["active_investigations"] if i["label"] == "CASE-2026-8888"]
    assert hit and hit[0]["kind"] == "CASE" and hit[0]["href"].startswith("/cases/")


def test_command_center_recent_vehicle_has_workspace_href(client, officer_user,
                                                          make_camera, make_vehicle_event):
    _, tok = officer_user
    cam = make_camera(code="CAM-P16RV", status=CameraStatus.ONLINE)
    make_vehicle_event(cam, plate="GJ44RV0001")
    b = client.get("/api/v1/command-center/summary", headers=bearer(tok)).json()
    rv = [v for v in b["recent_vehicles"] if v["plate"] == "GJ44RV0001"]
    assert rv and rv[0]["href"] == "/workspace?plate=GJ44RV0001"
    assert b["kpis"]["vehicles_today"] >= 1


def test_command_center_camera_carries_feed_source(client, officer_user, make_camera):
    _, tok = officer_user
    make_camera(code="CAM-P16FS-DEMO", status=CameraStatus.ONLINE, is_demo=True)
    b = client.get("/api/v1/command-center/summary", headers=bearer(tok)).json()
    src = {c["code"]: c["feed_source"] for c in b["cameras"]}
    assert src["CAM-P16FS-DEMO"] == "DEMO"


# ── evidence endpoint ──────────────────────────────────────────────────
def test_evidence_no_snapshot_serves_placeholder(client, officer_user,
                                                 make_camera, make_vehicle_event):
    _, tok = officer_user
    cam = make_camera(code="CAM-P16NS")
    ev = make_vehicle_event(cam, plate="GJ55NS0001")  # no snapshot_url
    ticket = media_ticket(client, tok)
    r = client.get(f"/api/v1/vehicles/evidence/{ev.id}?token={ticket}")
    assert r.status_code == 200
    assert r.headers.get("X-Evidence-Status") == "no-snapshot"


def test_evidence_access_is_audited(client, officer_user, make_camera, make_vehicle_event):
    from sqlalchemy import select as _select

    from app.models.audit_log import AuditLog

    _, tok = officer_user
    cam = make_camera(code="CAM-P16AUD")
    ev = make_vehicle_event(cam, plate="GJ66AU0001", snapshot_url="file:///demo/x.jpg")
    ticket = media_ticket(client, tok)
    client.get(f"/api/v1/vehicles/evidence/{ev.id}?token={ticket}")
    with SessionLocal() as db:
        actions = {r.action for r in db.execute(_select(AuditLog)).scalars()}
    assert "EVIDENCE_VIEW" in actions or "EVIDENCE_ACCESS" in actions or any(
        "EVIDENCE" in a for a in actions)


# ── global search: entity hrefs ────────────────────────────────────────
def test_global_search_camera_and_incident_hrefs(client, officer_user, make_camera):
    _, tok = officer_user
    make_camera(code="CAM-P16GS", name="Paldi Junction P16")
    inc = client.post("/api/v1/incidents", json={"title": "Paldi Junction P16 incident"},
                      headers=bearer(tok)).json()
    r = client.get("/api/v1/search/global", params={"q": "Paldi Junction P16"},
                   headers=bearer(tok)).json()
    cams = r["groups"].get("CAMERAS") or []
    incs = r["groups"].get("INCIDENTS") or []
    assert any(h["kind"] == "CAMERA" for h in cams)
    assert any(h["id"] == inc["id"] and h["href"].startswith("/incidents/") for h in incs)


def test_global_search_requires_auth(client):
    assert client.get("/api/v1/search/global", params={"q": "x"}).status_code == 401


# ── command center: additional states / access ─────────────────────────
def test_command_center_degraded_camera_state(client, db_session, officer_user, make_camera):
    _, tok = officer_user
    cam = make_camera(code="CAM-P16DEG", status=CameraStatus.ONLINE)
    cam.health_updated_at = datetime.utcnow()
    cam.stream_fps = 2.0  # below the 8 fps floor -> DEGRADED
    db_session.add(cam)
    db_session.commit()
    b = client.get("/api/v1/command-center/summary", headers=bearer(tok)).json()
    states = {c["code"]: c["state"] for c in b["cameras"]}
    assert states["CAM-P16DEG"] == "DEGRADED"
    assert b["kpis"]["cameras_degraded"] >= 1


def test_command_center_readable_by_operator(client, operator_user):
    _, tok = operator_user
    r = client.get("/api/v1/command-center/summary", headers=bearer(tok))
    assert r.status_code == 200


def test_command_center_alert_investigate_href_targets_the_plate(client, officer_user,
                                                                make_camera, make_vehicle_event):
    _, tok = officer_user
    cam = make_camera(code="CAM-P16IH", status=CameraStatus.ONLINE)
    ev = make_vehicle_event(cam, plate="GJ77IH0001")
    _watchlisted_alert(cam, ev, plate="GJ77IH0001")
    b = client.get("/api/v1/command-center/summary", headers=bearer(tok)).json()
    hit = [a for a in b["active_alerts"] if a["plate"] == "GJ77IH0001"]
    assert hit and "plate=GJ77IH0001" in hit[0]["investigate_href"]


def test_vehicle_search_feed_source_real_for_normal_camera(client, officer_user,
                                                          make_camera, make_vehicle_event):
    _, tok = officer_user
    cam = make_camera(code="CAM-P16REAL")
    make_vehicle_event(cam, plate="GJ88RL0001")
    s = client.get("/api/v1/vehicles/search", params={"plate": "GJ88RL0001"},
                   headers=bearer(tok)).json()
    assert s["sightings"][0]["feed_source"] == "REAL"
