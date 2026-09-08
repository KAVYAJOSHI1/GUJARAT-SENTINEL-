"""
Phase 14 (7/7) -- Investigation Graph.

Covers: node/edge construction from persisted rows, the full
vehicle -> detection -> camera -> alert -> incident -> evidence -> case
chain, visual-match edges, camera-transition edges, watchlist edge,
missing relationships (empty graph), determinism, bounded output, endpoint.
"""
from datetime import datetime, timedelta

from app.models.alert import Alert
from app.models.base import PriorityLevel
from app.models.case import Case, CaseEvidence, CaseIncident
from app.models.incident import Incident, IncidentEvidence
from app.models.watchlist import Watchlist
from app.services.ai.graph import InvestigationGraphService
from conftest import bearer

PLATE = "GJ18TC0450"


def _cam(make_camera, code, lat, lon):
    c = make_camera(code=code, lat=lat, lon=lon)
    c._lat, c._lon = lat, lon
    return c


def _full_case(db, make_camera, mk):
    cams = [_cam(make_camera, f"CAM-{i}", 23.0 + i * 0.01, 72.55 + i * 0.01) for i in range(3)]
    base = datetime.utcnow() - timedelta(hours=1)
    evs = [mk(c, plate=PLATE, track_id=i + 1, ts=base + timedelta(minutes=6 * i),
              latitude=c._lat, longitude=c._lon,
              location=f"SRID=4326;POINT({c._lon} {c._lat})",
              vehicle_type="car", vehicle_color="white") for i, c in enumerate(cams)]
    db.add(Watchlist(plate_number=PLATE, plate_number_normalized=PLATE,
                     offense_category="STOLEN", priority_level=PriorityLevel.HIGH))
    alert = Alert(plate_number=PLATE, plate_number_normalized=PLATE,
                  camera_id=cams[0].id, vehicle_event_id=evs[0].id)
    db.add(alert)
    db.commit()
    db.refresh(alert)
    inc = Incident(incident_number="INC-2026-7777", title="t", alert_id=alert.id,
                   vehicle_event_id=evs[0].id, camera_id=cams[0].id,
                   plate_number_normalized=PLATE)
    db.add(inc)
    db.commit()
    db.refresh(inc)
    db.add(IncidentEvidence(incident_id=inc.id, vehicle_event_id=evs[0].id))
    case = Case(case_number="CASE-2026-7777", title="c", primary_plate_normalized=PLATE)
    db.add(case)
    db.commit()
    db.refresh(case)
    db.add(CaseIncident(case_id=case.id, incident_id=inc.id))
    db.add(CaseEvidence(case_id=case.id, vehicle_event_id=evs[1].id))
    db.commit()
    return cams, evs, alert, inc, case


def test_graph_full_chain(db_session, make_camera, make_vehicle_event):
    _full_case(db_session, make_camera, make_vehicle_event)
    g = InvestigationGraphService(db_session).build_for_plate(PLATE)

    types = g["counts_by_type"]
    assert types.get("vehicle", 0) >= 1
    assert types.get("detection") == 3
    assert types.get("camera") == 3
    assert types.get("location") == 3
    assert types.get("alert") == 1
    assert types.get("incident") == 1
    assert types.get("case") == 1
    assert types.get("evidence", 0) >= 1
    assert types.get("watchlist") == 1

    kinds = {e["kind"] for e in g["edges"]}
    assert {"detected_as", "at_camera", "located_at", "raised_alert",
            "promoted_to", "has_evidence", "on_watchlist"} <= kinds

    # every node has an href to its Sentinel page
    assert all(n["href"] for n in g["nodes"])
    assert g["truncated"] is False


def test_graph_is_deterministic(db_session, make_camera, make_vehicle_event):
    _full_case(db_session, make_camera, make_vehicle_event)
    svc = InvestigationGraphService(db_session)
    a = svc.build_for_plate(PLATE)
    b = InvestigationGraphService(db_session).build_for_plate(PLATE)
    assert a["node_count"] == b["node_count"]
    assert a["edge_count"] == b["edge_count"]
    assert {n["id"] for n in a["nodes"]} == {n["id"] for n in b["nodes"]}


def test_graph_visual_match_edges(db_session, make_camera, make_vehicle_event):
    a = _cam(make_camera, "CAM-V1", 23.0, 72.55)
    b = _cam(make_camera, "CAM-V2", 23.01, 72.56)
    base = datetime.utcnow() - timedelta(hours=1)
    make_vehicle_event(a, plate=PLATE, track_id=1, ts=base, latitude=23.0, longitude=72.55,
                       location="SRID=4326;POINT(72.55 23.0)", vehicle_type="car", vehicle_color="white")
    # a look-alike white car, different plate
    make_vehicle_event(b, plate="GJ09LK1010", track_id=2, ts=base + timedelta(minutes=3),
                       latitude=23.01, longitude=72.56,
                       location="SRID=4326;POINT(72.56 23.01)", vehicle_type="car", vehicle_color="white")
    g = InvestigationGraphService(db_session).build_for_plate(PLATE)
    vm = [e for e in g["edges"] if e["kind"] == "visual_match"]
    assert vm and "%" in (vm[0]["label"] or "")
    assert any(n["id"] == "vehicle:GJ09LK1010" for n in g["nodes"])


def test_graph_empty_for_unknown_plate(db_session):
    g = InvestigationGraphService(db_session).build_for_plate("GJ00XX0000")
    # only the root vehicle node, no edges
    assert g["node_count"] == 1
    assert g["edge_count"] == 0
    assert g["nodes"][0]["type"] == "vehicle"


def test_graph_endpoint(client, db_session, officer_user, make_camera, make_vehicle_event):
    _, tok = officer_user
    _full_case(db_session, make_camera, make_vehicle_event)
    r = client.get(f"/api/v1/ai/graph?plate={PLATE}", headers=bearer(tok))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["subject"] == PLATE
    assert body["node_count"] > 5
    assert "persisted records" in body["note"]


def test_graph_requires_auth(client):
    assert client.get(f"/api/v1/ai/graph?plate={PLATE}").status_code == 401
