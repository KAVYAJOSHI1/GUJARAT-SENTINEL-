"""
Phase 16A -- /command-center/summary aggregation.

One bounded read-only call composed from existing services.
"""
from datetime import datetime, timedelta

from app.models.alert import Alert
from app.models.base import AlertStatus, CameraStatus, PriorityLevel
from app.models.incident import Incident
from conftest import bearer


def test_summary_shape_empty(client, officer_user):
    _, tok = officer_user
    r = client.get("/api/v1/command-center/summary", headers=bearer(tok))
    assert r.status_code == 200, r.text
    b = r.json()
    for key in ("kpis", "active_alerts", "active_investigations", "cameras",
                "problem_cameras", "recent_vehicles", "recent_anomalies", "metrics"):
        assert key in b
    for kpi in ("active_alerts", "escalated", "open_incidents", "open_cases",
                "cameras_online", "cameras_degraded", "cameras_offline",
                "cameras_poor_video", "vehicles_today", "anomalies_today"):
        assert kpi in b["kpis"]
    assert "single bounded aggregation" in b["note"].lower()


def test_summary_reflects_alerts_and_incidents(client, db_session, officer_user, make_camera, make_vehicle_event):
    _, tok = officer_user
    cam = make_camera(code="CAM-CC", status=CameraStatus.ONLINE)
    ev = make_vehicle_event(cam, plate="GJ18TC0450")
    a1 = Alert(plate_number="GJ18TC0450", plate_number_normalized="GJ18TC0450",
               camera_id=cam.id, vehicle_event_id=ev.id, status=AlertStatus.NEW,
               priority_level=PriorityLevel.CRITICAL)
    a2 = Alert(plate_number="GJ01AB0001", plate_number_normalized="GJ01AB0001",
               camera_id=cam.id, vehicle_event_id=ev.id, status=AlertStatus.ESCALATED,
               priority_level=PriorityLevel.HIGH)
    db_session.add_all([a1, a2])
    db_session.commit()
    db_session.add(Incident(incident_number="INC-2026-6001", title="t",
                            plate_number_normalized="GJ18TC0450"))
    db_session.commit()

    b = client.get("/api/v1/command-center/summary", headers=bearer(tok)).json()
    assert b["kpis"]["active_alerts"] == 1        # NEW only
    assert b["kpis"]["escalated"] == 1
    assert b["kpis"]["open_incidents"] == 1
    assert b["active_alerts_total"] == 2
    # ESCALATED sorts first
    assert b["active_alerts"][0]["severity"] == "ESCALATED"
    assert all("investigate_href" in x and "/workspace?plate=" in x["investigate_href"]
               for x in b["active_alerts"])
    assert any(i["label"] == "INC-2026-6001" for i in b["active_investigations"])


def test_summary_camera_states(client, db_session, officer_user, make_camera):
    _, tok = officer_user
    on = make_camera(code="CC-ON", status=CameraStatus.ONLINE)
    on.health_updated_at = datetime.utcnow()
    on.stream_fps = 25.0
    off = make_camera(code="CC-OFF", status=CameraStatus.OFFLINE)
    db_session.add_all([on, off])
    db_session.commit()

    b = client.get("/api/v1/command-center/summary", headers=bearer(tok)).json()
    states = {c["code"]: c["state"] for c in b["cameras"]}
    assert states["CC-ON"] == "ONLINE"
    assert states["CC-OFF"] == "OFFLINE"
    assert "CC-OFF" in {c["code"] for c in b["problem_cameras"]}


def test_summary_requires_auth(client):
    assert client.get("/api/v1/command-center/summary").status_code == 401
