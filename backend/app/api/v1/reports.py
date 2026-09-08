"""
Reports Center (FEATURE 9).

Nine operational reports, each a bounded PostgreSQL aggregate/extract over
the EXISTING tables -- no fabricated statistics, no new store. CSV export
(StreamingResponse, same mechanism as the case-report export). PDF is
deferred (documented) -- the frontend can still print the on-screen table.
"""
import csv
import io
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlmodel import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.alert import Alert
from app.models.camera import Camera
from app.models.camera_health_history import CameraHealthHistory
from app.models.case import Case
from app.models.incident import Incident
from app.models.vehicle_event import VehicleEvent
from app.schemas.auth import CurrentUser
from app.services.audit import client_ip, record_audit
from app.services.plate_utils import normalize_plate
from pydantic import BaseModel

router = APIRouter()

REPORTS = {
    "vehicle-detections": "Vehicle Detection Report",
    "watchlist-matches": "Watchlist Match Report",
    "alerts": "Alert Report",
    "incidents": "Incident Report",
    "cases": "Case Report",
    "camera-activity": "Camera Activity Report",
    "camera-health": "Camera Health Report",
    "vehicle-journey": "Vehicle Journey Report",
    "daily-summary": "Daily Operations Summary",
}


class ReportInfo(BaseModel):
    key: str
    name: str
    needs_plate: bool = False


@router.get("", response_model=list[ReportInfo])
def list_reports(_: CurrentUser = Depends(get_current_user)):
    return [
        ReportInfo(key=k, name=v, needs_plate=(k == "vehicle-journey"))
        for k, v in REPORTS.items()
    ]


def _csv(header, rows, filename):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    for r in rows:
        w.writerow(r)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _range(date_from, date_to):
    to = date_to or datetime.utcnow()
    frm = date_from or (to - timedelta(days=7))
    return frm, to


@router.get("/{report}.csv")
def export_report(
    report: str,
    request: Request,
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    camera_code: str | None = Query(default=None),
    department: str | None = Query(default=None, description="matches camera name / location_desc"),
    plate: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    if report not in REPORTS:
        from app.core.exceptions import NotFoundError
        raise NotFoundError("Report", report)

    frm, to = _range(date_from, date_to)
    dept_like = f"%{department.strip()}%" if department else None

    def _dept_camera_ids():
        if not dept_like:
            return None
        return [
            c for (c,) in db.execute(
                select(Camera.id).where(
                    Camera.name.ilike(dept_like) | Camera.location_desc.ilike(dept_like)
                )
            ).all()
        ]

    header, rows = [], []

    if report == "vehicle-detections":
        conds = [VehicleEvent.timestamp >= frm, VehicleEvent.timestamp <= to]
        if camera_code:
            conds.append(VehicleEvent.camera_code == camera_code)
        if plate:
            conds.append(VehicleEvent.plate_number_normalized == normalize_plate(plate))
        if dept_like:
            ids = _dept_camera_ids()
            conds.append(VehicleEvent.camera_id.in_(ids or ["-"]))
        header = ["timestamp", "plate", "vehicle_type", "camera_code", "confidence", "event_id"]
        for ev in db.execute(
            select(VehicleEvent).where(*conds).order_by(VehicleEvent.timestamp.asc()).limit(20000)
        ).scalars():
            rows.append([ev.timestamp.isoformat(), ev.plate_number_normalized,
                         ev.vehicle_type or "", ev.camera_code or "",
                         f"{ev.confidence_score:.3f}" if ev.confidence_score else "", ev.id])

    elif report in ("watchlist-matches", "alerts"):
        conds = [Alert.created_at >= frm, Alert.created_at <= to]
        if severity:
            conds.append(Alert.priority_level == severity.upper())
        if plate:
            conds.append(Alert.plate_number_normalized == normalize_plate(plate))
        alerts = db.execute(
            select(Alert).where(*conds).order_by(Alert.created_at.asc()).limit(20000)
        ).scalars().all()
        code_map = dict(db.execute(
            select(Camera.id, Camera.code).where(
                Camera.id.in_({a.camera_id for a in alerts})
            )
        ).all()) if alerts else {}
        if report == "watchlist-matches":
            header = ["created_at", "plate", "camera", "priority", "status"]
            rows = [[a.created_at.isoformat(), a.plate_number_normalized,
                     code_map.get(a.camera_id, ""), a.priority_level.value, a.status.value]
                    for a in alerts]
        else:
            header = ["created_at", "plate", "camera", "priority", "status",
                      "escalated_at", "escalation_reason", "resolved_at"]
            rows = [[a.created_at.isoformat(), a.plate_number_normalized,
                     code_map.get(a.camera_id, ""), a.priority_level.value, a.status.value,
                     a.escalated_at.isoformat() if a.escalated_at else "",
                     (a.escalation_reason or "").replace("\n", " "),
                     a.resolved_at.isoformat() if a.resolved_at else ""]
                    for a in alerts]

    elif report == "incidents":
        conds = [Incident.created_at >= frm, Incident.created_at <= to]
        if severity:
            conds.append(Incident.priority_level == severity.upper())
        header = ["incident_number", "title", "category", "priority", "status",
                  "plate", "created_at", "resolved_at"]
        for i in db.execute(
            select(Incident).where(*conds).order_by(Incident.created_at.asc()).limit(20000)
        ).scalars():
            rows.append([i.incident_number, i.title, i.category, i.priority_level.value,
                         i.status.value, i.plate_number_normalized or "",
                         i.created_at.isoformat(),
                         i.resolved_at.isoformat() if i.resolved_at else ""])

    elif report == "cases":
        conds = [Case.created_at >= frm, Case.created_at <= to]
        if severity:
            conds.append(Case.priority_level == severity.upper())
        header = ["case_number", "title", "priority", "status", "primary_plate", "created_at"]
        for c in db.execute(
            select(Case).where(*conds).order_by(Case.created_at.asc()).limit(20000)
        ).scalars():
            rows.append([c.case_number, c.title, c.priority_level.value, c.status.value,
                         c.primary_plate_normalized or "", c.created_at.isoformat()])

    elif report == "camera-activity":
        conds = [VehicleEvent.timestamp >= frm, VehicleEvent.timestamp <= to]
        if camera_code:
            conds.append(VehicleEvent.camera_code == camera_code)
        agg = db.execute(
            select(VehicleEvent.camera_code, func.count(VehicleEvent.id),
                   func.count(VehicleEvent.id).filter(
                       VehicleEvent.plate_number_normalized != "UNKNOWN"))
            .where(*conds).group_by(VehicleEvent.camera_code)
            .order_by(func.count(VehicleEvent.id).desc())
        ).all()
        names = dict(db.execute(select(Camera.code, Camera.name)).all())
        header = ["camera_code", "camera_name", "detections", "readable_plates"]
        rows = [[code or "", names.get(code, ""), int(total), int(readable)]
                for code, total, readable in agg]

    elif report == "camera-health":
        conds = [CameraHealthHistory.detected_at >= frm, CameraHealthHistory.detected_at <= to]
        hist = db.execute(
            select(CameraHealthHistory).where(*conds)
            .order_by(CameraHealthHistory.detected_at.asc()).limit(20000)
        ).scalars().all()
        code_map = dict(db.execute(
            select(Camera.id, Camera.code).where(
                Camera.id.in_({h.camera_id for h in hist})
            )
        ).all()) if hist else {}
        header = ["detected_at", "camera", "previous_status", "status", "source", "reconnect_count"]
        rows = [[h.detected_at.isoformat(), code_map.get(h.camera_id, h.camera_id),
                 h.previous_status.value if h.previous_status else "",
                 h.status.value, h.source, h.reconnect_count if h.reconnect_count is not None else ""]
                for h in hist]

    elif report == "vehicle-journey":
        if not plate:
            from app.core.exceptions import SentinelException
            raise SentinelException(code="PLATE_REQUIRED",
                                    message="vehicle-journey report needs a ?plate=", status_code=400)
        norm = normalize_plate(plate)
        rows_ = db.execute(
            select(VehicleEvent, Camera.code, Camera.name)
            .join(Camera, Camera.id == VehicleEvent.camera_id, isouter=True)
            .where(VehicleEvent.plate_number_normalized == norm)
            .where(VehicleEvent.timestamp >= frm, VehicleEvent.timestamp <= to)
            .order_by(VehicleEvent.timestamp.asc()).limit(20000)
        ).all()
        header = ["seq", "plate", "timestamp", "camera_code", "camera_name", "latitude",
                  "longitude", "vehicle_type", "confidence", "event_id"]
        for n, (ev, code, name) in enumerate(rows_, start=1):
            rows.append([n, ev.plate_number_normalized, ev.timestamp.isoformat(), code or "",
                         name or "",
                         ev.latitude if ev.latitude is not None else "",
                         ev.longitude if ev.longitude is not None else "",
                         ev.vehicle_type or "",
                         f"{ev.confidence_score:.3f}" if ev.confidence_score else "", ev.id])

    elif report == "daily-summary":
        _day = func.date_trunc("day", VehicleEvent.timestamp)
        det = dict(db.execute(
            select(_day, func.count(VehicleEvent.id))
            .where(VehicleEvent.timestamp >= frm, VehicleEvent.timestamp <= to)
            .group_by(_day)
        ).all())
        _aday = func.date_trunc("day", Alert.created_at)
        alr = dict(db.execute(
            select(_aday, func.count(Alert.id))
            .where(Alert.created_at >= frm, Alert.created_at <= to).group_by(_aday)
        ).all())
        _iday = func.date_trunc("day", Incident.created_at)
        inc = dict(db.execute(
            select(_iday, func.count(Incident.id))
            .where(Incident.created_at >= frm, Incident.created_at <= to).group_by(_iday)
        ).all())
        _cday = func.date_trunc("day", Case.created_at)
        cas = dict(db.execute(
            select(_cday, func.count(Case.id))
            .where(Case.created_at >= frm, Case.created_at <= to).group_by(_cday)
        ).all())
        days = sorted(set(det) | set(alr) | set(inc) | set(cas))
        header = ["date", "detections", "watchlist_matches", "incidents_opened", "cases_opened"]
        rows = [[d.date().isoformat(), int(det.get(d, 0)), int(alr.get(d, 0)),
                 int(inc.get(d, 0)), int(cas.get(d, 0))] for d in days]

    record_audit(
        db, action="REPORT_EXPORT", user_id=user.id, resource="report", resource_id=report,
        ip_address=client_ip(request),
        detail={"report": report, "rows": len(rows), "from": frm.isoformat(), "to": to.isoformat()},
    )
    return _csv(header, rows, f"{report}_{frm:%Y%m%d}_{to:%Y%m%d}.csv")
