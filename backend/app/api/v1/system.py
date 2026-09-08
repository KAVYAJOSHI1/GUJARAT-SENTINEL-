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
from app.services.system_metrics import system_metrics_summary

router = APIRouter()


@router.get("/metrics/summary")
def metrics_summary(
    window_hours: int = Query(default=24, ge=1, le=24 * 7),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
):
    return system_metrics_summary(db, window_hours=window_hours)
