"""
Shared pytest fixtures for the SENTINEL backend test suite.

Runs against a REAL Postgres+PostGIS instance (a `Camera.location`
`Geometry` column can't be faked with SQLite) -- point `DATABASE_URL` at a
disposable database before running these tests, e.g. the local
docker-compose `postgis` service:

    docker compose up -d postgis
    createdb -h localhost -p 5457 -U sentinel sentinel_test   # once
    cd backend && ../.venv/bin/python -m pytest tests/

The env vars below are set BEFORE any `app.*` import so
`app.config.settings` (a module-level singleton, read once at import) picks
them up. Nothing here is a production credential -- this is a disposable
local test database with a throwaway JWT secret.
"""
import os

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg2://sentinel:sentinel@localhost:5457/sentinel_test",
)
os.environ["JWT_SECRET_KEY"] = "test-only-jwt-secret-never-used-in-production"
os.environ["INGEST_API_KEY"] = "test-ingest-key"
os.environ["CORS_ALLOW_ORIGINS"] = '["*"]'
os.environ["ENV"] = "test"
os.environ["INGEST_AUTO_ONBOARD_CAMERAS"] = "true"
# Retention sweep is exercised directly in test_retention.py; keep the
# background lifespan task off during the rest of the suite.
os.environ["RETENTION_SWEEP_ENABLED"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

# Import every table module so SQLModel.metadata knows about all of them
# before create_all() runs.
from app.models import alert, audit_log, camera, user, vehicle_event, watchlist  # noqa: E402,F401
from app.core.security import create_access_token, hash_password  # noqa: E402
from app.database import SessionLocal, engine, get_db  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.models.base import CameraStatus, UserRole  # noqa: E402
from app.models.camera import Camera  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.vehicle_event import VehicleEvent  # noqa: E402
from app.services.plate_utils import normalize_plate  # noqa: E402

TABLES_TO_CLEAN = (
    "audit_logs",
    "alerts",
    "vehicle_events",
    "watchlist",
    "cameras",
    "users",
)


@pytest.fixture(scope="session", autouse=True)
def _schema():
    """Create (once) every table the app models declare, in the test DB."""
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    SQLModel.metadata.create_all(engine)
    yield


@pytest.fixture(autouse=True)
def _clean_tables():
    """Every test starts from an empty (but already-migrated) database."""
    yield
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {', '.join(TABLES_TO_CLEAN)} RESTART IDENTITY CASCADE"))


@pytest.fixture
def db_session():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client(db_session):
    def _override_get_db():
        yield db_session

    fastapi_app.dependency_overrides[get_db] = _override_get_db
    with TestClient(fastapi_app) as c:
        yield c
    fastapi_app.dependency_overrides.pop(get_db, None)


def _make_user(db_session, username: str, role: UserRole, password: str = "Password123!"):
    user = User(
        username=username,
        email=f"{username}@example.test",
        hashed_password=hash_password(password),
        role=role,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    token = create_access_token(subject=user.id, role=user.role.value)
    return user, token


@pytest.fixture
def admin_user(db_session):
    return _make_user(db_session, "test_admin", UserRole.ADMIN)


@pytest.fixture
def officer_user(db_session):
    return _make_user(db_session, "test_officer", UserRole.OFFICER)


@pytest.fixture
def operator_user(db_session):
    return _make_user(db_session, "test_operator", UserRole.OPERATOR)


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def ws_ticket(client, token: str) -> str:
    """Exchange a session JWT for a short-lived WS handshake ticket, the way
    the real dashboard does before opening /ws/alerts."""
    resp = client.post("/api/v1/auth/ws-ticket", headers=bearer(token))
    assert resp.status_code == 200, resp.text
    return resp.json()["ticket"]


def media_ticket(client, token: str) -> str:
    resp = client.post("/api/v1/auth/media-ticket", headers=bearer(token))
    assert resp.status_code == 200, resp.text
    return resp.json()["ticket"]


@pytest.fixture(autouse=True)
def _reset_login_rate_limiter():
    """Each test starts with an empty login rate-limiter (it's process-global
    in-memory state, not DB state, so the table TRUNCATE doesn't touch it)."""
    from app.services.rate_limit import login_rate_limiter

    login_rate_limiter.clear()
    yield
    login_rate_limiter.clear()


@pytest.fixture
def make_camera(db_session):
    def _make(code="cam-test-01", status=CameraStatus.OFFLINE, lat=23.03, lon=72.58, **extra):
        # pass lat=None (or lon=None) for a camera with no geometry
        loc = extra.pop("location", None)
        if loc is None and lat is not None and lon is not None:
            loc = f"SRID=4326;POINT({lon} {lat})"
        cam = Camera(
            code=code,
            name=extra.pop("name", code),
            status=status,
            location=loc,
            **extra,
        )
        db_session.add(cam)
        db_session.commit()
        db_session.refresh(cam)
        return cam

    return _make


@pytest.fixture
def make_vehicle_event(db_session):
    def _make(camera, plate="GJ18XX1234", track_id=1, ts=None, **extra):
        from datetime import datetime

        norm = normalize_plate(plate)
        ev = VehicleEvent(
            plate_number=plate,
            plate_number_normalized=norm,
            camera_id=camera.id,
            camera_code=camera.code,
            track_id=track_id,
            timestamp=ts or datetime.utcnow(),
            confidence_score=0.9,
            **extra,
        )
        db_session.add(ev)
        db_session.commit()
        db_session.refresh(ev)
        return ev

    return _make
