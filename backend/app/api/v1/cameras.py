"""
Camera Registry API — /api/v1/cameras
CRUD endpoints plus a PostGIS-backed GeoJSON FeatureCollection endpoint
for map rendering (consumed by Isha/Vishakha's frontend).
"""
from fastapi import APIRouter, Depends, status
from geoalchemy2.functions import ST_X, ST_Y
from sqlalchemy import select
from sqlmodel import Session

from app.api.deps import get_current_user
from app.core.exceptions import NotFoundError
from app.core.rbac import require_roles
from app.database import get_db
from app.models.base import UserRole
from app.models.camera import Camera
from app.schemas.camera import (
    CameraCreate,
    CameraUpdate,
    CameraRead,
    CameraRegistryEntry,
    CameraSyncResult,
    GeoJSONFeature,
    GeoJSONFeatureCollection,
    GeoJSONPointGeometry,
)
from app.services.camera_resolver import upsert_camera_from_registry

router = APIRouter()


def _to_camera_read(camera: Camera, lon: float | None, lat: float | None) -> CameraRead:
    return CameraRead(
        id=camera.id,
        code=camera.code,
        name=camera.name,
        rtsp_url=camera.rtsp_url,
        location_desc=camera.location_desc,
        status=camera.status,
        latitude=lat,
        longitude=lon,
    )


def _camera_xy(db: Session, camera_id: str):
    return db.execute(
        select(ST_X(Camera.location), ST_Y(Camera.location)).where(Camera.id == camera_id)
    ).first() or (None, None)


@router.get("", response_model=list[CameraRead])
def list_cameras(db: Session = Depends(get_db), _=Depends(get_current_user)):
    stmt = select(Camera, ST_X(Camera.location), ST_Y(Camera.location))
    rows = db.execute(stmt).all()
    return [_to_camera_read(cam, lon, lat) for cam, lon, lat in rows]


@router.get("/geojson", response_model=GeoJSONFeatureCollection)
def list_cameras_geojson(db: Session = Depends(get_db), _=Depends(get_current_user)):
    """PostGIS GeoJSON FeatureCollection of all cameras, for map widgets."""
    stmt = select(Camera, ST_X(Camera.location), ST_Y(Camera.location))
    rows = db.execute(stmt).all()
    features = [
        GeoJSONFeature(
            id=cam.id,
            geometry=GeoJSONPointGeometry(coordinates=(lon, lat)),
            properties={"name": cam.name, "status": cam.status.value, "code": cam.code},
        )
        for cam, lon, lat in rows
        if lon is not None and lat is not None
    ]
    return GeoJSONFeatureCollection(features=features)


@router.post("/sync", response_model=CameraSyncResult)
def sync_camera_registry(
    entries: list[CameraRegistryEntry],
    db: Session = Depends(get_db),
    _=Depends(require_roles(UserRole.ADMIN, UserRole.OFFICER)),
):
    """Upsert a camera catalogue / registry (keyed by external ``code``).

    Feed this the contents of ``data/camera_registry.json`` (or any subset) to
    register the Sentinel cameras the AI pipeline will emit events for.
    """
    synced = []
    for entry in entries:
        cam = upsert_camera_from_registry(db, entry.model_dump(exclude_none=True))
        lon, lat = _camera_xy(db, cam.id)
        synced.append(_to_camera_read(cam, lon, lat))
    return CameraSyncResult(synced=len(synced), cameras=synced)


@router.get("/{camera_id}", response_model=CameraRead)
def get_camera(camera_id: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    stmt = select(Camera, ST_X(Camera.location), ST_Y(Camera.location)).where(
        Camera.id == camera_id
    )
    row = db.execute(stmt).first()
    if row is None:
        raise NotFoundError("Camera", camera_id)
    cam, lon, lat = row
    return _to_camera_read(cam, lon, lat)


@router.post("", response_model=CameraRead, status_code=status.HTTP_201_CREATED)
def create_camera(
    payload: CameraCreate,
    db: Session = Depends(get_db),
    _=Depends(require_roles(UserRole.ADMIN, UserRole.OFFICER)),
):
    camera = Camera(
        name=payload.name,
        code=payload.code,
        rtsp_url=payload.rtsp_url,
        location_desc=payload.location_desc,
        status=payload.status,
        location=f"SRID=4326;POINT({payload.longitude} {payload.latitude})",
    )
    db.add(camera)
    db.commit()
    db.refresh(camera)
    return _to_camera_read(camera, payload.longitude, payload.latitude)


@router.patch("/{camera_id}", response_model=CameraRead)
def update_camera(
    camera_id: str,
    payload: CameraUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_roles(UserRole.ADMIN, UserRole.OFFICER)),
):
    camera = db.get(Camera, camera_id)
    if camera is None:
        raise NotFoundError("Camera", camera_id)

    for field in ("name", "rtsp_url", "location_desc", "status"):
        value = getattr(payload, field)
        if value is not None:
            setattr(camera, field, value)

    if payload.latitude is not None and payload.longitude is not None:
        camera.location = f"SRID=4326;POINT({payload.longitude} {payload.latitude})"

    db.add(camera)
    db.commit()
    db.refresh(camera)

    stmt = select(ST_X(Camera.location), ST_Y(Camera.location)).where(Camera.id == camera_id)
    lon, lat = db.execute(stmt).first()
    return _to_camera_read(camera, lon, lat)


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_camera(
    camera_id: str,
    db: Session = Depends(get_db),
    _=Depends(require_roles(UserRole.ADMIN)),
):
    camera = db.get(Camera, camera_id)
    if camera is None:
        raise NotFoundError("Camera", camera_id)
    db.delete(camera)
    db.commit()
