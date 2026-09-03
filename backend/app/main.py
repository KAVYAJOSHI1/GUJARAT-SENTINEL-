"""
SENTINEL backend microservice entrypoint.
Initializes FastAPI, CORS, exception handlers, REST routers and the
native WebSocket alert endpoint.
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.api.ws_alerts import router as ws_router
from app.config import settings
from app.core.exceptions import register_exception_handlers

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="SENTINEL — Automated ANPR Watchlist Cross-Referencing Backend",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)
app.include_router(ws_router)


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok", "service": settings.APP_NAME}
