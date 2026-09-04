"""
AI Event Ingestion API — POST /api/v1/events/ai-detection

Receives the detection payload emitted by Kavya's ANPR/YOLO/ByteTrack
pipeline (``ai/pipeline.py``), resolves the external camera id to a
``cameras`` row (auto-onboarding if needed), persists to ``vehicle_events``,
records the evidence reference (inline base64 -> object storage, or a
path/URL as-is), runs the watchlist engine + cooldown deduplicator, and
broadcasts any resulting alert over WebSocket.

Auth: ``X-Ingest-Key`` (AI pipeline service credential) OR an operator JWT.
"""
import logging
import os

from fastapi import APIRouter, Depends, status

from app.api.deps import require_ingest_auth
from app.config import settings
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.vehicle_event import VehicleEvent
from app.schemas.event import AIDetectionEventIn, AIDetectionEventOut
from app.services.alert_dispatcher import connection_manager
from app.services.camera_resolver import resolve_camera
from app.services.minio_service import get_minio_service
from app.services.plate_utils import normalize_plate
from app.services.watchlist_engine import process_event_against_watchlist
from sqlmodel import Session

logger = logging.getLogger("sentinel.events")

router = APIRouter()


def _store_snapshot(payload: AIDetectionEventIn, plate_normalized: str, camera_code: str):
    """Return a snapshot reference string (or None). Inline base64 goes to
    object storage; a path/URL is stored as-is (normalised to file:// if it is
    a local file that exists)."""
    if payload.snapshot_base64:
        try:
            return get_minio_service().upload_snapshot(
                camera_id=camera_code,
                plate=plate_normalized,
                snapshot_base64=payload.snapshot_base64,
                content_type=payload.snapshot_content_type,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("snapshot upload failed (%s)", exc)

    ref = payload.resolved_snapshot_ref()
    if not ref:
        return None
    if ref.startswith(("http://", "https://", "file://", "s3://")):
        return ref
    # bare filesystem path
    if os.path.exists(ref):
        return f"file://{os.path.abspath(ref)}"
    return ref  # keep the reference even if not resolvable here


@router.post(
    "/ai-detection",
    response_model=AIDetectionEventOut,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_ai_detection(
    payload: AIDetectionEventIn,
    db: Session = Depends(get_db),
    _auth: str = Depends(require_ingest_auth),
):
    camera = resolve_camera(
        db,
        payload.camera_id,
        name=payload.camera_name,
        latitude=payload.latitude,
        longitude=payload.longitude,
        auto_create=settings.INGEST_AUTO_ONBOARD_CAMERAS,
    )
    if camera is None:
        raise NotFoundError("Camera", payload.camera_id)

    plate_raw = payload.resolved_plate()
    plate_normalized = normalize_plate(plate_raw)
    camera_code = camera.code or payload.camera_id

    snapshot_url = _store_snapshot(payload, plate_normalized, camera_code)

    lat = payload.latitude
    lon = payload.longitude
    event = VehicleEvent(
        plate_number=plate_raw,
        plate_number_normalized=plate_normalized,
        camera_id=camera.id,
        camera_code=camera_code,
        track_id=payload.resolved_track_id(),
        timestamp=payload.timestamp,
        vehicle_type=payload.resolved_vehicle_type(),
        vehicle_color=payload.vehicle_color,
        confidence_score=payload.resolved_confidence(),
        snapshot_url=snapshot_url,
        latitude=lat,
        longitude=lon,
        location=(
            f"SRID=4326;POINT({lon} {lat})" if lat is not None and lon is not None else None
        ),
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    # --- Watchlist cross-reference + cooldown-gated alert creation ---
    # UNKNOWN plates never match the watchlist (there is no "UNKNOWN" entry),
    # so uncertain reads are preserved as normal logged events, not alerts.
    match, alert, suppressed = process_event_against_watchlist(db, event)

    if alert is not None:
        await connection_manager.broadcast(
            {
                "type": "ALERT",
                "alert_id": alert.id,
                "plate_number": alert.plate_number,
                "camera_id": alert.camera_id,
                "camera_code": camera_code,
                "priority_level": alert.priority_level.value,
                "snapshot_url": alert.snapshot_url,
                "created_at": alert.created_at.isoformat(),
            }
        )
    elif suppressed:
        logger.info(
            "Alert suppressed by cooldown for plate=%s camera=%s",
            plate_normalized,
            camera_code,
        )

    return AIDetectionEventOut(
        id=event.id,
        event_id=payload.event_id,
        camera_id=event.camera_id,
        camera_code=camera_code,
        track_id=event.track_id,
        plate_number=event.plate_number,
        plate_number_normalized=event.plate_number_normalized,
        timestamp=event.timestamp,
        snapshot_url=event.snapshot_url,
        watchlist_match=match is not None,
        alert_id=alert.id if alert else None,
        alert_suppressed_by_cooldown=suppressed,
    )
