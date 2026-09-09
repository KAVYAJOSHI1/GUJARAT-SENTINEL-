"""
System observability API (Phase 15G).

  GET /api/v1/system/metrics/summary

One lightweight consolidated snapshot (pipeline + ANPR + detections + open
work + cameras). JWT-authenticated, read-only, bounded.
"""
from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.schemas.auth import CurrentUser
from app.services.capacity import system_capacity
from app.services.system_metrics import system_metrics_summary

router = APIRouter()


@router.get("/metrics/summary")
def metrics_summary(
    window_hours: int = Query(default=24, ge=1, le=24 * 7),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
):
    return system_metrics_summary(db, window_hours=window_hours)


@router.get("/capacity")
def capacity(
    target_cameras: int = Query(default=80_000, ge=1, le=1_000_000),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
):
    """Phase 17 Step 11. Read-only; composed from the latest pipeline
    status push, a live camera count, and a committed benchmark summary
    (see app/services/capacity.py). Never claims 80,000-camera support --
    it returns a transparent calculation from a measured or explicitly
    assumption-labeled baseline."""
    return system_capacity(db, target_cameras=target_cameras)
