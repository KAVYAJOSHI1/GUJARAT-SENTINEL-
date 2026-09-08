"""
Command Center summary (Phase 16A).

ONE bounded, read-only aggregation for the /command-center landing page,
composed entirely from EXISTING services + indexed queries. No new
business logic, no expensive work, no video processing. The dashboard
makes a single call instead of a dozen.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from geoalchemy2.functions import ST_X, ST_Y
from sqlalchemy import func, select
from sqlmodel import Session

from app.models.alert import Alert
from app.models.anomaly_event import AnomalyEvent
from app.models.base import (
    AlertStatus,
    AnomalyStatus,
    CaseStatus,
    IncidentStatus,
    PriorityLevel,
)
from app.models.camera import Camera
from app.models.case import Case
from app.models.incident import Incident
from app.models.vehicle_event import VehicleEvent
from app.services.system_metrics import system_metrics_summary

_SEV_ORDER = {"ESCALATED": 0, "CRITICAL": 1, "HIGH": 2, "MEDIUM": 3, "LOW": 4}
_HEALTH_STALE = timedelta(seconds=20)


def _effective_online(cam: Camera, now: datetime) -> bool:
    if cam.status.value != "ONLINE":
        return False
    if cam.health_updated_at is None:
        return True
    return (now - cam.health_updated_at) <= _HEALTH_STALE


def command_center_summary(db: Session) -> dict:
    now = datetime.utcnow()
    day_start = now - timedelta(hours=24)

    # ---- alerts ------------------------------------------------------- #
    alert_rows = db.execute(
        select(Alert, Camera.code, Camera.name)
        .join(Camera, Camera.id == Alert.camera_id, isouter=True)
        .where(Alert.status.in_([AlertStatus.NEW, AlertStatus.ACKNOWLEDGED, AlertStatus.ESCALATED]))
        .order_by(Alert.created_at.desc())
        .limit(200)
    ).all()

    def _sev(a: Alert) -> str:
        if a.status == AlertStatus.ESCALATED:
            return "ESCALATED"
        return a.priority_level.value

    active_alerts = []
    for a, ccode, cname in alert_rows:
        active_alerts.append({
            "id": a.id,
            "plate": a.plate_number_normalized,
            "camera_code": ccode,
            "camera_name": cname,
            "severity": _sev(a),
            "priority": a.priority_level.value,
            "source": a.source.value,
            "status": a.status.value,
            "created_at": a.created_at,
            "age_seconds": int((now - a.created_at).total_seconds()),
            "assigned_to_user_id": getattr(a, "assigned_to_user_id", None),
            "vehicle_event_id": a.vehicle_event_id,
            "href": f"/alerts?focus={a.id}",
            "investigate_href": f"/workspace?plate={a.plate_number_normalized}&alert={a.id}",
        })
    active_alerts.sort(key=lambda x: (_SEV_ORDER.get(x["severity"], 5), x["age_seconds"]))

    kpi_active = sum(1 for a in alert_rows if a[0].status == AlertStatus.NEW)
    kpi_escalated = sum(1 for a in alert_rows if a[0].status == AlertStatus.ESCALATED)

    # ---- incidents / cases ----------------------------------------------- #
    open_inc_rows = db.execute(
        select(Incident)
        .where(Incident.status.in_([IncidentStatus.NEW, IncidentStatus.ACKNOWLEDGED,
                                    IncidentStatus.INVESTIGATING]))
        .order_by(Incident.created_at.desc()).limit(50)
    ).scalars().all()
    open_case_rows = db.execute(
        select(Case)
        .where(Case.status.in_([CaseStatus.OPEN, CaseStatus.INVESTIGATING, CaseStatus.ON_HOLD]))
        .order_by(Case.created_at.desc()).limit(50)
    ).scalars().all()

    active_investigations = []
    for i in open_inc_rows[:15]:
        active_investigations.append({
            "kind": "INCIDENT", "id": i.id, "label": i.incident_number, "title": i.title,
            "status": i.status.value, "priority": i.priority_level.value,
            "plate": i.plate_number_normalized, "created_at": i.created_at,
            "href": f"/incidents/{i.id}",
        })
    for c in open_case_rows[:15]:
        active_investigations.append({
            "kind": "CASE", "id": c.id, "label": c.case_number, "title": c.title,
            "status": c.status.value, "priority": c.priority_level.value,
            "plate": c.primary_plate_normalized, "created_at": c.created_at,
            "href": f"/cases/{c.id}",
        })
    active_investigations.sort(key=lambda x: x["created_at"], reverse=True)

    # ---- cameras ------------------------------------------------------- #
    cam_rows = db.execute(
        select(Camera, ST_Y(Camera.location), ST_X(Camera.location))
    ).all()
    last_det = dict(db.execute(
        select(VehicleEvent.camera_id, func.max(VehicleEvent.timestamp))
        .group_by(VehicleEvent.camera_id)
    ).all())
    # video quality (bounded: one grouped aggregate over 24h)
    vq = {
        cid: (int(tot or 0), int(ok or 0))
        for cid, tot, ok in db.execute(
            select(
                VehicleEvent.camera_id,
                func.count(VehicleEvent.id),
                func.count(VehicleEvent.id).filter(VehicleEvent.anpr_status == "OK"),
            ).where(VehicleEvent.timestamp >= day_start).group_by(VehicleEvent.camera_id)
        ).all()
    }

    cameras = []
    n_online = n_degraded = n_offline = n_poor = 0
    for cam, lat, lon in cam_rows:
        online = _effective_online(cam, now)
        stale = (cam.health_updated_at is not None
                 and (now - cam.health_updated_at) > _HEALTH_STALE)
        low_fps = cam.stream_fps is not None and cam.stream_fps < 8.0
        degraded = online and (low_fps or stale)
        tot, ok = vq.get(cam.id, (0, 0))
        poor_video = tot >= 5 and (ok / tot) < 0.55
        state = "OFFLINE" if not online else ("DEGRADED" if degraded else "ONLINE")
        if state == "ONLINE":
            n_online += 1
        elif state == "DEGRADED":
            n_degraded += 1
        else:
            n_offline += 1
        if poor_video:
            n_poor += 1
        cameras.append({
            "id": cam.id, "code": cam.code, "name": cam.name,
            "location_desc": cam.location_desc, "latitude": lat, "longitude": lon,
            "state": state, "poor_video": poor_video,
            "stream_fps": cam.stream_fps,
            "last_heartbeat": cam.health_updated_at,
            "last_detection_at": last_det.get(cam.id),
            "reconnect_count": cam.reconnect_count,
            "feed_source": "DEMO" if getattr(cam, "is_demo", False) else (
                "MOCK" if (cam.code or "").lower().startswith(("mock", "mock_cam", "mockcam")) else "REAL"),
            "href": f"/cameras?focus={cam.id}",
        })

    problem_cameras = [c for c in cameras if c["state"] != "ONLINE" or c["poor_video"]]
    problem_cameras.sort(key=lambda c: (c["state"] == "ONLINE", c["state"]))

    # ---- recent vehicles + today counts ------------------------------- #
    recent_vehicles = [
        {"plate": p, "sightings": int(n), "last_seen": last,
         "href": f"/workspace?plate={p}"}
        for p, n, last in db.execute(
            select(VehicleEvent.plate_number_normalized, func.count(VehicleEvent.id),
                   func.max(VehicleEvent.timestamp))
            .where(VehicleEvent.plate_number_normalized != "UNKNOWN")
            .group_by(VehicleEvent.plate_number_normalized)
            .order_by(func.max(VehicleEvent.timestamp).desc())
            .limit(8)
        ).all()
    ]
    vehicles_today = int(db.execute(
        select(func.count(VehicleEvent.id)).where(VehicleEvent.timestamp >= day_start)
    ).scalar() or 0)
    anomalies_today = int(db.execute(
        select(func.count(AnomalyEvent.id)).where(AnomalyEvent.created_at >= day_start)
    ).scalar() or 0)
    anomalies_new = int(db.execute(
        select(func.count(AnomalyEvent.id)).where(AnomalyEvent.status == AnomalyStatus.NEW)
    ).scalar() or 0)
    recent_anomalies = [
        {"id": a.id, "kind": a.kind.value, "camera_code": a.camera_code,
         "plate": a.plate_number_normalized, "confidence_level": a.confidence_level.value,
         "created_at": a.created_at, "status": a.status.value, "href": "/anomalies"}
        for a in db.execute(
            select(AnomalyEvent).order_by(AnomalyEvent.created_at.desc()).limit(6)
        ).scalars().all()
    ]

    metrics = system_metrics_summary(db, window_hours=24)

    return {
        "generated_at": datetime.now(timezone.utc),
        "kpis": {
            "active_alerts": kpi_active,
            "escalated": kpi_escalated,
            "open_incidents": len(open_inc_rows),
            "open_cases": len(open_case_rows),
            "cameras_online": n_online,
            "cameras_degraded": n_degraded,
            "cameras_offline": n_offline,
            "cameras_poor_video": n_poor,
            "vehicles_today": vehicles_today,
            "anomalies_today": anomalies_today,
        },
        "active_alerts": active_alerts[:12],
        "active_alerts_total": len(active_alerts),
        "active_investigations": active_investigations[:12],
        "cameras": cameras,
        "problem_cameras": problem_cameras[:12],
        "recent_vehicles": recent_vehicles,
        "recent_anomalies": recent_anomalies,
        "anomalies_new": anomalies_new,
        "metrics": {
            "pipeline": metrics["pipeline"],
            "anpr": metrics["anpr"],
            "cameras": metrics["cameras"],
        },
        "note": "Single bounded aggregation over existing read-only services.",
    }
