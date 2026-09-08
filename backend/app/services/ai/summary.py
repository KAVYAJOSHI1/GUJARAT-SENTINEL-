"""
AI incident / case summary (phase brief §3).

Deterministic structured summary built ONLY from existing rows (the
incident/case, its linked alert, notes, evidence links, and the vehicle's
recorded sightings). If an LLM is configured it re-words the headline --
it is never given anything the summary didn't already establish.

Every section is tagged FACT (straight from data) or INFERENCE. Missing
information is stated as "Not available in recorded evidence." -- never
filled in.
"""
from __future__ import annotations

from datetime import datetime

from sqlmodel import Session

from app.models.alert import Alert
from app.models.base import ConfidenceLevel
from app.models.case import Case, CaseEvidence, CaseIncident, CaseNote
from app.models.incident import Incident, IncidentEvidence, IncidentNote
from app.schemas.ai import AISummaryResponse, SummarySection
from app.services.ai.confidence import level_from_score
from app.services.ai.llm import get_llm_provider
from app.services.ai.tools import InvestigationTools
from sqlalchemy import func, select

_GAP_MINUTES = 20


def _fmt(v) -> str:
    return v.strftime("%d %b %H:%M") if isinstance(v, datetime) else str(v)


def _journey_facts(db: Session, plate: str | None):
    if not plate:
        return None
    return InvestigationTools(db).get_vehicle_journey(plate)


def _gaps(sightings: list[dict]) -> list[str]:
    gaps = []
    for a, b in zip(sightings, sightings[1:]):
        mins = (b["timestamp"] - a["timestamp"]).total_seconds() / 60
        if mins >= _GAP_MINUTES:
            gaps.append(
                f"No confirmed sighting between {a['camera_code'] or a['camera_id']} "
                f"({_fmt(a['timestamp'])}) and {b['camera_code'] or b['camera_id']} "
                f"({_fmt(b['timestamp'])}) — a {int(mins)} min gap."
            )
    return gaps


def build_incident_summary(db: Session, inc: Incident) -> AISummaryResponse:
    provider = get_llm_provider()
    notes = db.execute(
        select(func.count(IncidentNote.id)).where(IncidentNote.incident_id == inc.id)
    ).scalar() or 0
    ev_count = db.execute(
        select(func.count(IncidentEvidence.id)).where(IncidentEvidence.incident_id == inc.id)
    ).scalar() or 0
    alert = db.get(Alert, inc.alert_id) if inc.alert_id else None
    journey = _journey_facts(db, inc.plate_number_normalized)

    sections: list[SummarySection] = [
        SummarySection(label="Incident", value=f"{inc.incident_number} — {inc.title}"),
        SummarySection(label="Category / priority", value=f"{inc.category} · {inc.priority_level.value}"),
        SummarySection(label="Status", value=inc.status.value),
        SummarySection(label="Vehicle", value=inc.plate_number_normalized or "Not available in recorded evidence."),
        SummarySection(label="Opened", value=f"{_fmt(inc.created_at)}"
                       + (f" by {inc.created_by_user_id[:8]}" if inc.created_by_user_id else "")),
    ]
    if alert:
        sections.append(SummarySection(
            label="Originating alert",
            value=f"{alert.source.value} match · {alert.priority_level.value} · raised {_fmt(alert.created_at)}",
        ))
    else:
        sections.append(SummarySection(label="Originating alert", value="None (manually opened).", is_fact=True))

    gaps: list[str] = []
    if journey and journey["sightings"]:
        s = journey["sightings"]
        cams = " → ".join(dict.fromkeys(x["camera_code"] or x["camera_id"] for x in s))
        sections += [
            SummarySection(label="First detection", value=f"{_fmt(s[0]['timestamp'])} at {s[0]['camera_code'] or s[0]['camera_id']}"),
            SummarySection(label="Last detection", value=f"{_fmt(s[-1]['timestamp'])} at {s[-1]['camera_code'] or s[-1]['camera_id']}"),
            SummarySection(label="Cameras", value=cams),
            SummarySection(label="Journey", value=f"{len(s)} sighting(s), {journey['distinct_cameras']} camera(s), span {journey['span_seconds']//60} min"),
        ]
        gaps = _gaps(s)
    elif inc.plate_number_normalized:
        sections.append(SummarySection(label="Journey", value="Not available in recorded evidence."))

    sections.append(SummarySection(label="Evidence items", value=str(ev_count)))
    sections.append(SummarySection(label="Officer notes", value=str(notes)))
    if inc.resolved_at:
        sections.append(SummarySection(label="Resolved", value=_fmt(inc.resolved_at)))

    if ev_count == 0:
        gaps.append("No evidence attached to this incident yet.")
    if notes == 0:
        gaps.append("No officer notes recorded yet.")

    # headline (deterministic)
    if journey and journey["sightings"]:
        s = journey["sightings"]
        head = (
            f"Vehicle {inc.plate_number_normalized} was detected at {journey['distinct_cameras']} "
            f"camera(s) between {_fmt(s[0]['timestamp'])} and {_fmt(s[-1]['timestamp'])}."
        )
        if alert:
            head += f" A {alert.source.value.lower()} match generated an alert at {_fmt(alert.created_at)}."
        head += f" Evidence contains {ev_count} item(s)."
        if gaps:
            head += f" {gaps[0]}"
    else:
        head = (
            f"Incident {inc.incident_number} ({inc.status.value}). "
            + (f"Vehicle {inc.plate_number_normalized}. " if inc.plate_number_normalized else "")
            + f"{ev_count} evidence item(s), {notes} note(s). "
            + ("No recorded sightings for the vehicle of interest." if inc.plate_number_normalized else "")
        )
    facts = {"sections": [s.model_dump() for s in sections], "gaps": gaps}
    head = provider.narrate(f"Summarise incident {inc.incident_number}", facts, head)

    score = 0.85 if (journey and journey["sightings"]) else (0.5 if inc.plate_number_normalized else 0.3)
    return AISummaryResponse(
        subject_kind="incident", subject_id=inc.id, subject_ref=inc.incident_number,
        provider=provider.name, headline=head, sections=sections, investigation_gaps=gaps,
        confidence_level=level_from_score(score), generated_at=datetime.utcnow(),
    )


def build_case_summary(db: Session, case: Case) -> AISummaryResponse:
    provider = get_llm_provider()
    inc_ids = [r for (r,) in db.execute(
        select(CaseIncident.incident_id).where(CaseIncident.case_id == case.id)).all()]
    incidents = db.execute(select(Incident).where(Incident.id.in_(inc_ids))).scalars().all() if inc_ids else []
    ev_count = db.execute(
        select(func.count(CaseEvidence.id)).where(CaseEvidence.case_id == case.id)).scalar() or 0
    note_count = db.execute(
        select(func.count(CaseNote.id)).where(CaseNote.case_id == case.id)).scalar() or 0
    journey = _journey_facts(db, case.primary_plate_normalized)

    sections = [
        SummarySection(label="Case", value=f"{case.case_number} — {case.title}"),
        SummarySection(label="Status / priority", value=f"{case.status.value} · {case.priority_level.value}"),
        SummarySection(label="Primary vehicle", value=case.primary_plate_normalized or "Not available in recorded evidence."),
        SummarySection(label="Opened", value=_fmt(case.created_at)),
        SummarySection(label="Linked incidents", value=str(len(incidents))),
        SummarySection(label="Evidence items", value=str(ev_count)),
        SummarySection(label="Officer notes", value=str(note_count)),
    ]
    gaps: list[str] = []
    if journey and journey["sightings"]:
        s = journey["sightings"]
        sections.append(SummarySection(
            label="Vehicle activity",
            value=f"{len(s)} sighting(s) across {journey['distinct_cameras']} camera(s), "
                  f"{_fmt(s[0]['timestamp'])} – {_fmt(s[-1]['timestamp'])}"))
        gaps = _gaps(s)
    elif case.primary_plate_normalized:
        sections.append(SummarySection(label="Vehicle activity", value="Not available in recorded evidence."))
    for i in incidents:
        sections.append(SummarySection(label=f"Incident {i.incident_number}",
                                       value=f"{i.status.value} · {i.title}"))
    if not incidents:
        gaps.append("No incidents linked to this case yet.")
    if ev_count == 0:
        gaps.append("No evidence attached to this case yet.")

    head = (
        f"Case {case.case_number} ({case.status.value}) covers "
        + (f"vehicle {case.primary_plate_normalized}, " if case.primary_plate_normalized else "")
        + f"{len(incidents)} incident(s), {ev_count} evidence item(s) and {note_count} note(s)."
    )
    if journey and journey["sightings"]:
        s = journey["sightings"]
        head += (f" The vehicle was recorded at {journey['distinct_cameras']} camera(s) between "
                 f"{_fmt(s[0]['timestamp'])} and {_fmt(s[-1]['timestamp'])}.")
    if gaps:
        head += f" {gaps[0]}"
    facts = {"sections": [s.model_dump() for s in sections], "gaps": gaps}
    head = provider.narrate(f"Summarise case {case.case_number}", facts, head)

    score = 0.8 if incidents and journey and journey["sightings"] else 0.5
    return AISummaryResponse(
        subject_kind="case", subject_id=case.id, subject_ref=case.case_number,
        provider=provider.name, headline=head, sections=sections, investigation_gaps=gaps,
        confidence_level=level_from_score(score), generated_at=datetime.utcnow(),
    )
