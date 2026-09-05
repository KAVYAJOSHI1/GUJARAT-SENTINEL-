"""
Vehicle Search & Trajectory API — GET /api/v1/vehicles/search?plate={plate}
Returns chronologically ordered sightings using the composite B-Tree index
on (plate_number_normalized, timestamp). Target: <50ms for 100k+ rows.
"""
import os

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse, RedirectResponse
from geoalchemy2.functions import ST_X, ST_Y
from sqlalchemy import select
from sqlmodel import Session

from app.api.deps import get_current_user, verify_bearer_header_or_query
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.camera import Camera
from app.models.vehicle_event import VehicleEvent
from app.models.watchlist import Watchlist
from app.schemas.auth import CurrentUser
from app.schemas.vehicle import VehicleHistoryResponse, VehicleSighting
from app.services.audit import record_audit
from app.services.plate_utils import normalize_plate
from app.services.watchlist_engine import active_watchlist_clause

router = APIRouter()

# Where THIS process can see the AI pipeline's local evidence tree
# (evidence/live/, evidence/mock/, ...). The DB stores whatever absolute
# path the pipeline process wrote (host machine, since the pipeline only
# ever runs on bare metal) -- in the dockerized backend that path doesn't
# exist, so it's translated against this mount instead (see the `evidence`
# volume in docker-compose.yml). Defaults to the repo-relative folder for a
# bare-metal (non-docker) backend run, where the literal path already works.
EVIDENCE_ROOT = os.getenv(
    "EVIDENCE_ROOT",
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "evidence"),
)


def _resolve_local_evidence_path(stored_path: str):
    """Rewrite anything after 'evidence/' in a stored host path onto
    EVIDENCE_ROOT, mirroring cameras.py's _resolve_mock_video_path. Returns
    None (falls back to the literal path) if there's nothing to translate or
    the translated file doesn't exist either."""
    if not stored_path:
        return None
    marker = f"evidence{os.sep}"
    idx = stored_path.rfind(marker)
    if idx == -1:
        return None
    candidate = os.path.join(EVIDENCE_ROOT, stored_path[idx + len(marker):])
    return candidate if os.path.isfile(candidate) else None


@router.get("/search", response_model=VehicleHistoryResponse)
def search_vehicle(
    plate: str = Query(..., min_length=2, description="Registration plate to search, e.g. GJ01AB1234"),
    limit: int = Query(default=200, le=1000),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    plate_normalized = normalize_plate(plate)

    stmt = (
        select(
            VehicleEvent,
            Camera.name,
            Camera.code,
            Camera.location_desc,
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
            location_desc=location_desc,
            timestamp=ev.timestamp,
            # prefer the event's own fix; fall back to the camera's location
            latitude=ev.latitude if ev.latitude is not None else cam_lat,
            longitude=ev.longitude if ev.longitude is not None else cam_lon,
            snapshot_url=ev.snapshot_url,
            confidence_score=ev.confidence_score,
            track_id=ev.track_id,
            vehicle_type=ev.vehicle_type,
            plate_number=ev.plate_number,
        )
        for ev, camera_name, camera_code, location_desc, cam_lat, cam_lon in rows
    ]

    is_watchlisted = (
        db.execute(
            select(Watchlist.id)
            .where(Watchlist.plate_number_normalized == plate_normalized)
            .where(active_watchlist_clause())
            .limit(1)
        ).first()
        is not None
    )

    # Investigation / vehicle-search is a sensitive lookup on a real person's
    # movement history -- audit who searched what (SENTINEL_System_Audit_Report.md
    # §10 "Vehicle investigation/search"). Never blocks the response if the
    # audit write itself fails (see services/audit.py).
    record_audit(
        db,
        action="VEHICLE_SEARCH",
        user_id=user.id,
        resource="vehicle",
        resource_id=plate_normalized,
        detail={"total_sightings": len(sightings), "is_watchlisted": is_watchlisted},
    )

    return VehicleHistoryResponse(
        plate_number=plate_normalized,
        total_sightings=len(sightings),
        is_watchlisted=is_watchlisted,
        sightings=sightings,
    )


@router.get("/events/recent", response_model=list[VehicleSighting])
def recent_vehicle_events(
    limit: int = Query(default=50, le=500),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Most recent AI detections across all cameras (dashboard event feed)."""
    stmt = (
        select(
            VehicleEvent,
            Camera.name,
            Camera.code,
            Camera.location_desc,
            ST_Y(Camera.location),
            ST_X(Camera.location),
        )
        .join(Camera, Camera.id == VehicleEvent.camera_id, isouter=True)
        .order_by(VehicleEvent.timestamp.desc())
        .limit(limit)
    )
    return [
        VehicleSighting(
            event_id=ev.id,
            camera_id=ev.camera_id,
            camera_code=code,
            camera_name=name,
            location_desc=location_desc,
            timestamp=ev.timestamp,
            latitude=ev.latitude if ev.latitude is not None else cam_lat,
            longitude=ev.longitude if ev.longitude is not None else cam_lon,
            snapshot_url=ev.snapshot_url,
            confidence_score=ev.confidence_score,
            track_id=ev.track_id,
            vehicle_type=ev.vehicle_type,
            plate_number=ev.plate_number,
        )
        for ev, name, code, location_desc, cam_lat, cam_lon in db.execute(stmt).all()
    ]


@router.get("/evidence/{event_id}")
def get_evidence(
    event_id: str,
    requesting_user_id: str = Depends(verify_bearer_header_or_query),
    db: Session = Depends(get_db),
):
    """Serve (or redirect to) the snapshot image for one vehicle event.

    Accepts a normal Bearer token OR a ``?token=`` query param, because
    ``<img src>`` cannot send an Authorization header. ``event_id`` is an
    opaque UUID, so this is a low-sensitivity read.
    """
    ev = db.get(VehicleEvent, event_id)
    if ev is None or not ev.snapshot_url:
        raise NotFoundError("Evidence", event_id)
    record_audit(
        db,
        action="EVIDENCE_ACCESSED",
        user_id=requesting_user_id,
        resource="vehicle_event",
        resource_id=event_id,
    )
    url = ev.snapshot_url

    # Proxy the bytes through the backend so it works from any network (browser
    # can't reach the internal MinIO host, file:// paths aren't shared, etc).
    from app.services.minio_service import get_minio_service

    got = get_minio_service().fetch_bytes(url)
    if got is not None:
        from fastapi.responses import Response

        data, ctype = got
        return Response(content=data, media_type=ctype)

    if url.startswith(("http://", "https://")):
        return RedirectResponse(url)
    # ai/pipeline.py writes plain absolute filesystem paths (os.path.abspath),
    # not file:// URIs -- accept both. This is the fallback for a snapshot
    # that was never uploaded to MinIO (SENTINEL_SEND_SNAPSHOT sends it only
    # once per track, per ai/pipeline.py's dedup) -- covers both real
    # cameras' evidence/live/ and mock cameras' evidence/mock/.
    local_path = url[7:] if url.startswith("file://") else url
    local_path = _resolve_local_evidence_path(local_path) or local_path
    if os.path.isabs(local_path) and os.path.isfile(local_path):
        return FileResponse(local_path)
    raise NotFoundError("Evidence file", event_id)
