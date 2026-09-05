"""Alerts API — list recent alerts and acknowledge/resolve them."""
from fastapi import APIRouter, Depends, Query
from geoalchemy2.functions import ST_X, ST_Y
from sqlalchemy import select
from sqlmodel import Session

from app.api.deps import get_current_user
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.alert import Alert
from app.models.camera import Camera
from app.schemas.alert import AlertAcknowledge, AlertRead
from app.schemas.auth import CurrentUser
from app.services.audit import record_audit

router = APIRouter()


def _to_alert_read(a: Alert, code=None, name=None, location_desc=None, lat=None, lon=None) -> AlertRead:
    return AlertRead(
        id=a.id,
        plate_number=a.plate_number,
        plate_number_normalized=a.plate_number_normalized,
        camera_id=a.camera_id,
        camera_code=code,
        camera_name=name,
        location_desc=location_desc,
        latitude=lat,
        longitude=lon,
        vehicle_event_id=a.vehicle_event_id,
        watchlist_id=a.watchlist_id,
        priority_level=a.priority_level,
        status=a.status,
        snapshot_url=a.snapshot_url,
        created_at=a.created_at,
    )


def _camera_lookup(db: Session, camera_id: str):
    """(code, name, location_desc, lat, lon) for one camera, or all-None if
    it's since been removed. Shared by list/acknowledge so both return the
    identical AlertRead shape -- no route-specific contract drift."""
    row = db.execute(
        select(Camera.code, Camera.name, Camera.location_desc, ST_Y(Camera.location), ST_X(Camera.location)).where(
            Camera.id == camera_id
        )
    ).first()
    return row or (None, None, None, None, None)


@router.get("", response_model=list[AlertRead])
def list_alerts(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    # Joined with Camera (same pattern as vehicles.py) so the incident UI can
    # show the human camera code/name/location instead of a bare UUID.
    stmt = (
        select(Alert, Camera.code, Camera.name, Camera.location_desc, ST_Y(Camera.location), ST_X(Camera.location))
        .join(Camera, Camera.id == Alert.camera_id, isouter=True)
        .order_by(Alert.created_at.desc())
        .limit(limit)
    )
    if status_filter:
        stmt = stmt.where(Alert.status == status_filter)
    rows = db.execute(stmt).all()
    return [_to_alert_read(a, code, name, location_desc, lat, lon) for a, code, name, location_desc, lat, lon in rows]


@router.patch("/{alert_id}", response_model=AlertRead)
def acknowledge_alert(
    alert_id: str,
    payload: AlertAcknowledge,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise NotFoundError("Alert", alert_id)
    alert.status = payload.status
    alert.acknowledged_by_user_id = user.id
    db.add(alert)
    db.commit()
    db.refresh(alert)
    record_audit(
        db,
        action="ALERT_ACKNOWLEDGED",
        user_id=user.id,
        resource="alert",
        resource_id=alert.id,
        detail={"status": alert.status.value, "plate": alert.plate_number_normalized},
    )
    code, name, location_desc, lat, lon = _camera_lookup(db, alert.camera_id)
    return _to_alert_read(alert, code, name, location_desc, lat, lon)
