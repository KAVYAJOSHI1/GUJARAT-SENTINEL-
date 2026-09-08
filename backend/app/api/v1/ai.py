"""
AI intelligence layer API (phase brief §1-5, §8, §9).

  POST /ai/investigate               Investigation Copilot (NL question)
  POST /ai/search                    NL -> existing Advanced Search
  POST /ai/incidents/{id}/summary    AI incident summary
  POST /ai/cases/{id}/summary        AI case summary
  GET  /ai/anomalies                 list stopped-vehicle anomalies
  POST /ai/anomalies/scan            run the detector over recorded events (ADMIN/OFFICER)
  POST /ai/anomalies/{id}/review     mark reviewed / dismissed (ADMIN/OFFICER)
  GET  /ai/suggestions               suggested questions for the UI
  GET  /ai/status                    provider + config (so the UI shows "deterministic" mode)

Every endpoint is JWT-authenticated. Copilot / search / summaries are
read-only for any authenticated user; the anomaly scan + review require
ADMIN/OFFICER. Important actions are audited.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.concurrency import run_in_threadpool
from geoalchemy2.functions import ST_X, ST_Y
from sqlalchemy import func, or_, select
from sqlmodel import Session

from app.api.deps import get_current_user
from app.api.v1._enrich import resolve_usernames
from app.core.exceptions import NotFoundError
from app.core.rbac import require_roles
from app.config import settings
from app.database import get_db
from app.models.anomaly_event import AnomalyEvent
from app.models.base import AnomalyStatus, UserRole
from app.models.camera import Camera
from app.models.case import Case
from app.models.incident import Incident
from app.schemas.ai import (
    AISearchRequest,
    AISearchResponse,
    AIStatus,
    AISummaryResponse,
    AnomalyEventRead,
    AnomalyPage,
    AnomalyReviewRequest,
    AnomalyScanRequest,
    AnomalyScanResult,
    CopilotRequest,
    CopilotResponse,
)
from app.schemas.auth import CurrentUser
from app.services.ai.behavior import BehaviorAnalyticsService
from app.services.ai.copilot import InvestigationCopilotService
from app.services.ai.llm import get_llm_provider
from app.services.ai.nlq import parse_query
from app.services.ai.summary import build_case_summary, build_incident_summary
from app.services.alert_dispatcher import connection_manager
from app.services.audit import client_ip, record_audit

router = APIRouter()

_MANAGE = require_roles(UserRole.ADMIN, UserRole.OFFICER)

SUGGESTED_QUESTIONS = [
    "Where was GJ18TC0450 seen?",
    "Where was GJ18TC0450 seen in the last 6 hours?",
    "Show the journey of GJ18TC0450.",
    "Which cameras detected GJ18TC0450?",
    "Show watchlist vehicles detected today.",
    "Show vehicles detected near CAM-04 after 9 PM.",
    "Show all alerts related to GJ18TC0450.",
    "Which incidents are associated with GJ18TC0450?",
    "Show white cars detected between 8 PM and 10 PM.",
    "Show vehicles detected for more than 5 minutes.",
]


@router.get("/status", response_model=AIStatus)
def ai_status(_: CurrentUser = Depends(get_current_user)):
    p = get_llm_provider()
    return AIStatus(
        provider=p.name,
        llm_available=p.name != "deterministic" and p.available,
        anomaly_scan_enabled=settings.AI_ANOMALY_SCAN_ENABLED,
        anomaly_thresholds={
            "min_seconds": settings.ANOMALY_STOPPED_MIN_SECONDS,
            "min_detections": settings.ANOMALY_STOPPED_MIN_DETECTIONS,
            "max_displacement_m": settings.ANOMALY_STOPPED_MAX_DISPLACEMENT_M,
        },
        max_results=settings.AI_MAX_RESULTS,
    )


@router.get("/suggestions", response_model=list[str])
def ai_suggestions(_: CurrentUser = Depends(get_current_user)):
    return SUGGESTED_QUESTIONS


@router.post("/investigate", response_model=CopilotResponse)
def ai_investigate(
    payload: CopilotRequest,
    request: Request,
    plate: str | None = Query(default=None, description="page-context plate for 'this vehicle'"),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    resp = InvestigationCopilotService(db).investigate(payload.query, context_plate=plate)
    record_audit(
        db, action="AI_INVESTIGATION", user_id=user.id, resource="ai", ip_address=client_ip(request),
        detail={"intent": resp.intent, "results": resp.result_count,
                "provider": resp.provider, "confidence": resp.confidence_level.value},
    )
    return resp


@router.post("/search", response_model=AISearchResponse)
def ai_search(
    payload: AISearchRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """Natural language -> the EXISTING Advanced Search (POST /search/vehicles).
    The generated structured filters are returned so the officer sees exactly
    what the AI ran."""
    from app.api.v1.search import execute_vehicle_search
    from app.schemas.search import VehicleSearchQuery

    parsed = parse_query(payload.query)
    q = VehicleSearchQuery(
        plate=parsed.plate,
        vehicle_type=parsed.vehicle_type,
        vehicle_color=parsed.vehicle_color,
        camera_code=parsed.camera_codes[0] if parsed.camera_codes else None,
        date_from=parsed.date_from, date_to=parsed.date_to,
        time_from=parsed.time_from, time_to=parsed.time_to,
        unknown_only=parsed.unknown_only,
        min_duration_seconds=parsed.min_duration_seconds,
        watchlist_only=parsed.watchlist_only,
        sort="latest", limit=payload.limit, offset=payload.offset,
    )
    search = execute_vehicle_search(db, q)
    record_audit(
        db, action="AI_SEARCH", user_id=user.id, resource="vehicle_events",
        ip_address=client_ip(request),
        detail={"total": search.total, "returned": len(search.items),
                "filters": q.model_dump(exclude_none=True, exclude_defaults=True)},
    )
    limitations = list(parsed.notes)
    if parsed.camera_codes and len(parsed.camera_codes) > 1:
        limitations.append(f"multiple cameras parsed; searched only {q.camera_code}")
    return AISearchResponse(
        query=payload.query, parsed=parsed,
        filters=q.model_dump(exclude_none=True, exclude_defaults=True),
        search=search, limitations=limitations,
    )


@router.post("/incidents/{incident_id}/summary", response_model=AISummaryResponse)
def ai_incident_summary(
    incident_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    inc = db.get(Incident, incident_id)
    if inc is None:
        raise NotFoundError("Incident", incident_id)
    summ = build_incident_summary(db, inc)
    record_audit(
        db, action="AI_INCIDENT_SUMMARY", user_id=user.id, resource="incident",
        resource_id=incident_id, ip_address=client_ip(request),
        detail={"provider": summ.provider, "gaps": len(summ.investigation_gaps)},
    )
    return summ


@router.post("/cases/{case_id}/summary", response_model=AISummaryResponse)
def ai_case_summary(
    case_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    c = db.get(Case, case_id)
    if c is None:
        raise NotFoundError("Case", case_id)
    summ = build_case_summary(db, c)
    record_audit(
        db, action="AI_CASE_SUMMARY", user_id=user.id, resource="case", resource_id=case_id,
        ip_address=client_ip(request), detail={"provider": summ.provider},
    )
    return summ


# --------------------------------------------------------------------------- #
#  Anomaly events                                                             #
# --------------------------------------------------------------------------- #
def _anomaly_read(a: AnomalyEvent, cam: dict, usernames: dict) -> AnomalyEventRead:
    return AnomalyEventRead(
        id=a.id, kind=a.kind, camera_id=a.camera_id, camera_code=a.camera_code,
        camera_name=cam.get("name"), location_desc=cam.get("loc"),
        plate_number_normalized=a.plate_number_normalized, track_id=a.track_id,
        first_seen=a.first_seen, last_seen=a.last_seen, duration_seconds=a.duration_seconds,
        detection_count=a.detection_count, displacement_meters=a.displacement_meters,
        confidence_score=a.confidence_score, confidence_level=a.confidence_level,
        reasoning=a.reasoning, evidence_event_id=a.evidence_event_id, alert_id=a.alert_id,
        zone_name=a.zone_name, direction_deg=a.direction_deg,
        expected_direction_deg=a.expected_direction_deg,
        status=a.status, reviewed_by_username=usernames.get(a.reviewed_by_user_id or ""),
        created_at=a.created_at,
    )


@router.get("/anomalies", response_model=AnomalyPage)
def list_anomalies(
    status_filter: str | None = Query(default=None, alias="status"),
    camera_code: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
):
    conds = []
    if status_filter:
        conds.append(AnomalyEvent.status == status_filter)
    if camera_code:
        conds.append(AnomalyEvent.camera_code == camera_code)
    total = db.execute(select(func.count(AnomalyEvent.id)).where(*conds)).scalar() or 0
    rows = db.execute(
        select(AnomalyEvent).where(*conds).order_by(AnomalyEvent.created_at.desc())
        .limit(limit).offset(offset)
    ).scalars().all()
    cams = {}
    if rows:
        for cid, name, loc in db.execute(
            select(Camera.id, Camera.name, Camera.location_desc)
            .where(Camera.id.in_({r.camera_id for r in rows}))
        ).all():
            cams[cid] = {"name": name, "loc": loc}
    usernames = resolve_usernames(db, [r.reviewed_by_user_id for r in rows])
    return AnomalyPage(
        items=[_anomaly_read(r, cams.get(r.camera_id, {}), usernames) for r in rows],
        total=int(total), limit=limit, offset=offset,
    )


@router.post("/anomalies/scan", response_model=AnomalyScanResult)
async def scan_anomalies(
    payload: AnomalyScanRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(_MANAGE),
):
    svc = BehaviorAnalyticsService(db)
    result = await run_in_threadpool(
        svc.scan,
        kinds=payload.kinds or None,
        lookback_hours=payload.lookback_hours,
        camera_code=payload.camera_code,
    )
    # broadcast the new ANOMALY alerts over the existing WS channel
    for a in result["anomalies"]:
        if a.alert_id:
            await connection_manager.broadcast({
                "type": "ALERT", "alert_id": a.alert_id, "source": "ANOMALY",
                "plate_number": a.plate_number_normalized or "UNKNOWN",
                "camera_code": a.camera_code, "priority_level": settings.ANOMALY_PRIORITY,
                "created_at": datetime.utcnow().isoformat(),
            })
    record_audit(
        db, action="AI_ANOMALY_SCAN", user_id=user.id, resource="anomaly",
        ip_address=client_ip(request),
        detail={"scanned": result["scanned_tracks"], "created": result["created"],
                "already_flagged": result["already_flagged"]},
    )
    cams = {}
    if result["anomalies"]:
        for cid, name, loc in db.execute(
            select(Camera.id, Camera.name, Camera.location_desc)
            .where(Camera.id.in_({a.camera_id for a in result["anomalies"]}))
        ).all():
            cams[cid] = {"name": name, "loc": loc}
    return AnomalyScanResult(
        scanned_tracks=result["scanned_tracks"], created=result["created"],
        already_flagged=result["already_flagged"],
        anomalies=[_anomaly_read(a, cams.get(a.camera_id, {}), {}) for a in result["anomalies"]],
    )


@router.post("/anomalies/{anomaly_id}/review", response_model=AnomalyEventRead)
def review_anomaly(
    anomaly_id: str,
    payload: AnomalyReviewRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(_MANAGE),
):
    a = db.get(AnomalyEvent, anomaly_id)
    if a is None:
        raise NotFoundError("Anomaly event", anomaly_id)
    a.status = payload.status
    a.reviewed_by_user_id = user.id
    a.reviewed_at = datetime.utcnow()
    db.add(a)
    db.commit()
    db.refresh(a)
    record_audit(
        db, action="AI_ANOMALY_REVIEW", user_id=user.id, resource="anomaly", resource_id=a.id,
        ip_address=client_ip(request), detail={"status": a.status.value},
    )
    cam = db.execute(
        select(Camera.name, Camera.location_desc).where(Camera.id == a.camera_id)
    ).first()
    return _anomaly_read(a, {"name": cam[0], "loc": cam[1]} if cam else {},
                         {user.id: user.username})
