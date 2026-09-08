"""
SENTINEL backend microservice entrypoint.
Initializes FastAPI, CORS, exception handlers, REST routers, the native
WebSocket alert endpoint, and the periodic data-retention sweep.
"""
import asyncio
import contextlib
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.api.ws_alerts import router as ws_router
from app.config import settings
from app.core.exceptions import register_exception_handlers

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sentinel.main")


async def _retention_sweep_loop() -> None:
    """Periodically purge aged-out vehicle_events. Runs in-process off the
    event loop; safe to have running in every replica (the DELETE is
    idempotent and alert-referenced rows are never touched)."""
    from app.database import SessionLocal
    from app.services.audit import record_audit
    from app.services.retention import purge_old_vehicle_events

    interval_s = max(1, settings.RETENTION_SWEEP_INTERVAL_HOURS) * 3600
    # small initial delay so a burst of replicas don't all sweep at t=0
    await asyncio.sleep(min(60, interval_s))
    while True:
        try:
            db = SessionLocal()
            try:
                deleted = purge_old_vehicle_events(
                    db, retention_days=settings.VEHICLE_EVENT_RETENTION_DAYS
                )
                if deleted:
                    record_audit(
                        db,
                        action="RETENTION_PURGE",
                        resource="vehicle_events",
                        detail={
                            "deleted": deleted,
                            "retention_days": settings.VEHICLE_EVENT_RETENTION_DAYS,
                            "trigger": "sweep",
                        },
                    )
            finally:
                db.close()
        except Exception:  # noqa: BLE001 -- a failed sweep must not kill the loop
            logger.exception("retention sweep failed; will retry next interval")
        await asyncio.sleep(interval_s)


async def _camera_staleness_watcher_loop() -> None:
    """Phase 11 FEATURE 5/13 -- the smallest reliable mechanism for
    "camera went silent" transitions. Every CAMERA_HEALTH_WATCH_INTERVAL_S
    it recomputes each camera's effective status (fresh push -> stale ->
    OFFLINE) and records a transition + notification on a real change.
    Dedup lives in record_transition_if_changed, so a camera that stays
    offline never re-notifies. Bounded query (all cameras, ~dozens)."""
    from app.api.v1.cameras import _effective_status
    from app.database import SessionLocal
    from app.models.camera import Camera
    from app.services.camera_health import record_transition_if_changed
    from sqlalchemy import select

    interval_s = max(10, settings.CAMERA_HEALTH_WATCH_INTERVAL_S)
    await asyncio.sleep(min(30, interval_s))
    while True:
        try:
            db = SessionLocal()
            try:
                for cam in db.execute(select(Camera)).scalars().all():
                    # only cameras that have EVER reported health -- a camera
                    # that never had a push keeps its onboard status and is
                    # not a "transition to offline"
                    if cam.health_updated_at is None:
                        continue
                    record_transition_if_changed(
                        db, cam, _effective_status(cam), source="staleness_watcher",
                        stream_fps=cam.stream_fps, reconnect_count=cam.reconnect_count,
                    )
            finally:
                db.close()
        except Exception:  # noqa: BLE001 -- a failed tick must not kill the loop
            logger.exception("camera staleness watch tick failed; retrying next interval")
        await asyncio.sleep(interval_s)


async def _anomaly_scan_loop() -> None:
    """Phase 12 §4/§11 -- periodically run the stopped-vehicle detector over
    RECENTLY STORED events. Operates on `vehicle_events` only (never video).
    When government feeds resume, new events arrive through the existing
    ingest and this loop picks them up with no code change."""
    from app.database import SessionLocal
    from app.services.ai.behavior import BehaviorAnalyticsService
    from app.services.alert_dispatcher import connection_manager

    interval_s = max(30, settings.AI_ANOMALY_SCAN_INTERVAL_S)
    await asyncio.sleep(min(45, interval_s))
    while True:
        try:
            db = SessionLocal()
            try:
                result = BehaviorAnalyticsService(db).scan()
                for a in result["anomalies"]:
                    if a.alert_id:
                        await connection_manager.broadcast({
                            "type": "ALERT", "alert_id": a.alert_id, "source": "ANOMALY",
                            "plate_number": a.plate_number_normalized or "UNKNOWN",
                            "camera_code": a.camera_code,
                            "anomaly_kind": a.kind.value,
                            "priority_level": settings.ANOMALY_PRIORITY,
                        })
                if result["created"]:
                    logger.info("anomaly scan: %d new anomaly event(s)", result["created"])
            finally:
                db.close()
        except Exception:  # noqa: BLE001 -- a failed scan must not kill the loop
            logger.exception("anomaly scan tick failed; retrying next interval")
        await asyncio.sleep(interval_s)


async def _camera_transition_recompute_loop() -> None:
    """Phase 14 §3 -- periodically rebuild camera_transition_stats from
    stored vehicle_events (a plain statistical aggregate, NOT ML). Bounded,
    idempotent upsert. Off in the test suite."""
    from app.database import SessionLocal
    from app.services.ai.camera_transitions import CameraTransitionService

    interval_s = max(300, settings.CAMERA_TRANSITION_RECOMPUTE_INTERVAL_S)
    await asyncio.sleep(min(90, interval_s))
    while True:
        try:
            db = SessionLocal()
            try:
                result = CameraTransitionService(db).recompute()
                if result["pairs_upserted"]:
                    logger.info(
                        "camera transition recompute: %d pair(s) from %d event(s)",
                        result["pairs_upserted"], result["events_scanned"],
                    )
            finally:
                db.close()
        except Exception:  # noqa: BLE001 -- a failed recompute must not kill the loop
            logger.exception("camera transition recompute failed; retrying next interval")
        await asyncio.sleep(interval_s)


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    tasks: list[asyncio.Task] = []
    if settings.RETENTION_SWEEP_ENABLED and settings.VEHICLE_EVENT_RETENTION_DAYS > 0:
        tasks.append(asyncio.create_task(_retention_sweep_loop()))
        logger.info(
            "retention sweep enabled: every %dh, %d-day policy",
            settings.RETENTION_SWEEP_INTERVAL_HOURS,
            settings.VEHICLE_EVENT_RETENTION_DAYS,
        )
    if settings.CAMERA_HEALTH_WATCH_ENABLED:
        tasks.append(asyncio.create_task(_camera_staleness_watcher_loop()))
        logger.info(
            "camera health watcher enabled: every %ds",
            settings.CAMERA_HEALTH_WATCH_INTERVAL_S,
        )
    if settings.AI_ANOMALY_SCAN_ENABLED:
        tasks.append(asyncio.create_task(_anomaly_scan_loop()))
        logger.info(
            "AI anomaly scan enabled: every %ds (stopped-vehicle detector)",
            settings.AI_ANOMALY_SCAN_INTERVAL_S,
        )
    if settings.CAMERA_TRANSITION_RECOMPUTE_ENABLED:
        tasks.append(asyncio.create_task(_camera_transition_recompute_loop()))
        logger.info(
            "camera transition recompute enabled: every %ds",
            settings.CAMERA_TRANSITION_RECOMPUTE_INTERVAL_S,
        )
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="SENTINEL — Automated ANPR Watchlist Cross-Referencing Backend",
    lifespan=lifespan,
)

_cors_origins = settings.resolved_cors_origins()
# The CORS spec forbids credentialed requests when the allow-list is the
# "*" wildcard; Starlette would otherwise emit an invalid header pair.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials="*" not in _cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)
app.include_router(ws_router)


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok", "service": settings.APP_NAME}
