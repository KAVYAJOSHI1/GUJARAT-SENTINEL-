"""
Dashboard summary API — GET /api/v1/dashboard/stats

Small aggregate counts for the command-center header strip. Every number is
a live DB query; nothing is mocked.
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlmodel import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.alert import Alert
from app.models.base import AlertStatus, CameraStatus
from app.models.camera import Camera
from app.models.vehicle_event import VehicleEvent

router = APIRouter()


@router.get("/stats")
def dashboard_stats(db: Session = Depends(get_db), _=Depends(get_current_user)):
    total_cameras = db.execute(select(func.count(Camera.id))).scalar() or 0
    online_feeds = (
        db.execute(
            select(func.count(Camera.id)).where(Camera.status == CameraStatus.ONLINE)
        ).scalar()
        or 0
    )
    active_alerts = (
        db.execute(
            select(func.count(Alert.id)).where(Alert.status == AlertStatus.NEW)
        ).scalar()
        or 0
    )

    day_ago = datetime.utcnow() - timedelta(hours=24)
    hour_ago = datetime.utcnow() - timedelta(hours=1)
    todays_detections = (
        db.execute(
            select(func.count(VehicleEvent.id)).where(VehicleEvent.created_at >= day_ago)
        ).scalar()
        or 0
    )
    reads_last_hour = (
        db.execute(
            select(func.count(VehicleEvent.id))
            .where(VehicleEvent.created_at >= hour_ago)
            .where(VehicleEvent.plate_number_normalized != "UNKNOWN")
        ).scalar()
        or 0
    )
    zones_online = (
        db.execute(
            select(func.count(func.distinct(Camera.location_desc))).where(
                Camera.status == CameraStatus.ONLINE
            )
        ).scalar()
        or 0
    )

    return {
        "total_cameras": total_cameras,
        "online_feeds": online_feeds,
        "active_alerts": active_alerts,
        "todays_detections": todays_detections,
        "anpr_reads_per_hour": reads_last_hour,
        "zones_online": zones_online,
    }
