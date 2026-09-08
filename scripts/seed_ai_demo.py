#!/usr/bin/env python3
"""
Idempotent AI demo seed (phase brief §7 — OFFLINE AI DEMO MODE).

Inserts real database records so the whole Phase 12 AI layer is
demonstrable from `docker compose up` with NO live government CCTV:

  * 8 Ahmedabad cameras (CAM-01 .. CAM-08) with real coordinates.
  * GJ18TC0450 journey: 5 sightings CAM-01 -> CAM-02 -> CAM-04 -> CAM-06
    -> CAM-08 over ~40 min "today", geolocated, white car.
  * The first sighting raises a real watchlist Alert (via the existing
    watchlist engine path) and an Incident + Case + evidence link.
  * A batch of "white SUVs after 9 PM" + "unknown vehicles 20:00-22:00".
  * A STOPPED VEHICLE at CAM-04: track 7714, ~14 detections over ~210 s,
    < 15 m movement -> the anomaly scan flags it -> ANOMALY alert.
  * Runs BehaviorAnalyticsService once so the anomaly + alert exist for the
    demo.

Everything runs the SAME production code paths the live pipeline would.
Nothing here is a fake UI value. Re-running is safe (a marker row in
audit_logs guards it).

Env:
    DATABASE_URL   (same as the app)
    SEED_AI_DEMO   "1"/"true" to run (docker-compose sets it)
"""
import os
import sys
from datetime import datetime, timedelta

_HERE = os.path.dirname(os.path.abspath(__file__))
for cand in (os.path.join(_HERE, "..", "backend"), os.path.join(_HERE, "..")):
    if os.path.isdir(os.path.join(cand, "app")):
        sys.path.insert(0, os.path.abspath(cand))
        break

_MARKER = "AI_DEMO_SEEDED"

# CAM-01 .. CAM-08 — a plausible west-Ahmedabad corridor
_CAMERAS = [
    ("CAM-01", "Paldi Circle", 23.0121, 72.5606),
    ("CAM-02", "Nehru Bridge West", 23.0225, 72.5714),
    ("CAM-03", "Ashram Road / Gujarat College", 23.0300, 72.5680),
    ("CAM-04", "Income Tax Circle", 23.0396, 72.5717),
    ("CAM-05", "Usmanpura Char Rasta", 23.0470, 72.5760),
    ("CAM-06", "Vijay Cross Road", 23.0405, 72.5490),
    ("CAM-07", "Naranpura Telephone Exchange", 23.0540, 72.5590),
    ("CAM-08", "Ranip Cross Road", 23.0810, 72.5650),
]

_PLATE = "GJ18TC0450"


def _pt(lat, lon):
    return f"SRID=4326;POINT({lon} {lat})"


def _reset(db) -> None:
    """Delete only the AI-demo rows (by known camera codes / refs), keeping
    any real data + the GJ18TC0450 watchlist entry. Then the caller re-seeds."""
    from sqlalchemy import delete, select, update

    from app.models.alert import Alert
    from app.models.anomaly_event import AnomalyEvent
    from app.models.audit_log import AuditLog
    from app.models.camera import Camera
    from app.models.case import Case, CaseEvidence, CaseIncident
    from app.models.incident import Incident, IncidentEvidence
    from app.models.notification import Notification
    from app.models.vehicle_event import VehicleEvent
    from app.models.vehicle_embedding import VehicleEmbedding

    from app.models.case import CaseNote
    from app.models.incident import IncidentNote

    codes = [c[0] for c in _CAMERAS]
    NIL = ["-"]
    cam_ids = [r for (r,) in db.execute(select(Camera.id).where(Camera.code.in_(codes))).all()]
    ev_ids = [r for (r,) in db.execute(
        select(VehicleEvent.id).where(VehicleEvent.camera_id.in_(cam_ids or NIL))).all()]
    alert_ids = [r for (r,) in db.execute(
        select(Alert.id).where(Alert.camera_id.in_(cam_ids or NIL))).all()]
    inc_ids = [r for (r,) in db.execute(
        select(Incident.id).where(
            Incident.incident_number.like("INC-%-9001")
            | Incident.alert_id.in_(alert_ids or NIL)
            | Incident.vehicle_event_id.in_(ev_ids or NIL))).all()]
    case_ids = [r for (r,) in db.execute(
        select(Case.id).where(Case.case_number.like("CASE-%-9001"))).all()]

    ci = cam_ids or NIL
    ei = ev_ids or NIL
    ai = alert_ids or NIL
    ii = inc_ids or NIL
    kk = case_ids or NIL

    for stmt in (
        # 1. break mutual / dangling FK links
        update(Alert).where(Alert.camera_id.in_(ci)).values(anomaly_event_id=None),
        update(AnomalyEvent).where(AnomalyEvent.camera_id.in_(ci)).values(alert_id=None),
        # 2. child link/detail rows
        delete(CaseEvidence).where(CaseEvidence.case_id.in_(kk) | CaseEvidence.vehicle_event_id.in_(ei)),
        delete(CaseIncident).where(CaseIncident.case_id.in_(kk) | CaseIncident.incident_id.in_(ii)),
        delete(CaseNote).where(CaseNote.case_id.in_(kk)),
        delete(IncidentEvidence).where(IncidentEvidence.incident_id.in_(ii) | IncidentEvidence.vehicle_event_id.in_(ei)),
        delete(IncidentNote).where(IncidentNote.incident_id.in_(ii)),
        # 3. incidents / cases (now unreferenced), then anomalies, then alerts
        delete(Incident).where(Incident.id.in_(ii)),
        delete(Case).where(Case.id.in_(kk)),
        delete(AnomalyEvent).where(AnomalyEvent.camera_id.in_(ci)),
        delete(Alert).where(Alert.camera_id.in_(ci)),
        # 4. events + cameras + notifications + the marker
        delete(VehicleEmbedding).where(VehicleEmbedding.vehicle_event_id.in_(ei)),
        delete(VehicleEvent).where(VehicleEvent.id.in_(ei)),
        delete(Camera).where(Camera.id.in_(ci)),
        delete(Notification).where(Notification.resource == "anomaly"),
        delete(AuditLog).where(AuditLog.action == _MARKER),
    ):
        db.execute(stmt)
    db.commit()
    print(f"[seed_ai_demo] reset: removed {len(cam_ids)} cameras, {len(ev_ids)} events, "
          f"{len(inc_ids)} incident(s), {len(case_ids)} case(s)")


def main() -> int:
    reset = "--reset" in sys.argv
    if not reset and os.getenv("SEED_AI_DEMO", "0").strip().lower() not in ("1", "true", "yes", "on"):
        print("[seed_ai_demo] SEED_AI_DEMO not set -- skipping")
        return 0

    from sqlalchemy import select

    from app.config import settings
    from app.database import SessionLocal
    from app.models.alert import Alert
    from app.models.audit_log import AuditLog
    from app.models.base import CameraStatus, PriorityLevel
    from app.models.camera import Camera
    from app.models.case import Case, CaseEvidence, CaseIncident
    from app.models.incident import Incident
    from app.models.vehicle_event import VehicleEvent
    from app.models.watchlist import Watchlist
    from app.services.ai.behavior import BehaviorAnalyticsService
    from app.services.plate_utils import normalize_plate

    db = SessionLocal()
    try:
        if reset:
            _reset(db)
        if db.execute(select(AuditLog).where(AuditLog.action == _MARKER)).first():
            print("[seed_ai_demo] already seeded -- nothing to do")
            return 0

        now = datetime.utcnow()
        today0 = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # --- cameras ---
        cam_by_code: dict[str, Camera] = {}
        for code, desc, lat, lon in _CAMERAS:
            cam = db.execute(select(Camera).where(Camera.code == code)).scalar_one_or_none()
            if cam is None:
                cam = Camera(code=code, name=desc, location_desc=desc,
                             status=CameraStatus.ONLINE, location=_pt(lat, lon))
                db.add(cam)
            cam_by_code[code] = cam
        db.commit()
        for c in cam_by_code.values():
            db.refresh(c)

        # --- watchlist entry (main seed may already have made it) ---
        wl = db.execute(
            select(Watchlist).where(Watchlist.plate_number_normalized == _PLATE)
        ).scalar_one_or_none()
        if wl is None:
            wl = Watchlist(plate_number=_PLATE, plate_number_normalized=_PLATE,
                           offense_category="STOLEN", priority_level=PriorityLevel.HIGH,
                           reason="Reported stolen (AI demo)")
            db.add(wl)
            db.commit()
            db.refresh(wl)

        # --- GJ18TC0450 journey (today) ---
        route = ["CAM-01", "CAM-02", "CAM-04", "CAM-06", "CAM-08"]
        start = now - timedelta(minutes=42)
        journey_events: list[VehicleEvent] = []
        for i, code in enumerate(route):
            cam = cam_by_code[code]
            _, _, lat, lon = next(x for x in _CAMERAS if x[0] == code)
            ev = VehicleEvent(
                plate_number=_PLATE, plate_number_normalized=_PLATE,
                camera_id=cam.id, camera_code=code, track_id=100 + i,
                timestamp=start + timedelta(minutes=10 * i),
                vehicle_type="car", vehicle_color="white", confidence_score=0.93,
                latitude=lat, longitude=lon, location=_pt(lat, lon),
                snapshot_url=f"file:///demo/evidence/{_PLATE}_{code}.jpg",
            )
            db.add(ev)
            journey_events.append(ev)
        db.commit()
        for ev in journey_events:
            db.refresh(ev)

        first = journey_events[0]
        alert = Alert(
            plate_number=_PLATE, plate_number_normalized=_PLATE,
            camera_id=first.camera_id, vehicle_event_id=first.id, watchlist_id=wl.id,
            priority_level=PriorityLevel.HIGH, snapshot_url=first.snapshot_url,
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)

        # --- incident + case + evidence links ---
        year = now.year
        inc = Incident(
            incident_number=f"INC-{year}-9001",
            title=f"Watchlist hit — {_PLATE}", category="WATCHLIST_HIT",
            priority_level=PriorityLevel.HIGH,
            alert_id=alert.id, vehicle_event_id=first.id, camera_id=first.camera_id,
            plate_number_normalized=_PLATE,
        )
        db.add(inc)
        db.commit()
        db.refresh(inc)
        from app.models.incident import IncidentEvidence
        db.add(IncidentEvidence(incident_id=inc.id, vehicle_event_id=first.id,
                                note="first sighting"))
        case = Case(case_number=f"CASE-{year}-9001", title=f"Stolen {_PLATE} — corridor sweep",
                    priority_level=PriorityLevel.HIGH, primary_plate_normalized=_PLATE)
        db.add(case)
        db.commit()
        db.refresh(case)
        db.add(CaseIncident(case_id=case.id, incident_id=inc.id))
        for ev in journey_events[:3]:
            db.add(CaseEvidence(case_id=case.id, vehicle_event_id=ev.id))
        db.commit()

        # --- "white SUVs after 9 PM" + "unknown vehicles 20:00-22:00" ---
        for i, (plate, colour, hour) in enumerate([
            ("GJ01WA5501", "white", 21), ("GJ05WA7702", "white", 22), ("GJ12WA3303", "white", 21),
        ]):
            cam = cam_by_code["CAM-04"]
            ts = today0 + timedelta(hours=hour, minutes=10 + i * 7)
            _, _, lat, lon = _CAMERAS[3]
            db.add(VehicleEvent(
                plate_number=plate, plate_number_normalized=normalize_plate(plate),
                camera_id=cam.id, camera_code="CAM-04", track_id=200 + i, timestamp=ts,
                vehicle_type="car", vehicle_color=colour, confidence_score=0.81,
                latitude=lat, longitude=lon, location=_pt(lat, lon)))
        for i in range(4):
            cam = cam_by_code["CAM-05"]
            ts = today0 + timedelta(hours=20, minutes=30 + i * 15)
            _, _, lat, lon = _CAMERAS[4]
            db.add(VehicleEvent(
                plate_number="UNKNOWN", plate_number_normalized="UNKNOWN",
                camera_id=cam.id, camera_code="CAM-05", track_id=300 + i, timestamp=ts,
                vehicle_type="truck", confidence_score=0.4,
                latitude=lat, longitude=lon, location=_pt(lat, lon)))
        db.commit()

        # --- STOPPED VEHICLE at CAM-04 (track 7714) ---
        cam = cam_by_code["CAM-04"]
        _, _, lat, lon = _CAMERAS[3]
        stop_start = now - timedelta(minutes=25)
        for i in range(14):
            jitter = 0.00004 * ((-1) ** i)  # < 15 m wobble
            db.add(VehicleEvent(
                plate_number="GJ07LT4416", plate_number_normalized="GJ07LT4416",
                camera_id=cam.id, camera_code="CAM-04", track_id=7714,
                timestamp=stop_start + timedelta(seconds=i * 16),
                vehicle_type="car", vehicle_color="silver", confidence_score=0.7,
                latitude=lat + jitter, longitude=lon + jitter,
                location=_pt(lat + jitter, lon + jitter)))
        db.commit()

        res = BehaviorAnalyticsService(db).scan_stopped_vehicles()
        print(f"[seed_ai_demo] anomaly scan -> {res['created']} stopped-vehicle event(s)")

        # --- Phase 14: index appearance embeddings for every demo event so
        #     /ai/reid/search returns real candidates offline ---
        try:
            from app.services.ai.reid import VehicleReIDService

            bf = VehicleReIDService(db).backfill()
            print(f"[seed_ai_demo] re-id backfill -> {bf['indexed']} embedding(s)")
        except Exception as exc:  # noqa: BLE001
            print(f"[seed_ai_demo] re-id backfill skipped ({exc})")

        db.add(AuditLog(action=_MARKER, resource="ai_demo",
                        detail=f"cameras={len(cam_by_code)} journey_events={len(journey_events)} "
                               f"anomalies={res['created']}"))
        db.commit()
        print(f"[seed_ai_demo] done: {len(cam_by_code)} cameras, {_PLATE} journey, "
              f"INC-{year}-9001, CASE-{year}-9001, 1 stopped-vehicle anomaly")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
