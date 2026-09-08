"""
Camera Reliability Intelligence API (Phase 14 §9, §10).

  GET /ai/camera-intelligence              all cameras, ranked worst-first
  GET /ai/camera-intelligence/{code}       one camera + its transition history

Read-only, JWT-authenticated, bounded. Statistics over
camera_health_history -- NOT failure prediction.
"""
from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.api.deps import get_current_user
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.schemas.auth import CurrentUser
from app.schemas.camera_intel import CameraIntelligenceResponse, CameraReliability
from app.services.ai.camera_reliability import CameraReliabilityService

router = APIRouter()


@router.get("", response_model=CameraIntelligenceResponse)
def camera_intelligence(
    window_hours: int = Query(default=24, ge=1, le=24 * 30),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
):
    return CameraIntelligenceResponse(
        **CameraReliabilityService(db).assess_all(window_hours=window_hours)
    )


@router.get("/{camera_code}", response_model=CameraReliability)
def camera_intelligence_one(
    camera_code: str,
    window_hours: int = Query(default=24, ge=1, le=24 * 30),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
):
    result = CameraReliabilityService(db).assess_one(camera_code, window_hours=window_hours)
    if result is None:
        raise NotFoundError("Camera", camera_code)
    return CameraReliability(**result)
