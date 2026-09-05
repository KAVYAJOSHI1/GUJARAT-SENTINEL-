"""
Vehicle-intelligence analytics — GET /api/v1/analytics/overview

Live aggregates over the real vehicle_events / alerts tables for the
command-centre "Vehicle Intelligence" panel:
  * detections by vehicle type (all-time)
  * detections by camera (windowed, top N)
  * top observed plates (windowed, top N, UNKNOWN excluded)
  * recent activity (hourly buckets over the window)
  * watchlist matches (total + windowed) and active alerts

Nothing is mocked. An empty database returns zeros / empty lists.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlmodel import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.alert import Alert
from app.models.base import AlertStatus
from app.models.camera import Camera
from app.models.vehicle_event import VehicleEvent
from app.schemas.analytics import AnalyticsOverview, HourBucket, LabelCount

router = APIRouter()

_UNKNOWN = "UNKNOWN"


@router.get("/overview", response_model=AnalyticsOverview)
def analytics_overview(
    window_hours: int = Query(default=24, ge=1, le=24 * 30),
    top: int = Query(default=8, ge=1, le=50),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=window_hours)

    total_events = db.execute(select(func.count(VehicleEvent.id))).scalar() or 0

    in_window = select(func.count(VehicleEvent.id)).where(
        VehicleEvent.timestamp >= window_start
    )
    total_events_in_window = db.execute(in_window).scalar() or 0
    readable_in_window = (
        db.execute(
            in_window.where(VehicleEvent.plate_number_normalized != _UNKNOWN)
        ).scalar()
        or 0
    )
    unknown_in_window = total_events_in_window - readable_in_window
    distinct_plates_in_window = (
        db.execute(
            select(func.count(func.distinct(VehicleEvent.plate_number_normalized)))
            .where(VehicleEvent.timestamp >= window_start)
            .where(VehicleEvent.plate_number_normalized != _UNKNOWN)
        ).scalar()
        or 0
    )

    # detections by vehicle type -- all-time (a stable distribution; the
    # windowed version would be noisy on a fresh DB). NULL type -> "unclassified".
    by_type_rows = db.execute(
        select(VehicleEvent.vehicle_type, func.count(VehicleEvent.id))
        .group_by(VehicleEvent.vehicle_type)
        .order_by(func.count(VehicleEvent.id).desc())
    ).all()
    detections_by_type = [
        LabelCount(label=(vt or "unclassified"), count=int(c)) for vt, c in by_type_rows
    ]

    # detections by camera -- windowed, top N, with the human camera name
    by_cam_rows = db.execute(
        select(
            VehicleEvent.camera_code,
            Camera.name,
            func.count(VehicleEvent.id),
        )
        .join(Camera, Camera.id == VehicleEvent.camera_id, isouter=True)
        .where(VehicleEvent.timestamp >= window_start)
        .group_by(VehicleEvent.camera_code, Camera.name)
        .order_by(func.count(VehicleEvent.id).desc())
        .limit(top)
    ).all()
    detections_by_camera = [
        LabelCount(label=(code or "unknown"), count=int(c), detail=name)
        for code, name, c in by_cam_rows
    ]

    # top observed plates -- windowed, top N, UNKNOWN excluded
    top_plate_rows = db.execute(
        select(
            VehicleEvent.plate_number_normalized,
            func.count(VehicleEvent.id),
        )
        .where(VehicleEvent.timestamp >= window_start)
        .where(VehicleEvent.plate_number_normalized != _UNKNOWN)
        .group_by(VehicleEvent.plate_number_normalized)
        .order_by(func.count(VehicleEvent.id).desc())
        .limit(top)
    ).all()
    top_plates = [LabelCount(label=p, count=int(c)) for p, c in top_plate_rows]

    # recent activity -- hourly buckets over the window
    _hour = func.date_trunc("hour", VehicleEvent.timestamp)
    bucket_rows = db.execute(
        select(_hour, func.count(VehicleEvent.id))
        .where(VehicleEvent.timestamp >= window_start)
        .group_by(_hour)
        .order_by(_hour)
    ).all()
    recent_activity_by_hour = [
        HourBucket(
            hour=(h.astimezone(timezone.utc) if h.tzinfo else h.replace(tzinfo=timezone.utc))
            .strftime("%Y-%m-%dT%H:00Z"),
            count=int(c),
        )
        for h, c in bucket_rows
    ]

    watchlist_matches_total = db.execute(select(func.count(Alert.id))).scalar() or 0
    watchlist_matches_in_window = (
        db.execute(
            select(func.count(Alert.id)).where(Alert.created_at >= window_start)
        ).scalar()
        or 0
    )
    active_alerts = (
        db.execute(
            select(func.count(Alert.id)).where(Alert.status == AlertStatus.NEW)
        ).scalar()
        or 0
    )

    return AnalyticsOverview(
        generated_at=now,
        window_hours=window_hours,
        total_events=total_events,
        total_events_in_window=total_events_in_window,
        readable_reads_in_window=readable_in_window,
        unknown_reads_in_window=unknown_in_window,
        distinct_plates_in_window=distinct_plates_in_window,
        detections_by_type=detections_by_type,
        detections_by_camera=detections_by_camera,
        top_plates=top_plates,
        recent_activity_by_hour=recent_activity_by_hour,
        watchlist_matches_total=watchlist_matches_total,
        watchlist_matches_in_window=watchlist_matches_in_window,
        active_alerts=active_alerts,
    )
