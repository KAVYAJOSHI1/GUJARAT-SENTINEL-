"""
Derive Incident / Case timelines from existing rows (FEATURE 7 / 8).

No new event table: a timeline is assembled at read time from audit_logs,
the entity's own timestamps, its notes / evidence links, and the vehicle's
camera sightings. Bounded queries only.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Iterable

from sqlalchemy import select
from sqlmodel import Session

from app.api.v1._enrich import resolve_usernames
from app.models.alert import Alert
from app.models.audit_log import AuditLog
from app.models.camera import Camera
from app.models.case import Case, CaseEvidence, CaseIncident, CaseNote
from app.models.incident import Incident, IncidentEvidence, IncidentNote
from app.models.vehicle_event import VehicleEvent
from app.schemas.timeline import Timeline, TimelineEntry

_MAX_SIGHTINGS = 50

# audit action -> (category, human verb)
_AUDIT_VERBS = {
    "ALERT_ACKNOWLEDGED": ("ALERT", "Alert acknowledged"),
    "ALERT_ASSIGNED": ("ALERT", "Alert assigned"),
    "ALERT_ESCALATED": ("ALERT", "Alert escalated"),
    "ALERT_RESOLVED": ("ALERT", "Alert resolved"),
    "INCIDENT_CREATE": ("INCIDENT", "Incident created"),
    "INCIDENT_UPDATE": ("STATUS", "Incident updated"),
    "INCIDENT_STATUS": ("STATUS", "Status changed"),
    "INCIDENT_ASSIGN": ("ACTIVITY", "Officer assigned"),
    "INCIDENT_NOTE_ADD": ("NOTE", "Note added"),
    "INCIDENT_EVIDENCE_ADD": ("EVIDENCE", "Evidence attached"),
    "INCIDENT_EVIDENCE_REMOVE": ("EVIDENCE", "Evidence removed"),
    "CASE_CREATE": ("CASE", "Case created"),
    "CASE_UPDATE": ("STATUS", "Case updated"),
    "CASE_ASSIGN": ("ACTIVITY", "Officer assigned"),
    "CASE_NOTE_ADD": ("NOTE", "Note added"),
    "CASE_INCIDENT_ADD": ("INCIDENT", "Incident linked"),
    "CASE_INCIDENT_REMOVE": ("INCIDENT", "Incident unlinked"),
    "CASE_EVIDENCE_ADD": ("EVIDENCE", "Evidence attached"),
    "CASE_EVIDENCE_REMOVE": ("EVIDENCE", "Evidence removed"),
    "CASE_REPORT_EXPORT": ("ACTIVITY", "Report exported"),
}


def _detail_text(action: str, raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        d = json.loads(raw)
    except (ValueError, TypeError):
        return raw[:200]
    if not isinstance(d, dict):
        return str(d)[:200]
    if "changed" in d and isinstance(d["changed"], dict):
        return ", ".join(f"{k}={v}" for k, v in d["changed"].items())[:200]
    for k in ("to", "status", "assigned_to", "reason", "format", "incident_number", "note"):
        if d.get(k):
            return f"{k}: {d[k]}"[:200]
    return None


def _audit_entries(db: Session, resource: str, resource_id: str) -> list[TimelineEntry]:
    rows = db.execute(
        select(AuditLog).where(AuditLog.resource == resource, AuditLog.resource_id == resource_id)
        .order_by(AuditLog.created_at.asc())
    ).scalars().all()
    usernames = resolve_usernames(db, [r.user_id for r in rows])
    out = []
    for r in rows:
        cat, verb = _AUDIT_VERBS.get(r.action, ("ACTIVITY", r.action.replace("_", " ").title()))
        out.append(TimelineEntry(
            timestamp=r.created_at, category=cat, action=verb,
            actor=usernames.get(r.user_id or ""), detail=_detail_text(r.action, r.detail),
            ref_kind=resource, ref_id=resource_id,
        ))
    return out


def _sighting_entries(db: Session, plate_normalized: str | None) -> list[TimelineEntry]:
    if not plate_normalized:
        return []
    rows = db.execute(
        select(VehicleEvent, Camera.code, Camera.name)
        .join(Camera, Camera.id == VehicleEvent.camera_id, isouter=True)
        .where(VehicleEvent.plate_number_normalized == plate_normalized)
        .order_by(VehicleEvent.timestamp.asc())
        .limit(_MAX_SIGHTINGS)
    ).all()
    out = []
    for ev, code, name in rows:
        out.append(TimelineEntry(
            timestamp=ev.timestamp, category="VEHICLE", action="Vehicle sighting",
            actor=None,
            detail=f"{ev.plate_number} at {code or name or ev.camera_id}"
                   + (f" · {ev.confidence_score:.0%} conf" if ev.confidence_score else ""),
            ref_kind="vehicle_event", ref_id=ev.id,
        ))
    return out


def _finalise(entries: Iterable[TimelineEntry], categories_filter: set[str] | None) -> Timeline:
    entries = sorted(entries, key=lambda e: e.timestamp)
    all_cats = sorted({e.category for e in entries})
    if categories_filter:
        entries = [e for e in entries if e.category in categories_filter]
    return Timeline(entries=list(entries), categories=all_cats)


def build_incident_timeline(
    db: Session, incident: Incident, categories: set[str] | None = None
) -> Timeline:
    entries: list[TimelineEntry] = []

    # linked alert
    if incident.alert_id:
        alert = db.get(Alert, incident.alert_id)
        if alert is not None:
            entries.append(TimelineEntry(
                timestamp=alert.created_at, category="ALERT", action="Alert raised",
                actor=None,
                detail=f"Watchlist match {alert.plate_number_normalized} "
                       f"({alert.priority_level.value})",
                ref_kind="alert", ref_id=alert.id,
            ))
            entries += _audit_entries(db, "alert", alert.id)

    # incident's own audit trail + creation
    entries.append(TimelineEntry(
        timestamp=incident.created_at, category="INCIDENT", action="Incident created",
        actor=None, detail=incident.title, ref_kind="incident", ref_id=incident.id,
    ))
    entries += _audit_entries(db, "incident", incident.id)

    # notes (body text — the audit row only has an id)
    for n in db.execute(
        select(IncidentNote).where(IncidentNote.incident_id == incident.id)
    ).scalars():
        usernames = resolve_usernames(db, [n.author_user_id])
        entries.append(TimelineEntry(
            timestamp=n.created_at, category="NOTE", action="Officer remark",
            actor=usernames.get(n.author_user_id or ""), detail=n.body[:280],
            ref_kind="note", ref_id=n.id,
        ))

    # explicit evidence links (event timestamp shown as the sighting)
    ev_links = db.execute(
        select(IncidentEvidence).where(IncidentEvidence.incident_id == incident.id)
    ).scalars().all()
    if ev_links:
        events = {
            e.id: e for e in db.execute(
                select(VehicleEvent).where(
                    VehicleEvent.id.in_([l.vehicle_event_id for l in ev_links])
                )
            ).scalars()
        }
        for l in ev_links:
            ev = events.get(l.vehicle_event_id)
            entries.append(TimelineEntry(
                timestamp=l.created_at, category="EVIDENCE", action="Evidence attached",
                actor=None,
                detail=(f"{ev.plate_number} @ {ev.camera_code}" if ev else l.vehicle_event_id),
                ref_kind="vehicle_event", ref_id=l.vehicle_event_id,
            ))

    entries += _sighting_entries(db, incident.plate_number_normalized)

    # resolution / closure stamps
    if incident.resolved_at:
        entries.append(TimelineEntry(
            timestamp=incident.resolved_at, category="STATUS", action="Incident resolved",
            actor=None, ref_kind="incident", ref_id=incident.id,
        ))
    return _finalise(entries, categories)


def build_case_timeline(db: Session, case: Case, categories: set[str] | None = None) -> Timeline:
    entries: list[TimelineEntry] = [TimelineEntry(
        timestamp=case.created_at, category="CASE", action="Case opened",
        actor=None, detail=case.title, ref_kind="case", ref_id=case.id,
    )]
    entries += _audit_entries(db, "case", case.id)

    inc_links = db.execute(
        select(CaseIncident).where(CaseIncident.case_id == case.id)
    ).scalars().all()
    incidents = {}
    if inc_links:
        incidents = {
            i.id: i for i in db.execute(
                select(Incident).where(Incident.id.in_([l.incident_id for l in inc_links]))
            ).scalars()
        }
        for l in inc_links:
            i = incidents.get(l.incident_id)
            entries.append(TimelineEntry(
                timestamp=l.created_at, category="INCIDENT", action="Incident linked",
                actor=None, detail=(f"{i.incident_number}: {i.title}" if i else l.incident_id),
                ref_kind="incident", ref_id=l.incident_id,
            ))

    ev_links = db.execute(
        select(CaseEvidence).where(CaseEvidence.case_id == case.id)
    ).scalars().all()
    if ev_links:
        events = {
            e.id: e for e in db.execute(
                select(VehicleEvent).where(
                    VehicleEvent.id.in_([l.vehicle_event_id for l in ev_links])
                )
            ).scalars()
        }
        for l in ev_links:
            ev = events.get(l.vehicle_event_id)
            ts = ev.timestamp if ev else l.created_at
            entries.append(TimelineEntry(
                timestamp=ts, category="EVIDENCE", action="Evidence attached",
                actor=None,
                detail=(f"{ev.plate_number} @ {ev.camera_code}" if ev else l.vehicle_event_id),
                ref_kind="vehicle_event", ref_id=l.vehicle_event_id,
            ))

    for n in db.execute(select(CaseNote).where(CaseNote.case_id == case.id)).scalars():
        usernames = resolve_usernames(db, [n.author_user_id])
        entries.append(TimelineEntry(
            timestamp=n.created_at, category="NOTE", action="Officer note",
            actor=usernames.get(n.author_user_id or ""), detail=n.body[:280],
            ref_kind="note", ref_id=n.id,
        ))

    entries += _sighting_entries(db, case.primary_plate_normalized)
    return _finalise(entries, categories)
