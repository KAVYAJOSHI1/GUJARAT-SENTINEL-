"""
Cross-camera correlation + camera transition intelligence API
(Phase 14 §2, §3, §10).

  POST /ai/correlation/analyze                 explain one hop, or every hop for a plate
  GET  /ai/correlation/transitions             list camera_transition_stats
  GET  /ai/correlation/transitions/{code}      likely next / previous cameras
  POST /ai/correlation/transitions/recompute   rebuild the stats (ADMIN/OFFICER)

JWT-authenticated + bounded. analyze / list are read-only for any auth user;
recompute mutates and requires ADMIN/OFFICER. analyze is audited.
"""
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import or_, select
from sqlmodel import Session

from app.api.deps import get_current_user
from app.core.exceptions import NotFoundError, SentinelException
from app.core.rbac import require_roles
from app.database import get_db
from app.models.base import UserRole
from app.models.camera import Camera
from app.models.camera_transition_stat import CameraTransitionStat
from app.models.vehicle_event import VehicleEvent
from app.schemas.auth import CurrentUser
from app.schemas.correlation import (
    CameraTransitionNeighbours,
    CameraTransitionStatRead,
    CorrelationBreakdown,
    CorrelationJourneyResponse,
    CorrelationRequest,
    TransitionRecomputeResponse,
)
from app.services.ai.camera_transitions import CameraTransitionService
from app.services.ai.correlation import VehicleCorrelationService
from app.services.audit import client_ip, record_audit
from app.services.plate_utils import normalize_plate

router = APIRouter()

_MANAGE = require_roles(UserRole.ADMIN, UserRole.OFFICER)


@router.post("/analyze")
def analyze(
    body: CorrelationRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    svc = VehicleCorrelationService(db)
    if body.event_id_a and body.event_id_b:
        result = svc.analyze_pair(body.event_id_a, body.event_id_b)
        if result is None:
            raise NotFoundError("VehicleEvent", f"{body.event_id_a} / {body.event_id_b}")
        record_audit(
            db, action="AI_CORRELATION_ANALYZE", user_id=user.id, resource="vehicle_event",
            resource_id=body.event_id_a, ip_address=client_ip(request),
            detail={"verdict": result["verdict"], "overall": result["overall_score"]},
        )
        return CorrelationBreakdown(**result)

    if body.plate:
        norm = normalize_plate(body.plate)
        result = svc.analyze_plate_journey(norm, limit=body.limit)
        record_audit(
            db, action="AI_CORRELATION_ANALYZE", user_id=user.id, resource="vehicle",
            resource_id=norm, ip_address=client_ip(request),
            detail={"hops": result["hops_analyzed"], "confirmed": result["confirmed"]},
        )
        return CorrelationJourneyResponse(**result)

    raise SentinelException("VALIDATION_ERROR", "Provide event_id_a+event_id_b or plate.", 400)


@router.get("/transitions", response_model=list[CameraTransitionStatRead])
def list_transitions(
    camera_code: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
):
    stmt = select(CameraTransitionStat).order_by(CameraTransitionStat.sample_count.desc())
    if camera_code:
        stmt = stmt.where(
            or_(
                CameraTransitionStat.from_camera_code == camera_code,
                CameraTransitionStat.to_camera_code == camera_code,
            )
        )
    rows = db.execute(stmt.limit(limit)).scalars().all()
    return [CameraTransitionStatRead.model_validate(r) for r in rows]


@router.get("/transitions/{camera_code}/neighbours", response_model=CameraTransitionNeighbours)
def transition_neighbours(
    camera_code: str,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
):
    cam = db.execute(select(Camera).where(Camera.code == camera_code)).scalar_one_or_none()
    if cam is None:
        raise NotFoundError("Camera", camera_code)
    svc = CameraTransitionService(db)
    return CameraTransitionNeighbours(
        camera_id=cam.id,
        camera_code=cam.code,
        likely_next=svc.likely_next_cameras(cam.id),
        likely_previous=svc.likely_previous_cameras(cam.id),
    )


@router.post("/transitions/recompute", response_model=TransitionRecomputeResponse)
def recompute_transitions(
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(_MANAGE),
):
    result = CameraTransitionService(db).recompute()
    record_audit(
        db, action="AI_TRANSITION_RECOMPUTE", user_id=user.id,
        resource="camera_transition_stats", ip_address=client_ip(request), detail=result,
    )
    return TransitionRecomputeResponse(**result)
