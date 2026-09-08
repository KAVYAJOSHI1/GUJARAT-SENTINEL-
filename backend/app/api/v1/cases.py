"""
Case management API (phase brief FEATURE 2).

A case is a folder of links: incidents, evidence (vehicle_events) and
notes. The unified detail view re-resolves every linked row live and
derives a chronological timeline + the primary vehicle's sighting count
on read -- nothing is denormalised.

RBAC: view -> any authenticated user; mutate -> ADMIN or OFFICER.
CSV export reuses a plain StreamingResponse (same "reuse existing export
mechanisms" intent as the frontend jsPDF path).
"""
import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlmodel import Session

from app.api.v1._enrich import next_sequence_number, resolve_cameras, resolve_usernames
from app.api.deps import get_current_user
from app.api.v1.incidents import _incident_read
from app.core.exceptions import NotFoundError, SentinelException
from app.core.rbac import require_roles
from app.database import get_db
from app.models.base import CaseStatus, NotificationSeverity, PriorityLevel, UserRole
from app.models.case import Case, CaseEvidence, CaseIncident, CaseNote
from app.models.incident import Incident, IncidentEvidence, IncidentNote
from app.models.user import User
from app.models.vehicle_event import VehicleEvent
from app.schemas.auth import CurrentUser
from app.schemas.case import (
    CaseAssign,
    CaseCreate,
    CaseDetail,
    CaseEvidenceCreate,
    CaseEvidenceRead,
    CaseIncidentAttach,
    CaseNoteCreate,
    CaseNoteRead,
    CasePage,
    CaseRead,
    CaseTimelineEntry,
    CaseUpdate,
)
from app.schemas.timeline import Timeline
from app.services.audit import client_ip, record_audit
from app.services.notifications import push_notification
from app.services.plate_utils import normalize_plate
from app.services.timeline_builder import build_case_timeline

router = APIRouter()

_MANAGE = require_roles(UserRole.ADMIN, UserRole.OFFICER)


def _case_read(c: Case, *, usernames: dict, incident_count=0, evidence_count=0, note_count=0) -> CaseRead:
    return CaseRead(
        id=c.id,
        case_number=c.case_number,
        title=c.title,
        description=c.description,
        priority_level=c.priority_level,
        status=c.status,
        primary_plate_normalized=c.primary_plate_normalized,
        created_by_user_id=c.created_by_user_id,
        created_by_username=usernames.get(c.created_by_user_id or ""),
        assigned_to_user_id=c.assigned_to_user_id,
        assigned_to_username=usernames.get(c.assigned_to_user_id or ""),
        created_at=c.created_at,
        updated_at=c.updated_at,
        incident_count=incident_count,
        evidence_count=evidence_count,
        note_count=note_count,
    )


def _evidence_read(link: CaseEvidence, ev, cameras: dict, usernames: dict) -> CaseEvidenceRead:
    cam = cameras.get((ev.camera_id if ev else "") or "", {})
    return CaseEvidenceRead(
        id=link.id, case_id=link.case_id, vehicle_event_id=link.vehicle_event_id,
        note=link.note, added_by_user_id=link.added_by_user_id,
        added_by_username=usernames.get(link.added_by_user_id or ""),
        created_at=link.created_at,
        plate_number=ev.plate_number if ev else None,
        camera_id=ev.camera_id if ev else None,
        camera_code=cam.get("code"), camera_name=cam.get("name"),
        event_timestamp=ev.timestamp if ev else None,
        has_snapshot=bool(ev and ev.snapshot_url),
    )


def _load_detail(db: Session, c: Case) -> CaseDetail:
    inc_links = db.execute(
        select(CaseIncident).where(CaseIncident.case_id == c.id)
        .order_by(CaseIncident.created_at.asc())
    ).scalars().all()
    incidents = []
    if inc_links:
        incidents = db.execute(
            select(Incident).where(Incident.id.in_([l.incident_id for l in inc_links]))
        ).scalars().all()

    ev_links = db.execute(
        select(CaseEvidence).where(CaseEvidence.case_id == c.id)
        .order_by(CaseEvidence.created_at.asc())
    ).scalars().all()
    events = {}
    if ev_links:
        for ev in db.execute(
            select(VehicleEvent).where(VehicleEvent.id.in_([l.vehicle_event_id for l in ev_links]))
        ).scalars().all():
            events[ev.id] = ev

    notes = db.execute(
        select(CaseNote).where(CaseNote.case_id == c.id).order_by(CaseNote.created_at.asc())
    ).scalars().all()

    # incident note/evidence counts (bulk, no N+1)
    inc_ids = [i.id for i in incidents]
    inc_note_counts: dict[str, int] = {}
    inc_ev_counts: dict[str, int] = {}
    if inc_ids:
        for iid, cnt in db.execute(
            select(IncidentNote.incident_id, func.count(IncidentNote.id))
            .where(IncidentNote.incident_id.in_(inc_ids)).group_by(IncidentNote.incident_id)
        ).all():
            inc_note_counts[iid] = cnt
        for iid, cnt in db.execute(
            select(IncidentEvidence.incident_id, func.count(IncidentEvidence.id))
            .where(IncidentEvidence.incident_id.in_(inc_ids)).group_by(IncidentEvidence.incident_id)
        ).all():
            inc_ev_counts[iid] = cnt

    user_ids = (
        [c.created_by_user_id, c.assigned_to_user_id]
        + [n.author_user_id for n in notes]
        + [l.added_by_user_id for l in ev_links]
        + [i.created_by_user_id for i in incidents] + [i.assigned_to_user_id for i in incidents]
        + [i.acknowledged_by_user_id for i in incidents] + [i.resolved_by_user_id for i in incidents]
    )
    usernames = resolve_usernames(db, user_ids)
    cameras = resolve_cameras(
        db, [i.camera_id for i in incidents] + [ev.camera_id for ev in events.values()]
    )

    sighting_count = 0
    if c.primary_plate_normalized:
        sighting_count = db.execute(
            select(func.count(VehicleEvent.id)).where(
                VehicleEvent.plate_number_normalized == c.primary_plate_normalized
            )
        ).scalar() or 0

    detail = CaseDetail(
        **_case_read(
            c, usernames=usernames, incident_count=len(inc_links),
            evidence_count=len(ev_links), note_count=len(notes),
        ).model_dump()
    )
    detail.incidents = [
        _incident_read(i, usernames=usernames, cameras=cameras,
                       note_count=inc_note_counts.get(i.id, 0),
                       evidence_count=inc_ev_counts.get(i.id, 0))
        for i in incidents
    ]
    detail.evidence = [_evidence_read(l, events.get(l.vehicle_event_id), cameras, usernames)
                       for l in ev_links]
    detail.notes = [
        CaseNoteRead(id=n.id, case_id=n.case_id, author_user_id=n.author_user_id,
                     author_username=usernames.get(n.author_user_id or ""),
                     body=n.body, created_at=n.created_at)
        for n in notes
    ]
    detail.sighting_count = int(sighting_count)
    detail.timeline = _build_timeline(c, incidents, ev_links, events, notes)
    return detail


def _build_timeline(c, incidents, ev_links, events, notes) -> list[CaseTimelineEntry]:
    entries = [CaseTimelineEntry(
        timestamp=c.created_at, kind="CASE_CREATED", label=f"Case {c.case_number} opened",
        ref_id=c.id,
    )]
    for i in incidents:
        entries.append(CaseTimelineEntry(
            timestamp=i.created_at, kind="INCIDENT",
            label=f"{i.incident_number}: {i.title}", ref_id=i.id,
        ))
    for l in ev_links:
        ev = events.get(l.vehicle_event_id)
        ts = ev.timestamp if ev else l.created_at
        label = "Evidence attached"
        if ev:
            label = f"Sighting {ev.plate_number} @ {ev.camera_code or ev.camera_id}"
        entries.append(CaseTimelineEntry(timestamp=ts, kind="EVIDENCE", label=label, ref_id=l.vehicle_event_id))
    for n in notes:
        entries.append(CaseTimelineEntry(
            timestamp=n.created_at, kind="NOTE",
            label=(n.body[:80] + "…") if len(n.body) > 80 else n.body, ref_id=n.id,
        ))
    entries.sort(key=lambda e: e.timestamp)
    return entries


def _reload(db: Session, case_id: str) -> CaseDetail:
    c = db.get(Case, case_id)
    if c is None:
        raise NotFoundError("Case", case_id)
    return _load_detail(db, c)


# --------------------------------------------------------------------------- #
@router.get("", response_model=CasePage)
def list_cases(
    status_filter: str | None = Query(default=None, alias="status"),
    priority: PriorityLevel | None = Query(default=None),
    assigned_to: str | None = Query(default=None),
    plate: str | None = Query(default=None),
    q: str | None = Query(default=None),
    active_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
):
    conds = []
    if status_filter:
        conds.append(Case.status == status_filter)
    if active_only:
        conds.append(Case.status.notin_([CaseStatus.RESOLVED, CaseStatus.CLOSED]))
    if priority:
        conds.append(Case.priority_level == priority)
    if assigned_to:
        conds.append(Case.assigned_to_user_id == assigned_to)
    if plate:
        conds.append(Case.primary_plate_normalized == normalize_plate(plate))
    if q:
        like = f"%{q.strip()}%"
        conds.append(Case.title.ilike(like) | Case.case_number.ilike(like))

    total = db.execute(select(func.count(Case.id)).where(*conds)).scalar() or 0
    rows = db.execute(
        select(Case).where(*conds).order_by(Case.created_at.desc()).limit(limit).offset(offset)
    ).scalars().all()

    ids = [r.id for r in rows]
    inc_counts: dict[str, int] = {}
    ev_counts: dict[str, int] = {}
    note_counts: dict[str, int] = {}
    if ids:
        for cid, cnt in db.execute(
            select(CaseIncident.case_id, func.count(CaseIncident.id))
            .where(CaseIncident.case_id.in_(ids)).group_by(CaseIncident.case_id)
        ).all():
            inc_counts[cid] = cnt
        for cid, cnt in db.execute(
            select(CaseEvidence.case_id, func.count(CaseEvidence.id))
            .where(CaseEvidence.case_id.in_(ids)).group_by(CaseEvidence.case_id)
        ).all():
            ev_counts[cid] = cnt
        for cid, cnt in db.execute(
            select(CaseNote.case_id, func.count(CaseNote.id))
            .where(CaseNote.case_id.in_(ids)).group_by(CaseNote.case_id)
        ).all():
            note_counts[cid] = cnt

    usernames = resolve_usernames(
        db, [r.created_by_user_id for r in rows] + [r.assigned_to_user_id for r in rows]
    )
    items = [
        _case_read(r, usernames=usernames, incident_count=inc_counts.get(r.id, 0),
                   evidence_count=ev_counts.get(r.id, 0), note_count=note_counts.get(r.id, 0))
        for r in rows
    ]
    return CasePage(items=items, total=int(total), limit=limit, offset=offset)


@router.post("", response_model=CaseDetail, status_code=status.HTTP_201_CREATED)
def create_case(
    payload: CaseCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(_MANAGE),
):
    c = Case(
        case_number=next_sequence_number(db, "CASE", Case, Case.case_number),
        title=payload.title.strip(),
        description=payload.description,
        priority_level=payload.priority_level or PriorityLevel.MEDIUM,
        status=CaseStatus.OPEN,
        primary_plate_normalized=(
            normalize_plate(payload.primary_plate_number) if payload.primary_plate_number else None
        ),
        created_by_user_id=user.id,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    record_audit(
        db, action="CASE_CREATE", user_id=user.id, resource="case", resource_id=c.id,
        ip_address=client_ip(request),
        detail={"case_number": c.case_number, "plate": c.primary_plate_normalized},
    )
    return _load_detail(db, c)


@router.get("/{case_id}", response_model=CaseDetail)
def get_case(case_id: str, db: Session = Depends(get_db), _: CurrentUser = Depends(get_current_user)):
    return _reload(db, case_id)


@router.get("/{case_id}/timeline", response_model=Timeline)
def get_case_timeline(
    case_id: str,
    category: str | None = Query(
        default=None,
        description="comma-separated filter: CASE,INCIDENT,EVIDENCE,NOTE,VEHICLE,STATUS,ACTIVITY",
    ),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
):
    """Unified case timeline (FEATURE 8) -- case creation, incident/evidence
    links, notes, vehicle sightings, assignments, status changes and report
    exports, all derived from existing rows."""
    c = db.get(Case, case_id)
    if c is None:
        raise NotFoundError("Case", case_id)
    cats = {x.strip().upper() for x in category.split(",")} if category else None
    return build_case_timeline(db, c, cats)


@router.patch("/{case_id}", response_model=CaseDetail)
def update_case(
    case_id: str,
    payload: CaseUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(_MANAGE),
):
    c = db.get(Case, case_id)
    if c is None:
        raise NotFoundError("Case", case_id)
    changed: dict = {}
    if payload.title is not None and payload.title != c.title:
        c.title = payload.title.strip(); changed["title"] = c.title
    if payload.description is not None and payload.description != c.description:
        c.description = payload.description; changed["description"] = "updated"
    if payload.priority_level is not None and payload.priority_level != c.priority_level:
        c.priority_level = payload.priority_level; changed["priority_level"] = payload.priority_level.value
    if payload.status is not None and payload.status != c.status:
        changed["status"] = payload.status.value
        c.status = payload.status
    if payload.primary_plate_number is not None:
        norm = normalize_plate(payload.primary_plate_number) or None
        if norm != c.primary_plate_normalized:
            c.primary_plate_normalized = norm; changed["primary_plate"] = norm
    if changed:
        db.add(c)
        db.commit()
        db.refresh(c)
        record_audit(
            db, action="CASE_UPDATE", user_id=user.id, resource="case", resource_id=c.id,
            ip_address=client_ip(request),
            detail={"case_number": c.case_number, "changed": changed},
        )
    return _load_detail(db, c)


@router.post("/{case_id}/assign", response_model=CaseDetail)
def assign_case(
    case_id: str,
    payload: CaseAssign,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(_MANAGE),
):
    c = db.get(Case, case_id)
    if c is None:
        raise NotFoundError("Case", case_id)
    assignee = None
    if payload.user_id:
        assignee = db.get(User, payload.user_id)
        if assignee is None or not assignee.is_active:
            raise NotFoundError("User", payload.user_id)
    c.assigned_to_user_id = assignee.id if assignee else None
    db.add(c)
    db.commit()
    db.refresh(c)
    record_audit(
        db, action="CASE_ASSIGN", user_id=user.id, resource="case", resource_id=c.id,
        ip_address=client_ip(request),
        detail={"case_number": c.case_number, "assigned_to": assignee.username if assignee else None},
    )
    if assignee and assignee.id != user.id:
        push_notification(
            db, type="CASE_ASSIGNED", title=f"Case {c.case_number} assigned to you",
            body=c.title, severity=NotificationSeverity.WARNING,
            resource="case", resource_id=c.id, target_user_id=assignee.id,
        )
    return _load_detail(db, c)


# ---- notes ----------------------------------------------------------------- #
@router.post("/{case_id}/notes", response_model=CaseNoteRead, status_code=status.HTTP_201_CREATED)
def add_case_note(
    case_id: str,
    payload: CaseNoteCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(_MANAGE),
):
    c = db.get(Case, case_id)
    if c is None:
        raise NotFoundError("Case", case_id)
    note = CaseNote(case_id=c.id, author_user_id=user.id, body=payload.body.strip())
    db.add(note)
    db.commit()
    db.refresh(note)
    record_audit(
        db, action="CASE_NOTE_ADD", user_id=user.id, resource="case", resource_id=c.id,
        ip_address=client_ip(request), detail={"case_number": c.case_number, "note_id": note.id},
    )
    return CaseNoteRead(
        id=note.id, case_id=note.case_id, author_user_id=note.author_user_id,
        author_username=user.username, body=note.body, created_at=note.created_at,
    )


# ---- incident links ------------------------------------------------------- #
@router.post("/{case_id}/incidents", response_model=CaseDetail, status_code=status.HTTP_201_CREATED)
def attach_incident(
    case_id: str,
    payload: CaseIncidentAttach,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(_MANAGE),
):
    c = db.get(Case, case_id)
    if c is None:
        raise NotFoundError("Case", case_id)
    inc = db.get(Incident, payload.incident_id)
    if inc is None:
        raise NotFoundError("Incident", payload.incident_id)
    existing = db.execute(
        select(CaseIncident).where(
            CaseIncident.case_id == case_id, CaseIncident.incident_id == payload.incident_id
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise SentinelException(
            code="INCIDENT_ALREADY_LINKED",
            message="That incident is already attached to this case.",
            status_code=status.HTTP_409_CONFLICT,
        )
    db.add(CaseIncident(case_id=case_id, incident_id=payload.incident_id, added_by_user_id=user.id))
    db.commit()
    record_audit(
        db, action="CASE_INCIDENT_ADD", user_id=user.id, resource="case", resource_id=case_id,
        ip_address=client_ip(request),
        detail={"case_number": c.case_number, "incident_number": inc.incident_number},
    )
    return _reload(db, case_id)


@router.delete("/{case_id}/incidents/{incident_id}", status_code=status.HTTP_204_NO_CONTENT)
def detach_incident(
    case_id: str,
    incident_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(_MANAGE),
):
    link = db.execute(
        select(CaseIncident).where(
            CaseIncident.case_id == case_id, CaseIncident.incident_id == incident_id
        )
    ).scalar_one_or_none()
    if link is None:
        raise NotFoundError("Case-incident link", incident_id)
    db.delete(link)
    db.commit()
    record_audit(
        db, action="CASE_INCIDENT_REMOVE", user_id=user.id, resource="case", resource_id=case_id,
        ip_address=client_ip(request), detail={"incident_id": incident_id},
    )


# ---- evidence links ------------------------------------------------------- #
@router.post("/{case_id}/evidence", response_model=CaseEvidenceRead, status_code=status.HTTP_201_CREATED)
def attach_case_evidence(
    case_id: str,
    payload: CaseEvidenceCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(_MANAGE),
):
    c = db.get(Case, case_id)
    if c is None:
        raise NotFoundError("Case", case_id)
    ev = db.get(VehicleEvent, payload.vehicle_event_id)
    if ev is None:
        raise NotFoundError("Vehicle event", payload.vehicle_event_id)
    existing = db.execute(
        select(CaseEvidence).where(
            CaseEvidence.case_id == case_id,
            CaseEvidence.vehicle_event_id == payload.vehicle_event_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise SentinelException(
            code="EVIDENCE_ALREADY_ATTACHED",
            message="That evidence is already attached to this case.",
            status_code=status.HTTP_409_CONFLICT,
        )
    link = CaseEvidence(
        case_id=case_id, vehicle_event_id=payload.vehicle_event_id,
        added_by_user_id=user.id, note=payload.note,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    record_audit(
        db, action="CASE_EVIDENCE_ADD", user_id=user.id, resource="case", resource_id=case_id,
        ip_address=client_ip(request),
        detail={"case_number": c.case_number, "vehicle_event_id": payload.vehicle_event_id},
    )
    cameras = resolve_cameras(db, [ev.camera_id])
    return _evidence_read(link, ev, cameras, {user.id: user.username})


@router.delete("/{case_id}/evidence/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def detach_case_evidence(
    case_id: str,
    link_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(_MANAGE),
):
    link = db.get(CaseEvidence, link_id)
    if link is None or link.case_id != case_id:
        raise NotFoundError("Case evidence link", link_id)
    db.delete(link)
    db.commit()
    record_audit(
        db, action="CASE_EVIDENCE_REMOVE", user_id=user.id, resource="case", resource_id=case_id,
        ip_address=client_ip(request), detail={"vehicle_event_id": link.vehicle_event_id},
    )


# ---- report export ------------------------------------------------------- #
@router.get("/{case_id}/report")
def export_case_report(
    case_id: str,
    format: str = Query(default="json", pattern="^(json|csv)$"),
    request: Request = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    detail = _reload(db, case_id)
    record_audit(
        db, action="CASE_REPORT_EXPORT", user_id=user.id, resource="case", resource_id=case_id,
        ip_address=client_ip(request) if request else None,
        detail={"case_number": detail.case_number, "format": format},
    )
    if format == "json":
        return detail

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["SENTINEL Case Report", detail.case_number])
    w.writerow(["Title", detail.title])
    w.writerow(["Status", detail.status.value])
    w.writerow(["Priority", detail.priority_level.value])
    w.writerow(["Primary vehicle", detail.primary_plate_normalized or "—"])
    w.writerow(["Assigned to", detail.assigned_to_username or "—"])
    w.writerow(["Created", detail.created_at.isoformat()])
    w.writerow(["Generated", datetime.utcnow().isoformat() + "Z"])
    w.writerow([])
    w.writerow(["INCIDENTS"])
    w.writerow(["incident_number", "title", "status", "priority", "assigned_to", "created_at"])
    for i in detail.incidents:
        w.writerow([i.incident_number, i.title, i.status.value, i.priority_level.value,
                    i.assigned_to_username or "", i.created_at.isoformat()])
    w.writerow([])
    w.writerow(["EVIDENCE"])
    w.writerow(["vehicle_event_id", "plate", "camera", "timestamp", "added_by", "note"])
    for e in detail.evidence:
        w.writerow([e.vehicle_event_id, e.plate_number or "", e.camera_code or e.camera_id or "",
                    e.event_timestamp.isoformat() if e.event_timestamp else "",
                    e.added_by_username or "", e.note or ""])
    w.writerow([])
    w.writerow(["TIMELINE"])
    w.writerow(["timestamp", "kind", "label"])
    for t in detail.timeline:
        w.writerow([t.timestamp.isoformat(), t.kind, t.label])
    w.writerow([])
    w.writerow(["OFFICER NOTES"])
    w.writerow(["timestamp", "author", "note"])
    for n in detail.notes:
        w.writerow([n.created_at.isoformat(), n.author_username or "", n.body])

    buf.seek(0)
    filename = f"{detail.case_number}_report.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
