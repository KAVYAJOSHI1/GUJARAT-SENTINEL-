"""
Alerts API — list, acknowledge, assign, escalate, resolve.

Phase 11 (FEATURE 6) adds the escalation workflow ON TOP of the existing
alert row. The watchlist engine is untouched: it still only ever creates
NEW alerts; every status beyond NEW is set here by an officer action and
audited. Alert notes live on the incident (promote the alert first) --
this endpoint set deliberately does not add a second notes store.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from geoalchemy2.functions import ST_X, ST_Y
from sqlalchemy import select
from sqlmodel import Session

from app.api.deps import get_current_user
from app.api.v1._enrich import resolve_usernames
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.alert import Alert
from app.models.base import AlertStatus, NotificationSeverity, PriorityLevel, UserRole
from app.models.camera import Camera
from app.models.incident import Incident
from app.models.user import User
from app.schemas.alert import (
    AlertAssign,
    AlertAcknowledge,
    AlertEscalate,
    AlertRead,
    AlertResolve,
)
from app.schemas.auth import CurrentUser
from app.core.rbac import require_roles
from app.services.audit import client_ip, record_audit
from app.services.notifications import push_notification

router = APIRouter()

_MANAGE = require_roles(UserRole.ADMIN, UserRole.OFFICER)


def _to_alert_read(a: Alert, *, cam=None, usernames=None, incident=None) -> AlertRead:
    cam = cam or {}
    usernames = usernames or {}
    return AlertRead(
        id=a.id,
        plate_number=a.plate_number,
        plate_number_normalized=a.plate_number_normalized,
        camera_id=a.camera_id,
        camera_code=cam.get("code"),
        camera_name=cam.get("name"),
        location_desc=cam.get("location_desc"),
        latitude=cam.get("lat"),
        longitude=cam.get("lon"),
        vehicle_event_id=a.vehicle_event_id,
        watchlist_id=a.watchlist_id,
        priority_level=a.priority_level,
        status=a.status,
        snapshot_url=a.snapshot_url,
        created_at=a.created_at,
        assigned_to_user_id=a.assigned_to_user_id,
        assigned_to_username=usernames.get(a.assigned_to_user_id or ""),
        acknowledged_by_user_id=a.acknowledged_by_user_id,
        acknowledged_by_username=usernames.get(a.acknowledged_by_user_id or ""),
        escalated_by_user_id=a.escalated_by_user_id,
        escalated_by_username=usernames.get(a.escalated_by_user_id or ""),
        escalated_at=a.escalated_at,
        escalation_reason=a.escalation_reason,
        resolved_by_user_id=a.resolved_by_user_id,
        resolved_by_username=usernames.get(a.resolved_by_user_id or ""),
        resolved_at=a.resolved_at,
        incident_id=incident[0] if incident else None,
        incident_number=incident[1] if incident else None,
    )


def _camera_map(db: Session, camera_ids):
    ids = {c for c in camera_ids if c}
    if not ids:
        return {}
    rows = db.execute(
        select(Camera.id, Camera.code, Camera.name, Camera.location_desc,
               ST_Y(Camera.location), ST_X(Camera.location)).where(Camera.id.in_(ids))
    ).all()
    return {r[0]: {"code": r[1], "name": r[2], "location_desc": r[3], "lat": r[4], "lon": r[5]}
            for r in rows}


def _incident_map(db: Session, alert_ids):
    ids = [a for a in alert_ids if a]
    if not ids:
        return {}
    rows = db.execute(
        select(Incident.alert_id, Incident.id, Incident.incident_number)
        .where(Incident.alert_id.in_(ids))
    ).all()
    return {r[0]: (r[1], r[2]) for r in rows}


@router.get("", response_model=list[AlertRead])
def list_alerts(
    status_filter: str | None = Query(default=None, alias="status"),
    assigned_to: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    stmt = select(Alert).order_by(Alert.created_at.desc()).limit(limit)
    if status_filter:
        stmt = stmt.where(Alert.status == status_filter)
    if assigned_to:
        stmt = stmt.where(Alert.assigned_to_user_id == assigned_to)
    alerts = db.execute(stmt).scalars().all()
    cams = _camera_map(db, [a.camera_id for a in alerts])
    incs = _incident_map(db, [a.id for a in alerts])
    usernames = resolve_usernames(
        db,
        [a.assigned_to_user_id for a in alerts] + [a.acknowledged_by_user_id for a in alerts]
        + [a.escalated_by_user_id for a in alerts] + [a.resolved_by_user_id for a in alerts],
    )
    return [
        _to_alert_read(a, cam=cams.get(a.camera_id), usernames=usernames, incident=incs.get(a.id))
        for a in alerts
    ]


def _one(db: Session, alert_id: str) -> Alert:
    a = db.get(Alert, alert_id)
    if a is None:
        raise NotFoundError("Alert", alert_id)
    return a


def _reload(db: Session, a: Alert) -> AlertRead:
    cams = _camera_map(db, [a.camera_id])
    incs = _incident_map(db, [a.id])
    usernames = resolve_usernames(
        db, [a.assigned_to_user_id, a.acknowledged_by_user_id, a.escalated_by_user_id,
             a.resolved_by_user_id]
    )
    return _to_alert_read(a, cam=cams.get(a.camera_id), usernames=usernames, incident=incs.get(a.id))


@router.patch("/{alert_id}", response_model=AlertRead)
def acknowledge_alert(
    alert_id: str,
    payload: AlertAcknowledge,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """Backward-compatible acknowledge/resolve (existing contract). Stamps
    acknowledged_by / resolved_by as appropriate."""
    alert = _one(db, alert_id)
    now = datetime.utcnow()
    alert.status = payload.status
    if payload.status == AlertStatus.ACKNOWLEDGED:
        alert.acknowledged_by_user_id = user.id
    if payload.status == AlertStatus.RESOLVED and alert.resolved_at is None:
        alert.resolved_by_user_id = user.id
        alert.resolved_at = now
    db.add(alert)
    db.commit()
    db.refresh(alert)
    record_audit(
        db, action="ALERT_ACKNOWLEDGED", user_id=user.id, resource="alert", resource_id=alert.id,
        ip_address=client_ip(request),
        detail={"status": alert.status.value, "plate": alert.plate_number_normalized},
    )
    return _reload(db, alert)


@router.post("/{alert_id}/assign", response_model=AlertRead)
def assign_alert(
    alert_id: str,
    payload: AlertAssign,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(_MANAGE),
):
    alert = _one(db, alert_id)
    assignee = None
    if payload.user_id:
        assignee = db.get(User, payload.user_id)
        if assignee is None or not assignee.is_active:
            raise NotFoundError("User", payload.user_id)
    alert.assigned_to_user_id = assignee.id if assignee else None
    db.add(alert)
    db.commit()
    db.refresh(alert)
    record_audit(
        db, action="ALERT_ASSIGNED", user_id=user.id, resource="alert", resource_id=alert.id,
        ip_address=client_ip(request),
        detail={"assigned_to": assignee.username if assignee else None},
    )
    if assignee and assignee.id != user.id:
        push_notification(
            db, type="ALERT_ASSIGNED", title=f"Alert assigned to you — {alert.plate_number_normalized}",
            body=f"{alert.priority_level.value} priority", severity=NotificationSeverity.WARNING,
            resource="alert", resource_id=alert.id, target_user_id=assignee.id,
        )
    return _reload(db, alert)


@router.post("/{alert_id}/escalate", response_model=AlertRead)
def escalate_alert(
    alert_id: str,
    payload: AlertEscalate,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(_MANAGE),
):
    alert = _one(db, alert_id)
    now = datetime.utcnow()
    alert.status = AlertStatus.ESCALATED
    alert.escalated_by_user_id = user.id
    alert.escalated_at = now
    alert.escalation_reason = payload.reason.strip()
    db.add(alert)
    db.commit()
    db.refresh(alert)
    record_audit(
        db, action="ALERT_ESCALATED", user_id=user.id, resource="alert", resource_id=alert.id,
        ip_address=client_ip(request),
        detail={"plate": alert.plate_number_normalized, "reason": alert.escalation_reason[:200]},
    )
    push_notification(
        db, type="ALERT_ESCALATED",
        title=f"Alert escalated — {alert.plate_number_normalized}",
        body=payload.reason.strip()[:280],
        severity=NotificationSeverity.CRITICAL,
        resource="alert", resource_id=alert.id,
    )
    return _reload(db, alert)


@router.post("/{alert_id}/resolve", response_model=AlertRead)
def resolve_alert(
    alert_id: str,
    payload: AlertResolve,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(_MANAGE),
):
    alert = _one(db, alert_id)
    now = datetime.utcnow()
    alert.status = AlertStatus.RESOLVED
    alert.resolved_by_user_id = user.id
    alert.resolved_at = now
    db.add(alert)
    db.commit()
    db.refresh(alert)
    record_audit(
        db, action="ALERT_RESOLVED", user_id=user.id, resource="alert", resource_id=alert.id,
        ip_address=client_ip(request),
        detail={"plate": alert.plate_number_normalized,
                "note": (payload.note or "").strip()[:200] or None},
    )
    return _reload(db, alert)
