"""
Camera Registry API — /api/v1/cameras
CRUD endpoints plus a PostGIS-backed GeoJSON FeatureCollection endpoint
for map rendering (consumed by Isha/Vishakha's frontend).
"""
import os

from fastapi import APIRouter, Depends, status
from fastapi.responses import FileResponse
from geoalchemy2.functions import ST_X, ST_Y
from sqlalchemy import select
from sqlmodel import Session

from app.api.deps import get_current_user, verify_bearer_header_or_query
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
from app.services.camera_resolver import find_camera, upsert_camera_from_registry

router = APIRouter()

# Where THIS process can see the trafficdataset/ clips a mock camera's
# rtsp_url points at. The DB stores the host's absolute path (written by
# scripts/generate_mock_camera_registry.py, which only ever runs on the
# host) -- in the dockerized backend that path doesn't exist, so it's
# translated against this mount instead of being read literally. Defaults to
# the repo-relative folder for a bare-metal (non-docker) backend run.
MOCK_VIDEOS_ROOT = os.getenv(
    "MOCK_VIDEOS_ROOT",
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "trafficdataset"),
)


def _resolve_mock_video_path(camera_code: str, stored_path: str):
    """Find a browser-playable file for this mock camera.

    Prefers trafficdataset/_previews/<code>.mp4 -- a lossless H.264-in-MP4
    remux scripts/generate_mock_camera_registry.py makes of the source clip
    (the raw .MOV files are QuickTime-container H.264, which most browsers
    won't play via <video> even though the codec itself is standard).
    Falls back to the raw source path if no preview was generated (e.g. the
    optional `av` dependency wasn't installed at registry-generation time).

    Also translates the stored HOST absolute path onto wherever THIS process
    can actually see the trafficdataset/ tree: the literal path first
    (bare-metal backend, same machine as the pipeline), else rewritten onto
    MOCK_VIDEOS_ROOT (dockerized backend -- see docker-compose.yml)."""
    def _translate(path: str):
        if not path:
            return None
        if os.path.isfile(path):
            return path
        marker = f"trafficdataset{os.sep}"
        idx = path.find(marker)
        if idx == -1:
            return None
        candidate = os.path.join(MOCK_VIDEOS_ROOT, path[idx + len(marker):])
        return candidate if os.path.isfile(candidate) else None

    # Already container-local by construction (built from MOCK_VIDEOS_ROOT
    # directly) -- no host-path translation needed, just check it exists.
    preview_candidate = os.path.join(MOCK_VIDEOS_ROOT, "_previews", f"{camera_code}.mp4")
    if os.path.isfile(preview_candidate):
        return preview_candidate, "video/mp4"
    raw = _translate(stored_path)
    if raw:
        return raw, ("video/quicktime" if raw.lower().endswith(".mov") else "video/mp4")
    return None, None


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


@router.get("/{camera_id}/mock-video")
def get_mock_camera_video(
    camera_id: str,
    db: Session = Depends(get_db),
    _=Depends(verify_bearer_header_or_query),
):
    """Serve the raw local clip for a MOCK_CAM* camera so the dashboard can
    show actual moving footage instead of a static thumbnail.

    Real Sentinel cameras are never served this way: their RTSP feed needs
    Basic-auth the browser can't supply and has no CORS-open HLS path (see
    frontend/src/components/CameraCard.jsx), and this route refuses anything
    whose code doesn't start with MOCK -- it only ever streams a bare local
    video file that a mock camera's own registry entry already pointed at.

    Accepts a normal Bearer token OR a ``?token=`` query param, because a
    plain <video src> can't send an Authorization header.
    """
    camera = find_camera(db, camera_id)
    if camera is None or not (camera.code or "").upper().startswith("MOCK"):
        raise NotFoundError("Mock camera video", camera_id)
    path, media_type = _resolve_mock_video_path(camera.code, camera.rtsp_url)
    if not path:
        raise NotFoundError("Mock camera video", camera_id)
    return FileResponse(path, media_type=media_type)


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
