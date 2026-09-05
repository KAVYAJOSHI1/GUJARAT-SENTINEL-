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


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    task = None
    if settings.RETENTION_SWEEP_ENABLED and settings.VEHICLE_EVENT_RETENTION_DAYS > 0:
        task = asyncio.create_task(_retention_sweep_loop())
        logger.info(
            "retention sweep enabled: every %dh, %d-day policy",
            settings.RETENTION_SWEEP_INTERVAL_HOURS,
            settings.VEHICLE_EVENT_RETENTION_DAYS,
        )
    try:
        yield
    finally:
        if task is not None:
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
