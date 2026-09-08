"""
Traffic Intelligence API (Phase 14 §4, §5, §10).

  GET /analytics/traffic/overview     volume · peak hour · trend · congestion · type mix · top cameras
  GET /analytics/traffic/cameras      per-camera breakdown
  GET /analytics/traffic/trends       hourly / daily time series
  GET /analytics/traffic/heatmap      GIS density (geolocated cameras only)

All read-only, JWT-authenticated, bounded. Every figure is a live SQL
aggregate over existing rows -- video is never re-processed.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.schemas.auth import CurrentUser
from app.schemas.traffic import (
    TrafficByCamera,
    TrafficHeatmap,
    TrafficOverview,
    TrafficTrends,
)
from app.services.ai.traffic import TrafficAnalyticsService, TrafficFilters

router = APIRouter()


def _filters(
    date_from: datetime | None,
    date_to: datetime | None,
    camera_code: list[str] | None,
    vehicle_type: str | None,
    zone: str | None,
) -> TrafficFilters:
    return TrafficFilters(
        date_from=date_from, date_to=date_to,
        camera_codes=camera_code, vehicle_type=vehicle_type, zone=zone,
    )


@router.get("/overview", response_model=TrafficOverview)
def traffic_overview(
    window_hours: int = Query(default=24, ge=1, le=24 * 90),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    camera_code: list[str] | None = Query(default=None),
    vehicle_type: str | None = None,
    zone: str | None = None,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
):
    f = _filters(date_from, date_to, camera_code, vehicle_type, zone)
    return TrafficOverview(**TrafficAnalyticsService(db).overview(f, default_hours=window_hours))


@router.get("/cameras", response_model=TrafficByCamera)
def traffic_by_camera(
    window_hours: int = Query(default=24, ge=1, le=24 * 90),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    camera_code: list[str] | None = Query(default=None),
    vehicle_type: str | None = None,
    zone: str | None = None,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
):
    f = _filters(date_from, date_to, camera_code, vehicle_type, zone)
    return TrafficByCamera(**TrafficAnalyticsService(db).by_camera(f, default_hours=window_hours))


@router.get("/trends", response_model=TrafficTrends)
def traffic_trends(
    window_hours: int = Query(default=24, ge=1, le=24 * 90),
    bucket: str = Query(default="hour", pattern="^(hour|day)$"),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    camera_code: list[str] | None = Query(default=None),
    vehicle_type: str | None = None,
    zone: str | None = None,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
):
    f = _filters(date_from, date_to, camera_code, vehicle_type, zone)
    return TrafficTrends(
        **TrafficAnalyticsService(db).trends(f, bucket=bucket, default_hours=window_hours)
    )


@router.get("/heatmap", response_model=TrafficHeatmap)
def traffic_heatmap(
    kind: str = Query(
        default="vehicle_density",
        pattern="^(vehicle_density|alert_density|anomaly_density|incident_density)$",
    ),
    window_hours: int = Query(default=24, ge=1, le=24 * 90),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    camera_code: list[str] | None = Query(default=None),
    vehicle_type: str | None = None,
    zone: str | None = None,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
):
    f = _filters(date_from, date_to, camera_code, vehicle_type, zone)
    return TrafficHeatmap(
        **TrafficAnalyticsService(db).heatmap(f, kind=kind, default_hours=window_hours)
    )
