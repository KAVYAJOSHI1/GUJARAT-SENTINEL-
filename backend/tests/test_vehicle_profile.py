"""
Phase 15D -- consolidated vehicle profile (opened from a search result).
"""
from datetime import datetime, timedelta

from app.models.alert import Alert
from app.models.base import PriorityLevel
from app.models.incident import Incident
from app.models.watchlist import Watchlist
from conftest import bearer

PLATE = "GJ18TC0450"


def test_profile_consolidates_everything(client, db_session, officer_user, make_camera, make_vehicle_event):
    _, tok = officer_user
    cams = [make_camera(code=f"CAM-{i}", lat=23.0 + i * 0.01, lon=72.55 + i * 0.01) for i in range(3)]
    base = datetime.utcnow() - timedelta(hours=1)
    evs = []
    for i, c in enumerate(cams):
        evs.append(make_vehicle_event(c, plate=PLATE, track_id=i + 1,
                                      ts=base + timedelta(minutes=8 * i),
                                      latitude=23.0 + i * 0.01, longitude=72.55 + i * 0.01,
                                      location=f"SRID=4326;POINT({72.55 + i * 0.01} {23.0 + i * 0.01})",
                                      vehicle_type="car", vehicle_color="white"))
    # one UNKNOWN sighting with a reason
    u = make_vehicle_event(cams[0], plate="UNKNOWN", track_id=99, ts=base + timedelta(minutes=30))
    u.anpr_status = "UNKNOWN"
    u.anpr_failure_reason = "BLUR"
    db_session.add(u)
    db_session.add(Watchlist(plate_number=PLATE, plate_number_normalized=PLATE,
                             offense_category="STOLEN", priority_level=PriorityLevel.HIGH))
    alert = Alert(plate_number=PLATE, plate_number_normalized=PLATE, camera_id=cams[0].id,
                  vehicle_event_id=evs[0].id)
    db_session.add(alert)
    db_session.commit()
    db_session.refresh(alert)
    db_session.add(Incident(incident_number="INC-2026-5555", title="t", alert_id=alert.id,
                            plate_number_normalized=PLATE))
    db_session.commit()

    r = client.get("/api/v1/vehicles/profile", params={"plate": PLATE}, headers=bearer(tok))
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["plate"] == PLATE
    assert p["total_sightings"] == 3
    assert p["distinct_cameras"] == 3
    assert p["is_watchlisted"] is True
    assert len(p["cameras"]) == 3
    assert p["cameras"][0]["sightings"] == 1
    assert p["journey"]["inferred_transitions"] == 2
    assert p["counts"]["alerts"] == 1
    assert p["counts"]["incidents"] == 1
    assert p["anpr_readable"] == 3
    kinds = {rel["kind"] for rel in p["related"]}
    assert {"ALERT", "INCIDENT"} <= kinds


def test_profile_unknown_plate_anpr_breakdown(client, db_session, officer_user, make_camera, make_vehicle_event):
    _, tok = officer_user
    cam = make_camera(code="CAM-U")
    for i, reason in enumerate(["BLUR", "LOW_RESOLUTION", "BLUR"]):
        ev = make_vehicle_event(cam, plate="UNKNOWN", track_id=i + 1,
                                ts=datetime.utcnow() - timedelta(minutes=i))
        ev.anpr_status = "UNKNOWN"
        ev.anpr_failure_reason = reason
        db_session.add(ev)
    db_session.commit()
    p = client.get("/api/v1/vehicles/profile", params={"plate": "UNKNOWN"}, headers=bearer(tok)).json()
    assert p["anpr_unknown"] == 3
    assert p["anpr_failure_reasons"]["BLUR"] == 2


def test_profile_requires_auth(client):
    assert client.get("/api/v1/vehicles/profile?plate=GJ18TC0450").status_code == 401


def test_profile_empty_for_unknown_vehicle(client, officer_user):
    _, tok = officer_user
    p = client.get("/api/v1/vehicles/profile", params={"plate": "GJ00ZZ0000"}, headers=bearer(tok)).json()
    assert p["total_sightings"] == 0
    assert p["cameras"] == []
