"""
Phase 14 (5/7) -- AI Investigation Agent + gap detection.

Covers: multi-step tool planning, read-only enforcement, hallucination
prevention (empty DB / no plate), the strict tool registry, gap detection
(coverage / impossible travel / low-confidence ANPR / single sighting),
endpoints + audit + auth.
"""
from datetime import datetime, timedelta

from app.models.alert import Alert
from app.models.anomaly_event import AnomalyEvent
from app.models.incident import Incident
from app.models.vehicle_event import VehicleEvent
from app.services.ai.agent import InvestigationAgentService, ToolRegistry
from app.services.ai.gaps import InvestigationGapService
from conftest import bearer
from sqlalchemy import func, select

PLATE = "GJ18TC0450"


def _journey(mk, cams, plate, base, *, gap_min=6):
    evs = []
    for i, cam in enumerate(cams):
        evs.append(mk(cam, plate=plate, track_id=i + 1, ts=base + timedelta(minutes=i * gap_min),
                      latitude=cam._lat, longitude=cam._lon,
                      location=f"SRID=4326;POINT({cam._lon} {cam._lat})",
                      vehicle_type="car", vehicle_color="white"))
    return evs


def _cam(make_camera, code, lat, lon):
    c = make_camera(code=code, lat=lat, lon=lon)
    c._lat, c._lon = lat, lon
    return c


# --------------------------------------------------------------------------- #
#  agent
# --------------------------------------------------------------------------- #
def test_agent_investigates_vehicle(db_session, make_camera, make_vehicle_event):
    cams = [_cam(make_camera, f"CAM-{i}", 23.0 + i * 0.01, 72.55 + i * 0.01) for i in range(3)]
    base = datetime.utcnow() - timedelta(hours=1)
    evs = _journey(make_vehicle_event, cams, PLATE, base)
    db_session.add(Alert(plate_number=PLATE, plate_number_normalized=PLATE,
                         camera_id=cams[0].id, vehicle_event_id=evs[0].id))
    db_session.commit()

    report = InvestigationAgentService(db_session).run(f"Investigate {PLATE}")
    assert report["plate"] == PLATE
    assert report["read_only"] is True
    tools_run = {s["tool"] for s in report["steps"] if not s.get("skipped")}
    assert {"search_vehicle", "get_vehicle_journey", "detect_gaps"} <= tools_run
    titles = {s["title"] for s in report["sections"]}
    assert "Vehicle & journey" in titles and "Alerts" in titles
    assert PLATE in report["summary"]
    assert report["plan_source"] in ("deterministic", "llm")


def test_agent_no_plate_is_honest(db_session):
    report = InvestigationAgentService(db_session).run("what is going on today")
    assert report["plate"] is None
    assert "plate" in report["summary"].lower()
    # no fabricated vehicle sections
    assert all(s["title"] != "Vehicle & journey" for s in report["sections"])


def test_agent_unknown_plate_is_honest(db_session):
    report = InvestigationAgentService(db_session).run(f"Investigate {PLATE}")
    assert report["plate"] == PLATE
    assert "not available in recorded evidence" in report["sections"][0]["body"].lower()
    assert "does not appear in recorded evidence" in report["summary"].lower()
    assert report["confidence_score"] == 0.0


def test_agent_is_read_only(db_session, make_camera, make_vehicle_event):
    cams = [_cam(make_camera, f"CAM-R{i}", 23.0 + i * 0.01, 72.55) for i in range(3)]
    _journey(make_vehicle_event, cams, PLATE, datetime.utcnow() - timedelta(hours=1))

    def counts():
        return (
            db_session.execute(select(func.count(Alert.id))).scalar(),
            db_session.execute(select(func.count(Incident.id))).scalar(),
            db_session.execute(select(func.count(AnomalyEvent.id))).scalar(),
        )

    before = counts()
    InvestigationAgentService(db_session).run(f"Investigate {PLATE}")
    assert counts() == before                       # nothing created


def test_tool_registry_rejects_unknown_tool(db_session):
    reg = ToolRegistry(db_session)
    assert "search_vehicle" in reg.names()
    try:
        reg.call("run_raw_sql", query="DROP TABLE cameras")
        assert False, "unknown tool should raise"
    except KeyError:
        pass


# --------------------------------------------------------------------------- #
#  gap detection
# --------------------------------------------------------------------------- #
def test_gap_single_sighting(db_session, make_camera, make_vehicle_event):
    c = _cam(make_camera, "CAM-S1", 23.0, 72.55)
    make_vehicle_event(c, plate=PLATE, latitude=23.0, longitude=72.55,
                       location="SRID=4326;POINT(72.55 23.0)")
    res = InvestigationGapService(db_session).detect(PLATE)
    assert any(g["kind"] == "SINGLE_SIGHTING" for g in res["gaps"])


def test_gap_low_confidence_anpr(db_session, make_camera, make_vehicle_event):
    a = _cam(make_camera, "CAM-L1", 23.0, 72.55)
    b = _cam(make_camera, "CAM-L2", 23.001, 72.551)
    base = datetime.utcnow() - timedelta(hours=1)
    make_vehicle_event(a, plate=PLATE, track_id=1, ts=base, latitude=23.0, longitude=72.55,
                       location="SRID=4326;POINT(72.55 23.0)")
    lowconf = make_vehicle_event(b, plate=PLATE, track_id=2, ts=base + timedelta(minutes=3),
                                 latitude=23.001, longitude=72.551,
                                 location="SRID=4326;POINT(72.551 23.001)")
    lowconf.confidence_score = 0.30
    db_session.add(lowconf)
    db_session.commit()
    res = InvestigationGapService(db_session).detect(PLATE)
    assert any(g["kind"] == "LOW_CONFIDENCE_ANPR" for g in res["gaps"])


def test_gap_impossible_travel(db_session, make_camera, make_vehicle_event):
    a = _cam(make_camera, "CAM-I1", 23.0, 72.55)
    b = _cam(make_camera, "CAM-I2", 23.60, 73.20)          # ~90 km
    base = datetime.utcnow() - timedelta(hours=1)
    make_vehicle_event(a, plate=PLATE, track_id=1, ts=base, latitude=23.0, longitude=72.55,
                       location="SRID=4326;POINT(72.55 23.0)")
    make_vehicle_event(b, plate=PLATE, track_id=2, ts=base + timedelta(seconds=5),
                       latitude=23.60, longitude=73.20,
                       location="SRID=4326;POINT(73.20 23.60)")
    res = InvestigationGapService(db_session).detect(PLATE)
    kinds = {g["kind"] for g in res["gaps"]}
    assert "INCONSISTENT_TRAVEL" in kinds


def test_gap_missing_coverage(db_session, make_camera, make_vehicle_event):
    a = _cam(make_camera, "CAM-M1", 23.00, 72.55)
    mid = _cam(make_camera, "CAM-MID", 23.02, 72.57)       # on the path, no sighting
    b = _cam(make_camera, "CAM-M2", 23.04, 72.59)          # ~6 km from A
    base = datetime.utcnow() - timedelta(hours=1)
    make_vehicle_event(a, plate=PLATE, track_id=1, ts=base, latitude=23.00, longitude=72.55,
                       location="SRID=4326;POINT(72.55 23.00)")
    make_vehicle_event(b, plate=PLATE, track_id=2, ts=base + timedelta(minutes=12),
                       latitude=23.04, longitude=72.59,
                       location="SRID=4326;POINT(72.59 23.04)")
    res = InvestigationGapService(db_session).detect(PLATE)
    cov = [g for g in res["gaps"] if g["kind"] == "MISSING_COVERAGE"]
    assert cov and "CAM-MID" in cov[0].get("cameras_on_path", [])


def test_gap_no_sightings(db_session):
    res = InvestigationGapService(db_session).detect("GJ99XX0000")
    assert res["sighting_count"] == 0
    assert res["gaps"] == []
    assert "nothing to assess" in res["note"]


# --------------------------------------------------------------------------- #
#  API
# --------------------------------------------------------------------------- #
def test_run_endpoint_and_audit(client, db_session, officer_user, make_camera, make_vehicle_event):
    _, tok = officer_user
    cams = [_cam(make_camera, f"CAM-E{i}", 23.0 + i * 0.01, 72.55) for i in range(3)]
    _journey(make_vehicle_event, cams, PLATE, datetime.utcnow() - timedelta(hours=1))

    r = client.post("/api/v1/ai/investigation/run", json={"query": f"Investigate {PLATE}"},
                    headers=bearer(tok))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["plate"] == PLATE
    assert body["read_only"] is True
    assert len(body["steps"]) >= 3
    assert "AI-GENERATED" in body["disclaimer"]

    from app.models.audit_log import AuditLog
    actions = {a for (a,) in db_session.execute(select(AuditLog.action)).all()}
    assert "AI_INVESTIGATION_AGENT" in actions


def test_gaps_endpoint(client, officer_user, make_camera, make_vehicle_event):
    _, tok = officer_user
    c = _cam(make_camera, "CAM-GE", 23.0, 72.55)
    make_vehicle_event(c, plate=PLATE, latitude=23.0, longitude=72.55,
                       location="SRID=4326;POINT(72.55 23.0)")
    r = client.get(f"/api/v1/ai/investigation/gaps?plate={PLATE}", headers=bearer(tok))
    assert r.status_code == 200, r.text
    assert r.json()["sighting_count"] == 1


def test_run_requires_auth(client):
    assert client.post("/api/v1/ai/investigation/run", json={"query": "x"}).status_code == 401
