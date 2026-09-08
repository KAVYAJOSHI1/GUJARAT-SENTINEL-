"""
Incident management API (phase brief FEATURE 1).

Alerts -> manageable incidents. An incident links back to its source rows
(alert / vehicle_event / camera) by foreign key and never copies their
mutable state; the detail view re-resolves live data and derives the
vehicle's camera-sighting count on read.

RBAC:
  * view  -> any authenticated user (ADMIN / OFFICER / OPERATOR)
  * mutate -> ADMIN or OFFICER
Every privileged mutation is audited.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import func, select
from sqlmodel import Session

from app.api.v1._enrich import next_sequence_number, resolve_cameras, resolve_usernames
from app.api.deps import get_current_user
from app.core.exceptions import NotFoundError, SentinelException
from app.core.rbac import require_roles
from app.database import get_db
from app.models.alert import Alert
from app.models.base import IncidentStatus, PriorityLevel, UserRole
from app.models.case import CaseIncident, Case
from app.models.incident import Incident, IncidentEvidence, IncidentNote
from app.models.user import User
from app.models.vehicle_event import VehicleEvent
from app.schemas.auth import CurrentUser
from app.schemas.incident import (
    IncidentAssign,
    IncidentCreate,
    IncidentDetail,
    IncidentEvidenceCreate,
    IncidentEvidenceRead,
    IncidentNoteCreate,
    IncidentNoteRead,
    IncidentPage,
    IncidentRead,
    IncidentStatusUpdate,
    IncidentUpdate,
)
from app.services.audit import client_ip, record_audit
from app.services.notifications import push_notification
from app.models.base import NotificationSeverity
from app.services.plate_utils import normalize_plate

router = APIRouter()

_MANAGE = require_roles(UserRole.ADMIN, UserRole.OFFICER)


# --------------------------------------------------------------------------- #
#  serialisation                                                              #
# --------------------------------------------------------------------------- #
def _incident_read(inc: Incident, *, usernames: dict, cameras: dict,
                   note_count: int = 0, evidence_count: int = 0) -> IncidentRead:
    cam = cameras.get(inc.camera_id or "", {})
    return IncidentRead(
        id=inc.id,
        incident_number=inc.incident_number,
        title=inc.title,
        description=inc.description,
        category=inc.category,
        priority_level=inc.priority_level,
        status=inc.status,
        alert_id=inc.alert_id,
        vehicle_event_id=inc.vehicle_event_id,
        camera_id=inc.camera_id,
        camera_code=cam.get("code"),
        camera_name=cam.get("name"),
        location_desc=cam.get("location_desc"),
        latitude=cam.get("latitude"),
        longitude=cam.get("longitude"),
        plate_number_normalized=inc.plate_number_normalized,
        created_by_user_id=inc.created_by_user_id,
        created_by_username=usernames.get(inc.created_by_user_id or ""),
        assigned_to_user_id=inc.assigned_to_user_id,
        assigned_to_username=usernames.get(inc.assigned_to_user_id or ""),
        acknowledged_by_user_id=inc.acknowledged_by_user_id,
        acknowledged_by_username=usernames.get(inc.acknowledged_by_user_id or ""),
        acknowledged_at=inc.acknowledged_at,
        resolved_by_user_id=inc.resolved_by_user_id,
        resolved_by_username=usernames.get(inc.resolved_by_user_id or ""),
        resolved_at=inc.resolved_at,
        created_at=inc.created_at,
        updated_at=inc.updated_at,
        note_count=note_count,
        evidence_count=evidence_count,
    )


def _incident_detail(db: Session, inc: Incident) -> IncidentDetail:
    notes = db.execute(
        select(IncidentNote).where(IncidentNote.incident_id == inc.id)
        .order_by(IncidentNote.created_at.asc())
    ).scalars().all()
    ev_links = db.execute(
        select(IncidentEvidence).where(IncidentEvidence.incident_id == inc.id)
        .order_by(IncidentEvidence.created_at.asc())
    ).scalars().all()

    event_ids = [e.vehicle_event_id for e in ev_links]
    events = {}
    if event_ids:
        for ev in db.execute(
            select(VehicleEvent).where(VehicleEvent.id.in_(event_ids))
        ).scalars().all():
            events[ev.id] = ev

    user_ids = (
        [inc.created_by_user_id, inc.assigned_to_user_id, inc.acknowledged_by_user_id,
         inc.resolved_by_user_id]
        + [n.author_user_id for n in notes]
        + [e.added_by_user_id for e in ev_links]
    )
    usernames = resolve_usernames(db, user_ids)
    camera_ids = [inc.camera_id] + [ev.camera_id for ev in events.values()]
    cameras = resolve_cameras(db, camera_ids)

    case_numbers = db.execute(
        select(Case.case_number)
        .join(CaseIncident, CaseIncident.case_id == Case.id)
        .where(CaseIncident.incident_id == inc.id)
        .order_by(Case.created_at.asc())
    ).scalars().all()

    related_sightings = 0
    if inc.plate_number_normalized:
        related_sightings = db.execute(
            select(func.count(VehicleEvent.id)).where(
                VehicleEvent.plate_number_normalized == inc.plate_number_normalized
            )
        ).scalar() or 0

    base = _incident_read(
        inc, usernames=usernames, cameras=cameras,
        note_count=len(notes), evidence_count=len(ev_links),
    )
    detail = IncidentDetail(**base.model_dump())
    detail.notes = [
        IncidentNoteRead(
            id=n.id, incident_id=n.incident_id, author_user_id=n.author_user_id,
            author_username=usernames.get(n.author_user_id or ""), body=n.body,
            created_at=n.created_at,
        )
        for n in notes
    ]
    detail.evidence = [_evidence_read(e, events.get(e.vehicle_event_id), cameras, usernames)
                       for e in ev_links]
    detail.case_numbers = list(case_numbers)
    detail.related_sighting_count = int(related_sightings)
    return detail


def _evidence_read(link: IncidentEvidence, ev, cameras: dict, usernames: dict) -> IncidentEvidenceRead:
    cam = cameras.get((ev.camera_id if ev else "") or "", {})
    return IncidentEvidenceRead(
        id=link.id,
        incident_id=link.incident_id,
        vehicle_event_id=link.vehicle_event_id,
        note=link.note,
        added_by_user_id=link.added_by_user_id,
        added_by_username=usernames.get(link.added_by_user_id or ""),
        created_at=link.created_at,
        plate_number=ev.plate_number if ev else None,
        camera_id=ev.camera_id if ev else None,
        camera_code=cam.get("code"),
        camera_name=cam.get("name"),
        event_timestamp=ev.timestamp if ev else None,
        has_snapshot=bool(ev and ev.snapshot_url),
    )


def _reload_detail(db: Session, incident_id: str) -> IncidentDetail:
    inc = db.get(Incident, incident_id)
    if inc is None:
        raise NotFoundError("Incident", incident_id)
    return _incident_detail(db, inc)


# --------------------------------------------------------------------------- #
#  list / create                                                              #
# --------------------------------------------------------------------------- #
@router.get("", response_model=IncidentPage)
def list_incidents(
    status_filter: str | None = Query(default=None, alias="status"),
    priority: PriorityLevel | None = Query(default=None),
    assigned_to: str | None = Query(default=None),
    plate: str | None = Query(default=None),
    camera_id: str | None = Query(default=None),
    q: str | None = Query(default=None, description="substring match on title / incident_number"),
    active_only: bool = Query(default=False, description="exclude RESOLVED and CLOSED"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
):
    conds = []
    if status_filter:
        conds.append(Incident.status == status_filter)
    if active_only:
        conds.append(Incident.status.notin_([IncidentStatus.RESOLVED, IncidentStatus.CLOSED]))
    if priority:
        conds.append(Incident.priority_level == priority)
    if assigned_to:
        conds.append(Incident.assigned_to_user_id == assigned_to)
    if plate:
        conds.append(Incident.plate_number_normalized == normalize_plate(plate))
    if camera_id:
        conds.append(Incident.camera_id == camera_id)
    if q:
        like = f"%{q.strip()}%"
        conds.append(Incident.title.ilike(like) | Incident.incident_number.ilike(like))

    total = db.execute(
        select(func.count(Incident.id)).where(*conds)
    ).scalar() or 0
    rows = db.execute(
        select(Incident).where(*conds)
        .order_by(Incident.created_at.desc())
        .limit(limit).offset(offset)
    ).scalars().all()

    ids = [r.id for r in rows]
    note_counts: dict[str, int] = {}
    ev_counts: dict[str, int] = {}
    if ids:
        for iid, c in db.execute(
            select(IncidentNote.incident_id, func.count(IncidentNote.id))
            .where(IncidentNote.incident_id.in_(ids)).group_by(IncidentNote.incident_id)
        ).all():
            note_counts[iid] = c
        for iid, c in db.execute(
            select(IncidentEvidence.incident_id, func.count(IncidentEvidence.id))
            .where(IncidentEvidence.incident_id.in_(ids)).group_by(IncidentEvidence.incident_id)
        ).all():
            ev_counts[iid] = c

    usernames = resolve_usernames(
        db, [r.created_by_user_id for r in rows] + [r.assigned_to_user_id for r in rows]
        + [r.acknowledged_by_user_id for r in rows] + [r.resolved_by_user_id for r in rows]
    )
    cameras = resolve_cameras(db, [r.camera_id for r in rows])

    items = [
        _incident_read(r, usernames=usernames, cameras=cameras,
                       note_count=note_counts.get(r.id, 0),
                       evidence_count=ev_counts.get(r.id, 0))
        for r in rows
    ]
    return IncidentPage(items=items, total=int(total), limit=limit, offset=offset)


@router.post("", response_model=IncidentDetail, status_code=status.HTTP_201_CREATED)
def create_incident(
    payload: IncidentCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(_MANAGE),
):
    alert = None
    if payload.alert_id:
        alert = db.get(Alert, payload.alert_id)
        if alert is None:
            raise NotFoundError("Alert", payload.alert_id)
        # one incident per alert -- promoting the same alert twice returns 409
        existing = db.execute(
            select(Incident).where(Incident.alert_id == alert.id)
        ).scalar_one_or_none()
        if existing is not None:
            raise SentinelException(
                code="INCIDENT_ALREADY_EXISTS",
                message=f"Alert '{alert.id}' already has incident {existing.incident_number}.",
                status_code=status.HTTP_409_CONFLICT,
                details={"incident_id": existing.id, "incident_number": existing.incident_number},
            )

    camera_id = payload.camera_id or (alert.camera_id if alert else None)
    vehicle_event_id = payload.vehicle_event_id or (alert.vehicle_event_id if alert else None)
    plate_norm = None
    if payload.plate_number:
        plate_norm = normalize_plate(payload.plate_number)
    elif alert is not None:
        plate_norm = alert.plate_number_normalized

    priority = payload.priority_level or (alert.priority_level if alert else PriorityLevel.MEDIUM)
    category = payload.category or ("WATCHLIST_HIT" if alert else "OTHER")
    title = payload.title or (
        f"Watchlist hit — {alert.plate_number_normalized}" if alert else "Incident"
    )

    inc = Incident(
        incident_number=next_sequence_number(db, "INC", Incident, Incident.incident_number),
        title=title,
        description=payload.description,
        category=category,
        priority_level=priority,
        status=IncidentStatus.NEW,
        alert_id=alert.id if alert else None,
        vehicle_event_id=vehicle_event_id,
        camera_id=camera_id,
        plate_number_normalized=plate_norm,
        created_by_user_id=user.id,
    )
    db.add(inc)
    db.commit()
    db.refresh(inc)

    record_audit(
        db, action="INCIDENT_CREATE", user_id=user.id, resource="incident",
        resource_id=inc.id, ip_address=client_ip(request),
        detail={"incident_number": inc.incident_number, "alert_id": inc.alert_id,
                "plate": plate_norm, "priority": priority.value},
    )
    push_notification(
        db, type="INCIDENT_CREATED",
        title=f"Incident {inc.incident_number} opened",
        body=inc.title,
        severity=(NotificationSeverity.CRITICAL if priority == PriorityLevel.CRITICAL
                  else NotificationSeverity.WARNING),
        resource="incident", resource_id=inc.id,
    )
    return _incident_detail(db, inc)


# --------------------------------------------------------------------------- #
#  detail / update / assign / status                                          #
# --------------------------------------------------------------------------- #
@router.get("/{incident_id}", response_model=IncidentDetail)
def get_incident(
    incident_id: str,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
):
    return _reload_detail(db, incident_id)


@router.patch("/{incident_id}", response_model=IncidentDetail)
def update_incident(
    incident_id: str,
    payload: IncidentUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(_MANAGE),
):
    inc = db.get(Incident, incident_id)
    if inc is None:
        raise NotFoundError("Incident", incident_id)

    changed: dict = {}
    for field in ("title", "description", "category"):
        val = getattr(payload, field)
        if val is not None and val != getattr(inc, field):
            setattr(inc, field, val)
            changed[field] = val
    if payload.priority_level is not None and payload.priority_level != inc.priority_level:
        inc.priority_level = payload.priority_level
        changed["priority_level"] = payload.priority_level.value
    if payload.status is not None and payload.status != inc.status:
        _apply_status(inc, payload.status, user)
        changed["status"] = payload.status.value

    if changed:
        db.add(inc)
        db.commit()
        db.refresh(inc)
        record_audit(
            db, action="INCIDENT_UPDATE", user_id=user.id, resource="incident",
            resource_id=inc.id, ip_address=client_ip(request),
            detail={"incident_number": inc.incident_number, "changed": changed},
        )
    return _incident_detail(db, inc)


@router.post("/{incident_id}/status", response_model=IncidentDetail)
def set_incident_status(
    incident_id: str,
    payload: IncidentStatusUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(_MANAGE),
):
    inc = db.get(Incident, incident_id)
    if inc is None:
        raise NotFoundError("Incident", incident_id)
    if payload.status != inc.status:
        prev = inc.status.value
        _apply_status(inc, payload.status, user)
        db.add(inc)
        db.commit()
        db.refresh(inc)
        record_audit(
            db, action="INCIDENT_STATUS", user_id=user.id, resource="incident",
            resource_id=inc.id, ip_address=client_ip(request),
            detail={"incident_number": inc.incident_number, "from": prev, "to": payload.status.value},
        )
    return _incident_detail(db, inc)


@router.post("/{incident_id}/assign", response_model=IncidentDetail)
def assign_incident(
    incident_id: str,
    payload: IncidentAssign,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(_MANAGE),
):
    inc = db.get(Incident, incident_id)
    if inc is None:
        raise NotFoundError("Incident", incident_id)

    assignee = None
    if payload.user_id:
        assignee = db.get(User, payload.user_id)
        if assignee is None or not assignee.is_active:
            raise NotFoundError("User", payload.user_id)

    inc.assigned_to_user_id = assignee.id if assignee else None
    # assigning an untouched NEW incident implicitly acknowledges it
    if assignee and inc.status == IncidentStatus.NEW:
        _apply_status(inc, IncidentStatus.ACKNOWLEDGED, user)
    db.add(inc)
    db.commit()
    db.refresh(inc)

    record_audit(
        db, action="INCIDENT_ASSIGN", user_id=user.id, resource="incident",
        resource_id=inc.id, ip_address=client_ip(request),
        detail={"incident_number": inc.incident_number,
                "assigned_to": assignee.username if assignee else None},
    )
    if assignee and assignee.id != user.id:
        push_notification(
            db, type="INCIDENT_ASSIGNED",
            title=f"Incident {inc.incident_number} assigned to you",
            body=inc.title, severity=NotificationSeverity.WARNING,
            resource="incident", resource_id=inc.id, target_user_id=assignee.id,
        )
    return _incident_detail(db, inc)


def _apply_status(inc: Incident, new: IncidentStatus, user: CurrentUser) -> None:
    """Mutate status + stamp the accountability fields. Caller commits."""
    inc.status = new
    now = datetime.utcnow()
    if new == IncidentStatus.ACKNOWLEDGED and inc.acknowledged_at is None:
        inc.acknowledged_by_user_id = user.id
        inc.acknowledged_at = now
    if new in (IncidentStatus.RESOLVED, IncidentStatus.CLOSED) and inc.resolved_at is None:
        inc.resolved_by_user_id = user.id
        inc.resolved_at = now
    # reopening clears the resolution stamps so they always reflect the last real close
    if new in (IncidentStatus.NEW, IncidentStatus.ACKNOWLEDGED, IncidentStatus.INVESTIGATING):
        inc.resolved_by_user_id = None
        inc.resolved_at = None


# --------------------------------------------------------------------------- #
#  notes                                                                      #
# --------------------------------------------------------------------------- #
@router.get("/{incident_id}/notes", response_model=list[IncidentNoteRead])
def list_incident_notes(
    incident_id: str,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
):
    if db.get(Incident, incident_id) is None:
        raise NotFoundError("Incident", incident_id)
    notes = db.execute(
        select(IncidentNote).where(IncidentNote.incident_id == incident_id)
        .order_by(IncidentNote.created_at.asc())
    ).scalars().all()
    usernames = resolve_usernames(db, [n.author_user_id for n in notes])
    return [
        IncidentNoteRead(
            id=n.id, incident_id=n.incident_id, author_user_id=n.author_user_id,
            author_username=usernames.get(n.author_user_id or ""), body=n.body,
            created_at=n.created_at,
        )
        for n in notes
    ]


@router.post("/{incident_id}/notes", response_model=IncidentNoteRead,
             status_code=status.HTTP_201_CREATED)
def add_incident_note(
    incident_id: str,
    payload: IncidentNoteCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(_MANAGE),
):
    inc = db.get(Incident, incident_id)
    if inc is None:
        raise NotFoundError("Incident", incident_id)
    note = IncidentNote(incident_id=inc.id, author_user_id=user.id, body=payload.body.strip())
    db.add(note)
    db.commit()
    db.refresh(note)
    record_audit(
        db, action="INCIDENT_NOTE_ADD", user_id=user.id, resource="incident",
        resource_id=inc.id, ip_address=client_ip(request),
        detail={"incident_number": inc.incident_number, "note_id": note.id},
    )
    return IncidentNoteRead(
        id=note.id, incident_id=note.incident_id, author_user_id=note.author_user_id,
        author_username=user.username, body=note.body, created_at=note.created_at,
    )


# --------------------------------------------------------------------------- #
#  evidence links                                                             #
# --------------------------------------------------------------------------- #
@router.get("/{incident_id}/evidence", response_model=list[IncidentEvidenceRead])
def list_incident_evidence(
    incident_id: str,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
):
    if db.get(Incident, incident_id) is None:
        raise NotFoundError("Incident", incident_id)
    links = db.execute(
        select(IncidentEvidence).where(IncidentEvidence.incident_id == incident_id)
        .order_by(IncidentEvidence.created_at.asc())
    ).scalars().all()
    events = {}
    if links:
        for ev in db.execute(
            select(VehicleEvent).where(VehicleEvent.id.in_([l.vehicle_event_id for l in links]))
        ).scalars().all():
            events[ev.id] = ev
    cameras = resolve_cameras(db, [e.camera_id for e in events.values()])
    usernames = resolve_usernames(db, [l.added_by_user_id for l in links])
    return [_evidence_read(l, events.get(l.vehicle_event_id), cameras, usernames) for l in links]


@router.post("/{incident_id}/evidence", response_model=IncidentEvidenceRead,
             status_code=status.HTTP_201_CREATED)
def attach_incident_evidence(
    incident_id: str,
    payload: IncidentEvidenceCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(_MANAGE),
):
    inc = db.get(Incident, incident_id)
    if inc is None:
        raise NotFoundError("Incident", incident_id)
    ev = db.get(VehicleEvent, payload.vehicle_event_id)
    if ev is None:
        raise NotFoundError("Vehicle event", payload.vehicle_event_id)

    existing = db.execute(
        select(IncidentEvidence).where(
            IncidentEvidence.incident_id == incident_id,
            IncidentEvidence.vehicle_event_id == payload.vehicle_event_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise SentinelException(
            code="EVIDENCE_ALREADY_ATTACHED",
            message="That evidence is already attached to this incident.",
            status_code=status.HTTP_409_CONFLICT,
        )

    link = IncidentEvidence(
        incident_id=incident_id, vehicle_event_id=payload.vehicle_event_id,
        added_by_user_id=user.id, note=payload.note,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    record_audit(
        db, action="INCIDENT_EVIDENCE_ADD", user_id=user.id, resource="incident",
        resource_id=incident_id, ip_address=client_ip(request),
        detail={"incident_number": inc.incident_number, "vehicle_event_id": payload.vehicle_event_id},
    )
    cameras = resolve_cameras(db, [ev.camera_id])
    return _evidence_read(link, ev, cameras, {user.id: user.username})


@router.delete("/{incident_id}/evidence/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def detach_incident_evidence(
    incident_id: str,
    link_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(_MANAGE),
):
    link = db.get(IncidentEvidence, link_id)
    if link is None or link.incident_id != incident_id:
        raise NotFoundError("Incident evidence link", link_id)
    db.delete(link)
    db.commit()
    record_audit(
        db, action="INCIDENT_EVIDENCE_REMOVE", user_id=user.id, resource="incident",
        resource_id=incident_id, ip_address=client_ip(request),
        detail={"vehicle_event_id": link.vehicle_event_id},
    )
