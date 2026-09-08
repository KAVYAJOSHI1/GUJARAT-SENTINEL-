"""
Camera Registry API — /api/v1/cameras
CRUD endpoints plus a PostGIS-backed GeoJSON FeatureCollection endpoint
for map rendering (consumed by Isha/Vishakha's frontend).
"""
import os
import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, status
from fastapi.responses import FileResponse
from geoalchemy2.functions import ST_X, ST_Y
from sqlalchemy import func, select
from sqlmodel import Session

from app.api.deps import get_current_user, require_ingest_auth, verify_bearer_header_or_query
from app.core.exceptions import NotFoundError
from app.core.rbac import require_roles
from app.database import get_db
from app.models.base import CameraStatus, UserRole
from app.models.camera import Camera
from app.schemas.camera import (
    CameraCreate,
    CameraBehaviorConfig,
    CameraStreamProfile,
    CameraUpdate,
    CameraHealthEntry,
    CameraHealthPush,
    CameraHealthResult,
    CameraRead,
    CameraRegistryEntry,
    CameraSyncResult,
    GeoJSONFeature,
    GeoJSONFeatureCollection,
    GeoJSONPointGeometry,
)
from app.schemas.camera_health import CameraHealthHistoryResponse, CameraHealthHistoryRow
from app.services.audit import record_audit
from app.services.camera_health import record_transition_if_changed
from app.services.camera_resolver import find_camera, upsert_camera_from_registry
from app.services.camera_stream import CameraStreamService
from app.models.camera_health_history import CameraHealthHistory

router = APIRouter()

# A camera whose last health push is older than this is treated as OFFLINE
# regardless of the status that push last reported -- a stalled/dead
# ingestion worker must not leave a camera showing stale "ONLINE" forever.
# Several multiples of the ingestion side's default push interval (5s, see
# ingestion/config.py `health_push_interval_s`) so normal jitter/GC pauses
# never cause a flicker.
HEALTH_STALE_AFTER = timedelta(seconds=20)

_STREAM_TO_CAMERA_STATUS = {
    "ONLINE": CameraStatus.ONLINE,
    "OFFLINE": CameraStatus.OFFLINE,
    "RECONNECTING": CameraStatus.DEGRADED,
}

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

# Where THIS process can see the committed H.264 demo clips a
# data/demo_camera_registry.json entry points at (repo-relative paths like
# "demo_assets/clips/mockcam01.mp4"). Dockerized backend mounts the folder at
# a fixed path; bare-metal falls back to the repo-relative folder.
DEMO_ASSETS_ROOT = os.getenv(
    "DEMO_ASSETS_ROOT",
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "demo_assets"),
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
        # host/relative path -> whichever mount THIS process can actually see
        for marker, root in (
            (f"trafficdataset{os.sep}", MOCK_VIDEOS_ROOT),
            (f"demo_assets{os.sep}", DEMO_ASSETS_ROOT),
        ):
            idx = path.find(marker)
            if idx != -1:
                candidate = os.path.join(root, path[idx + len(marker):])
                if os.path.isfile(candidate):
                    return candidate
        return None

    # Already container-local by construction (built from MOCK_VIDEOS_ROOT
    # directly) -- no host-path translation needed, just check it exists.
    preview_candidate = os.path.join(MOCK_VIDEOS_ROOT, "_previews", f"{camera_code}.mp4")
    if os.path.isfile(preview_candidate):
        return preview_candidate, "video/mp4"
    # The committed demo clips are already browser-playable H.264/MP4 -- serve
    # the source clip directly, no preview remux needed.
    demo_candidate = os.path.join(DEMO_ASSETS_ROOT, "clips", f"{camera_code}.mp4")
    if os.path.isfile(demo_candidate):
        return demo_candidate, "video/mp4"
    raw = _translate(stored_path)
    if raw:
        return raw, ("video/quicktime" if raw.lower().endswith(".mov") else "video/mp4")
    return None, None


def _effective_status(camera: Camera) -> CameraStatus:
    """The status actually served to clients: the last real health push if
    it's still fresh, else OFFLINE (a camera that has gone quiet is not
    still "ONLINE" just because that's the last thing it ever reported --
    SENTINEL_System_Audit_Report.md §11 "dashboard camera status not wired
    to live health"). A camera that has never received a health push (e.g.
    just onboarded, or a real camera whose ingestion process isn't running
    in this environment) keeps whatever status was set at onboard/PATCH
    time -- there's no telemetry yet to override it with."""
    if camera.health_updated_at is None:
        return camera.status
    if datetime.utcnow() - camera.health_updated_at > HEALTH_STALE_AFTER:
        return CameraStatus.OFFLINE
    return camera.status


_MOCK_CODE_RE = re.compile(r"^mock[_-]?cam", re.IGNORECASE)


def _to_camera_read(
    camera: Camera, lon: float | None, lat: float | None,
    last_detection_at=None,
) -> CameraRead:
    return CameraRead(
        id=camera.id,
        code=camera.code,
        name=camera.name,
        rtsp_url=camera.rtsp_url,
        hls_url=camera.hls_url,
        webrtc_url=camera.webrtc_url,
        location_desc=camera.location_desc,
        status=_effective_status(camera),
        latitude=lat,
        longitude=lon,
        fps=camera.stream_fps,
        frame_drop_count=camera.frame_drop_count,
        reconnect_count=camera.reconnect_count,
        health_updated_at=camera.health_updated_at,
        is_mock=bool(camera.code and _MOCK_CODE_RE.match(camera.code)),
        last_detection_at=last_detection_at,
        permitted_direction_deg=camera.permitted_direction_deg,
        restricted_zones=camera.restricted_zones,
    )


def _camera_xy(db: Session, camera_id: str):
    return db.execute(
        select(ST_X(Camera.location), ST_Y(Camera.location)).where(Camera.id == camera_id)
    ).first() or (None, None)


@router.get("", response_model=list[CameraRead])
def list_cameras(db: Session = Depends(get_db), _=Depends(get_current_user)):
    from app.models.vehicle_event import VehicleEvent

    rows = db.execute(
        select(Camera, ST_X(Camera.location), ST_Y(Camera.location))
    ).all()
    # one bulk group-by for last-detection time (no N+1)
    last_by_cam = dict(
        db.execute(
            select(VehicleEvent.camera_id, func.max(VehicleEvent.timestamp))
            .group_by(VehicleEvent.camera_id)
        ).all()
    )
    return [
        _to_camera_read(cam, lon, lat, last_by_cam.get(cam.id))
        for cam, lon, lat in rows
    ]


@router.get("/geojson", response_model=GeoJSONFeatureCollection)
def list_cameras_geojson(db: Session = Depends(get_db), _=Depends(get_current_user)):
    """PostGIS GeoJSON FeatureCollection of all cameras, for map widgets."""
    stmt = select(Camera, ST_X(Camera.location), ST_Y(Camera.location))
    rows = db.execute(stmt).all()
    features = [
        GeoJSONFeature(
            id=cam.id,
            geometry=GeoJSONPointGeometry(coordinates=(lon, lat)),
            properties={"name": cam.name, "status": _effective_status(cam).value, "code": cam.code},
        )
        for cam, lon, lat in rows
        if lon is not None and lat is not None
    ]
    return GeoJSONFeatureCollection(features=features)


@router.post("/sync", response_model=CameraSyncResult)
def sync_camera_registry(
    entries: list[CameraRegistryEntry],
    db: Session = Depends(get_db),
    user=Depends(require_roles(UserRole.ADMIN, UserRole.OFFICER)),
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
    record_audit(
        db,
        action="CAMERA_SYNC",
        user_id=user.id,
        resource="camera",
        detail={"synced": len(synced)},
    )
    return CameraSyncResult(synced=len(synced), cameras=synced)


@router.post("/health", response_model=CameraHealthResult)
def push_camera_health(
    payload: CameraHealthPush,
    db: Session = Depends(get_db),
    _auth: str = Depends(require_ingest_auth),
):
    """Real endpoint for ``ingestion.stream_health.push_loop`` -- the
    HealthRegistry -> backend link that was previously a documented
    "SCHEMA PLACEHOLDER" pointing at a URL with no matching route
    (SENTINEL_System_Audit_Report.md §11 / ingestion/stream_health.py).

    Same auth as the AI event-ingestion endpoint (``X-Ingest-Key`` or an
    operator JWT) -- this is a service-to-service push from the ingestion
    process, not a browser call, so it reuses that dependency rather than
    inventing a third auth path.

    One camera's missing/unknown code is skipped (reported in the response,
    never raises) so a typo or a not-yet-onboarded camera in one entry can
    never fail the whole batch or affect any other camera's update --
    ingestion-side camera isolation is preserved end to end.
    """
    updated = 0
    skipped: list[str] = []
    now = datetime.utcnow()
    transitioned: list[Camera] = []
    for entry in payload.streams:
        camera = find_camera(db, entry.camera_id)
        if camera is None:
            skipped.append(entry.camera_id)
            continue
        mapped = _STREAM_TO_CAMERA_STATUS.get(entry.status)
        if mapped is not None:
            camera.status = mapped
        if entry.fps is not None:
            camera.stream_fps = entry.fps
        if entry.frame_drop_count is not None:
            camera.frame_drop_count = entry.frame_drop_count
        if entry.reconnect_count is not None:
            camera.reconnect_count = entry.reconnect_count
        camera.health_updated_at = now
        db.add(camera)
        updated += 1
        transitioned.append(camera)
    db.commit()

    # Phase 11 FEATURE 5/13: record an effective-status transition + emit a
    # camera offline/recovered notification, but only on a real change
    # (dedup lives in record_transition_if_changed). Best-effort; a failure
    # here never affects the health push result.
    for camera in transitioned:
        db.refresh(camera)
        record_transition_if_changed(
            db, camera, _effective_status(camera), source="health_push",
            stream_fps=camera.stream_fps, reconnect_count=camera.reconnect_count,
        )
    return CameraHealthResult(updated=updated, skipped=skipped)


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


@router.get("/{camera_id}/stream", response_model=CameraStreamProfile)
def camera_stream_profile(
    camera_id: str,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Phase 15A -- the ordered browser-playable sources for one camera plus
    an honest playback mode (LIVE / DEGRADED / RECORDED / OFFLINE). A
    snapshot is never presented as a live feed."""
    camera = find_camera(db, camera_id)
    if camera is None:
        raise NotFoundError("Camera", camera_id)
    return CameraStreamProfile(**CameraStreamService(db).profile(camera))


@router.get("/{camera_id}/health/history", response_model=CameraHealthHistoryResponse)
def camera_health_history(
    camera_id: str,
    limit: int = 100,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Effective-status transition log for one camera (Phase 11 FEATURE 5).
    Lightweight PostgreSQL history -- one row per real ONLINE<->OFFLINE
    change, never a per-second metric sample."""
    camera = db.get(Camera, camera_id)
    if camera is None:
        raise NotFoundError("Camera", camera_id)
    limit = max(1, min(limit, 500))
    total = db.execute(
        select(func.count(CameraHealthHistory.id)).where(
            CameraHealthHistory.camera_id == camera_id
        )
    ).scalar() or 0
    rows = db.execute(
        select(CameraHealthHistory)
        .where(CameraHealthHistory.camera_id == camera_id)
        .order_by(CameraHealthHistory.detected_at.desc())
        .limit(limit)
    ).scalars().all()
    return CameraHealthHistoryResponse(
        camera_id=camera_id,
        camera_code=camera.code,
        current_status=_effective_status(camera),
        health_updated_at=camera.health_updated_at,
        transitions=[CameraHealthHistoryRow.model_validate(r) for r in rows],
        total=int(total),
    )


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
    user=Depends(require_roles(UserRole.ADMIN, UserRole.OFFICER)),
):
    camera = Camera(
        name=payload.name,
        code=payload.code,
        rtsp_url=payload.rtsp_url,
        hls_url=payload.hls_url,
        webrtc_url=payload.webrtc_url,
        location_desc=payload.location_desc,
        status=payload.status,
        location=f"SRID=4326;POINT({payload.longitude} {payload.latitude})",
    )
    db.add(camera)
    db.commit()
    db.refresh(camera)
    record_audit(
        db, action="CAMERA_CREATED", user_id=user.id, resource="camera", resource_id=camera.id,
        detail={"code": camera.code, "name": camera.name},
    )
    return _to_camera_read(camera, payload.longitude, payload.latitude)


@router.patch("/{camera_id}", response_model=CameraRead)
def update_camera(
    camera_id: str,
    payload: CameraUpdate,
    db: Session = Depends(get_db),
    user=Depends(require_roles(UserRole.ADMIN, UserRole.OFFICER)),
):
    camera = db.get(Camera, camera_id)
    if camera is None:
        raise NotFoundError("Camera", camera_id)

    for field in ("name", "rtsp_url", "hls_url", "webrtc_url", "location_desc", "status"):
        value = getattr(payload, field)
        if value is not None:
            setattr(camera, field, value)

    if payload.latitude is not None and payload.longitude is not None:
        camera.location = f"SRID=4326;POINT({payload.longitude} {payload.latitude})"

    db.add(camera)
    db.commit()
    db.refresh(camera)
    record_audit(
        db, action="CAMERA_UPDATED", user_id=user.id, resource="camera", resource_id=camera.id,
        detail=payload.model_dump(exclude_none=True),
    )

    stmt = select(ST_X(Camera.location), ST_Y(Camera.location)).where(Camera.id == camera_id)
    lon, lat = db.execute(stmt).first()
    return _to_camera_read(camera, lon, lat)


@router.patch("/{camera_id}/behavior-config", response_model=CameraRead)
def update_camera_behavior_config(
    camera_id: str,
    payload: CameraBehaviorConfig,
    db: Session = Depends(get_db),
    user=Depends(require_roles(UserRole.ADMIN, UserRole.OFFICER)),
):
    """Phase 14 §6 -- set the wrong-way permitted direction and/or the
    restricted-zone polygons used by BehaviorAnalyticsService. Does NOT
    touch RTSP / credentials / status."""
    camera = db.get(Camera, camera_id)
    if camera is None:
        raise NotFoundError("Camera", camera_id)

    fields = payload.model_dump(exclude_unset=True)
    if "permitted_direction_deg" in fields:
        camera.permitted_direction_deg = fields["permitted_direction_deg"]
    if "restricted_zones" in fields:
        zones = fields["restricted_zones"]
        camera.restricted_zones = (
            [z if isinstance(z, dict) else z.model_dump() for z in payload.restricted_zones]
            if payload.restricted_zones is not None else None
        )

    db.add(camera)
    db.commit()
    db.refresh(camera)
    record_audit(
        db, action="CAMERA_BEHAVIOR_CONFIG", user_id=user.id, resource="camera",
        resource_id=camera.id,
        detail={"permitted_direction_deg": camera.permitted_direction_deg,
                "restricted_zones": len(camera.restricted_zones or [])},
    )
    lon, lat = db.execute(
        select(ST_X(Camera.location), ST_Y(Camera.location)).where(Camera.id == camera_id)
    ).first()
    return _to_camera_read(camera, lon, lat)


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_camera(
    camera_id: str,
    db: Session = Depends(get_db),
    user=Depends(require_roles(UserRole.ADMIN)),
):
    camera = db.get(Camera, camera_id)
    if camera is None:
        raise NotFoundError("Camera", camera_id)
    code = camera.code
    db.delete(camera)
    db.commit()
    record_audit(
        db, action="CAMERA_DELETED", user_id=user.id, resource="camera", resource_id=camera_id,
        detail={"code": code},
    )
