"""
Vehicle Search & Trajectory API — GET /api/v1/vehicles/search?plate={plate}
Returns chronologically ordered sightings using the composite B-Tree index
on (plate_number_normalized, timestamp). Target: <50ms for 100k+ rows.
"""
from fastapi import APIRouter, Depends, Query
from geoalchemy2.functions import ST_X, ST_Y
from sqlalchemy import select
from sqlmodel import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.camera import Camera
from app.models.vehicle_event import VehicleEvent
from app.models.watchlist import Watchlist
from app.schemas.vehicle import VehicleHistoryResponse, VehicleSighting
from app.services.plate_utils import normalize_plate

router = APIRouter()


@router.get("/search", response_model=VehicleHistoryResponse)
def search_vehicle(
    plate: str = Query(..., min_length=2, description="Registration plate to search, e.g. GJ01AB1234"),
    limit: int = Query(default=200, le=1000),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    plate_normalized = normalize_plate(plate)

    stmt = (
        select(
            VehicleEvent,
            Camera.name,
            Camera.code,
            ST_Y(Camera.location),
            ST_X(Camera.location),
        )
        .join(Camera, Camera.id == VehicleEvent.camera_id, isouter=True)
        .where(VehicleEvent.plate_number_normalized == plate_normalized)
        .order_by(VehicleEvent.timestamp.asc())
        .limit(limit)
    )
    rows = db.execute(stmt).all()

    sightings = [
        VehicleSighting(
            event_id=ev.id,
            camera_id=ev.camera_id,
            camera_code=camera_code,
            camera_name=camera_name,
            timestamp=ev.timestamp,
            # prefer the event's own fix; fall back to the camera's location
            latitude=ev.latitude if ev.latitude is not None else cam_lat,
            longitude=ev.longitude if ev.longitude is not None else cam_lon,
            snapshot_url=ev.snapshot_url,
            confidence_score=ev.confidence_score,
            track_id=ev.track_id,
        )
        for ev, camera_name, camera_code, cam_lat, cam_lon in rows
    ]

    is_watchlisted = (
        db.execute(
            select(Watchlist.id)
            .where(Watchlist.plate_number_normalized == plate_normalized)
            .where(Watchlist.active.is_(True))
            .limit(1)
        ).first()
        is not None
    )

    return VehicleHistoryResponse(
        plate_number=plate_normalized,
        total_sightings=len(sightings),
        is_watchlisted=is_watchlisted,
        sightings=sightings,
    )
