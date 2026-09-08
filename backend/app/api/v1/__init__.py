"""Aggregates all /api/v1 sub-routers into a single APIRouter."""
from fastapi import APIRouter

from app.api.v1 import (
    admin,
    ai,
    alerts,
    analytics,
    auth,
    cameras,
    cases,
    correlation,
    dashboard,
    events,
    incidents,
    notifications,
    pipeline,
    reid,
    reports,
    saved_searches,
    search,
    traffic,
    vehicles,
    watchlist,
    work_queue,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(cameras.router, prefix="/cameras", tags=["cameras"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(events.router, prefix="/events", tags=["events"])
api_router.include_router(vehicles.router, prefix="/vehicles", tags=["vehicles"])
api_router.include_router(watchlist.router, prefix="/watchlist", tags=["watchlist"])
api_router.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
api_router.include_router(incidents.router, prefix="/incidents", tags=["incidents"])
api_router.include_router(cases.router, prefix="/cases", tags=["cases"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
api_router.include_router(search.router, prefix="/search", tags=["search"])
api_router.include_router(saved_searches.router, prefix="/saved-searches", tags=["saved-searches"])
api_router.include_router(work_queue.router, prefix="/work-queue", tags=["work-queue"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])
api_router.include_router(reid.router, prefix="/ai/reid", tags=["ai", "reid"])
api_router.include_router(correlation.router, prefix="/ai/correlation", tags=["ai", "correlation"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(traffic.router, prefix="/analytics/traffic", tags=["analytics", "traffic"])
api_router.include_router(pipeline.router, prefix="/pipeline", tags=["pipeline"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
