"""Aggregates all /api/v1 sub-routers into a single APIRouter."""
from fastapi import APIRouter

from app.api.v1 import auth, cameras, dashboard, events, vehicles, watchlist, alerts

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(cameras.router, prefix="/cameras", tags=["cameras"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(events.router, prefix="/events", tags=["events"])
api_router.include_router(vehicles.router, prefix="/vehicles", tags=["vehicles"])
api_router.include_router(watchlist.router, prefix="/watchlist", tags=["watchlist"])
api_router.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
