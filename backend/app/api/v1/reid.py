"""
Vehicle Visual Re-ID API (Phase 14 §1, §10).

  POST /ai/reid/search              rank appearance-similar sightings (bounded)
  POST /ai/reid/compare             cosine similarity of two sightings
  GET  /ai/reid/embedding/{eid}     stored embedding metadata for one sighting
  POST /ai/reid/backfill            index events with no embedding (ADMIN/OFFICER)

All endpoints are JWT-authenticated + bounded. Search/compare are read-only
for any authenticated user; backfill mutates and requires ADMIN/OFFICER.
Search + backfill are audited.

Visual similarity is NOT identity -- every response carries a disclaimer and
capped confidence unless a deterministic plate match is also present.
"""
from fastapi import APIRouter, Depends, Request

from app.api.deps import get_current_user
from app.core.exceptions import NotFoundError, SentinelException
from app.core.rbac import require_roles
from app.database import get_db
from app.models.base import UserRole
from app.models.vehicle_embedding import VehicleEmbedding
from app.models.vehicle_event import VehicleEvent
from app.schemas.auth import CurrentUser
from app.schemas.reid import (
    EmbeddingInfo,
    ReIDBackfillResponse,
    ReIDCompareRequest,
    ReIDCompareResponse,
    ReIDSearchRequest,
    ReIDSearchResponse,
)
from app.services.ai.reid import VehicleReIDService
from app.services.audit import client_ip, record_audit
from app.services.plate_utils import normalize_plate
from sqlalchemy import select
from sqlmodel import Session

router = APIRouter()

_MANAGE = require_roles(UserRole.ADMIN, UserRole.OFFICER)


def _resolve_query_event(db: Session, body: ReIDSearchRequest) -> str:
    if body.event_id:
        if not db.get(VehicleEvent, body.event_id):
            raise NotFoundError("VehicleEvent", body.event_id)
        return body.event_id
    if body.plate:
        norm = normalize_plate(body.plate)
        ev = db.execute(
            select(VehicleEvent)
            .where(VehicleEvent.plate_number_normalized == norm)
            .order_by(VehicleEvent.timestamp.desc())
            .limit(1)
        ).scalar_one_or_none()
        if not ev:
            raise NotFoundError("VehicleEvent for plate", norm)
        return ev.id
    raise SentinelException("VALIDATION_ERROR", "Provide either event_id or plate.", 400)


@router.post("/search", response_model=ReIDSearchResponse)
def reid_search(
    body: ReIDSearchRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    event_id = _resolve_query_event(db, body)
    svc = VehicleReIDService(db)
    result = svc.find_similar(
        event_id=event_id,
        limit=body.limit,
        time_window_hours=body.time_window_hours,
        exclude_same_plate=body.exclude_same_plate,
        exclude_same_camera=body.exclude_same_camera,
        min_similarity=body.min_similarity,
    )
    record_audit(
        db, action="AI_REID_SEARCH", user_id=user.id, resource="vehicle_event",
        resource_id=event_id, ip_address=client_ip(request),
        detail={"plate": result.get("query_plate"), "returned": result.get("returned")},
    )
    return ReIDSearchResponse(**result)


@router.post("/compare", response_model=ReIDCompareResponse)
def reid_compare(
    body: ReIDCompareRequest,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
):
    result = VehicleReIDService(db).compare(body.event_id_a, body.event_id_b)
    if result is None:
        raise NotFoundError("VehicleEvent", f"{body.event_id_a} / {body.event_id_b}")
    return ReIDCompareResponse(**result)


@router.get("/embedding/{event_id}", response_model=EmbeddingInfo)
def reid_embedding(
    event_id: str,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
):
    row = db.execute(
        select(VehicleEmbedding).where(VehicleEmbedding.vehicle_event_id == event_id)
    ).scalar_one_or_none()
    if row is None:
        # index on demand if the event exists
        ev = db.get(VehicleEvent, event_id)
        if ev is None:
            raise NotFoundError("VehicleEvent", event_id)
        row = VehicleReIDService(db).index_event(ev)
    return EmbeddingInfo(
        vehicle_event_id=row.vehicle_event_id,
        plate_number_normalized=row.plate_number_normalized,
        camera_code=row.camera_code,
        timestamp=row.timestamp,
        vehicle_type=row.vehicle_type,
        vehicle_color=row.vehicle_color,
        dim=row.dim,
        model_name=row.model_name,
        source=row.source,
    )


@router.post("/backfill", response_model=ReIDBackfillResponse)
def reid_backfill(
    request: Request,
    limit: int | None = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(_MANAGE),
):
    result = VehicleReIDService(db).backfill(limit=limit)
    record_audit(
        db, action="AI_REID_BACKFILL", user_id=user.id, resource="vehicle_embeddings",
        ip_address=client_ip(request), detail=result,
    )
    return ReIDBackfillResponse(**result)
