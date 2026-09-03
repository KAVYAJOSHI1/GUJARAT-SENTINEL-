"""
AI Event Ingestion API — POST /api/v1/events/ai-detection
Receives detection payloads from Kavya's ANPR/YOLO pipeline, persists to
vehicle_events, uploads the snapshot to MinIO (local-disk fallback), runs
the Watchlist engine + cooldown deduplicator, and broadcasts any resulting
alert over WebSocket. Target ingestion latency: < 20ms exclusive of the
MinIO upload (uploads run inline here; for stricter SLAs, offload to a
background task queue).
"""
import logging

from fastapi import APIRouter, Depends, status

from app.api.deps import get_current_user
from app.database import get_db
from app.models.vehicle_event import VehicleEvent
from app.schemas.event import AIDetectionEventIn, AIDetectionEventOut
from app.services.alert_dispatcher import connection_manager
from app.services.minio_service import get_minio_service
from app.services.plate_utils import normalize_plate
from app.services.watchlist_engine import process_event_against_watchlist
from sqlmodel import Session

logger = logging.getLogger("sentinel.events")

router = APIRouter()


@router.post(
    "/ai-detection",
    response_model=AIDetectionEventOut,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_ai_detection(
    payload: AIDetectionEventIn,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    plate_normalized = normalize_plate(payload.plate_number)

    snapshot_url = None
    if payload.snapshot_base64:
        snapshot_url = get_minio_service().upload_snapshot(
            camera_id=payload.camera_id,
            plate=plate_normalized,
            snapshot_base64=payload.snapshot_base64,
            content_type=payload.snapshot_content_type,
        )

    event = VehicleEvent(
        plate_number=payload.plate_number,
        plate_number_normalized=plate_normalized,
        camera_id=payload.camera_id,
        timestamp=payload.timestamp,
        vehicle_type=payload.vehicle_type,
        vehicle_color=payload.vehicle_color,
        confidence_score=payload.confidence_score,
        snapshot_url=snapshot_url,
        latitude=payload.latitude,
        longitude=payload.longitude,
        location=(
            f"SRID=4326;POINT({payload.longitude} {payload.latitude})"
            if payload.latitude is not None and payload.longitude is not None
            else None
        ),
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    # --- Watchlist cross-reference + cooldown-gated alert creation ---
    match, alert, suppressed = process_event_against_watchlist(db, event)

    if alert is not None:
        await connection_manager.broadcast(
            {
                "type": "ALERT",
                "alert_id": alert.id,
                "plate_number": alert.plate_number,
                "camera_id": alert.camera_id,
                "priority_level": alert.priority_level.value,
                "snapshot_url": alert.snapshot_url,
                "created_at": alert.created_at.isoformat(),
            }
        )
    elif suppressed:
        logger.info(
            "Alert suppressed by cooldown for plate=%s camera=%s",
            plate_normalized,
            payload.camera_id,
        )

    return AIDetectionEventOut(
        id=event.id,
        camera_id=event.camera_id,
        plate_number=event.plate_number,
        plate_number_normalized=event.plate_number_normalized,
        timestamp=event.timestamp,
        snapshot_url=event.snapshot_url,
        watchlist_match=match is not None,
        alert_id=alert.id if alert else None,
    )
