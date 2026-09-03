# SENTINEL — Backend Microservice & PostGIS Platform

Developer: **Vanshal** — Backend Microservice, PostGIS Database & Watchlist Engine Lead
Branch: `feature/vanshal-backend`

## What this is

The central FastAPI backend + PostGIS spatial-temporal database for SENTINEL:
camera registry, AI detection ingestion, the Watchlist Cross-Referencing
Engine with a 300-second alert-cooldown deduplicator, real-time WebSocket
alert broadcasting, and MinIO evidence-snapshot storage (with local-disk
fallback).

## Layout

```
backend/
  app/
    api/v1/        REST routers: auth, cameras, events, vehicles, watchlist, alerts
    api/ws_alerts.py   WS /ws/alerts broadcaster endpoint
    core/           security (JWT), rbac, exception handlers
    models/         SQLModel tables: Camera, VehicleEvent, Watchlist, Alert, User, AuditLog
    schemas/        Pydantic request/response contracts
    services/       minio_service, watchlist_engine, cooldown, alert_dispatcher, plate_utils
    config.py, database.py, main.py
  requirements.txt, Dockerfile, .env.example
database/
  init_postgis.sql          enables PostGIS 3.3 on first container boot
  alembic.ini, migrations/  schema migrations (initial revision creates all 6 tables + indexes)
docker-compose.yml           postgis + minio + backend, wired together
```

## Run it

```bash
docker compose up --build
```

This starts:
- **postgis** (PostgreSQL 15 + PostGIS 3.3) on `5432`
- **minio** on `9000` (console on `9001`, both `minioadmin`/`minioadmin`)
- **backend** on `8000`, running Alembic migrations then Uvicorn with reload

API docs: `http://localhost:8000/docs`
Health check: `GET http://localhost:8000/health`

## Creating a first user

There's no self-serve signup by design (RBAC-gated system). Seed a user directly, e.g. via a one-off Python shell inside the backend container:

```python
from app.database import SessionLocal
from app.models.user import User
from app.models.base import UserRole
from app.core.security import hash_password

db = SessionLocal()
db.add(User(username="admin", email="admin@sentinel.local",
            hashed_password=hash_password("changeme"), role=UserRole.ADMIN))
db.commit()
```

Then `POST /api/v1/auth/login` with that username/password to get a bearer token.

## Key endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/auth/login` | Issue JWT |
| GET/POST/PATCH/DELETE | `/api/v1/cameras` | Camera CRUD |
| GET | `/api/v1/cameras/geojson` | PostGIS GeoJSON FeatureCollection |
| POST | `/api/v1/events/ai-detection` | AI event ingestion (Kavya's pipeline → here) |
| GET | `/api/v1/vehicles/search?plate=GJ01AB1234` | Chronological trajectory search |
| GET/POST/DELETE | `/api/v1/watchlist` | Watchlist management |
| GET/PATCH | `/api/v1/alerts` | Alert list / acknowledge |
| WS | `/ws/alerts` | Real-time alert broadcast |

## Pipeline (as implemented in `api/v1/events.py` + `services/watchlist_engine.py`)

```
POST /api/v1/events/ai-detection
  → snapshot to MinIO (fallback: local disk)
  → save vehicle_events row
  → watchlist_engine: exact normalized-plate lookup
      match:
        → cooldown.py: same plate+camera alert in last 300s?
            yes → suppress
            no  → create alerts row → broadcast over WS /ws/alerts
      no match: return success (event logged only)
```

## What's intentionally NOT here

Per the developer guide's scope boundaries: no YOLO/PaddleOCR detection
models, no RTSP stream capture workers, and no React/Leaflet frontend —
those belong to Kavya, Rishit, and Isha/Vishakha respectively.

## Next steps before opening the PR to `testing`

1. Seed an admin user and confirm login.
2. `docker compose up`, hit `/health`, confirm PostGIS tables via `\dt` in `psql`.
3. POST a sample AI detection event, confirm it lands in `vehicle_events`.
4. Add a watchlist entry for that plate, re-POST the same detection, confirm
   an `alerts` row is created and pushed over `/ws/alerts`.
5. Re-POST the same detection within 5 minutes and confirm no second alert
   is created (cooldown suppression).
6. Run `GET /api/v1/vehicles/search?plate=...` and confirm chronological
   ordering.
