# SENTINEL — Production Deployment & Orchestration Guide

---

## 1. Environment Startup Steps

Full-stack deployment is managed via Docker Compose. For a guided demo
walkthrough (mock ANPR flow, expected results, troubleshooting) see
[`DEMO_RUNBOOK.md`](DEMO_RUNBOOK.md).

```bash
# 1. Clone the repository
git clone <repo-url>
cd GUJARAT-SENTINEL

# 2. Configure environment variables (optional — sane defaults exist)
cp .env.example .env

# 3. Launch containerized services
docker compose up --build -d
```

---

## 2. Containerized Port Mappings

Host ports are configurable in `.env` (`*_HOST_PORT`); defaults below.

- **PostgreSQL + PostGIS**: `localhost:5432`
- **MinIO Object Storage**: `localhost:9000` (Console: `localhost:9001`)
- **FastAPI Backend Services**: `localhost:8000`
- **React Command Dashboard**: `localhost:3000`

---

## 3. Local Stack — `docker compose` (this branch)

```bash
cp .env.example .env          # optional: set ADMIN_PASSWORD, INGEST_API_KEY,
                              # and *_HOST_PORT if 5432/8000/3000/9000 are taken

docker compose up --build     # postgis + minio + backend + frontend
                              # backend auto-runs: alembic upgrade head + seed_db
                              # (if ADMIN_PASSWORD is unset a random one is printed)

docker compose down           # stop
docker compose down -v        # stop + wipe postgis/minio data volumes
```

Services: `http://localhost:${FRONTEND_HOST_PORT:-3000}` (dashboard),
`http://localhost:${BACKEND_HOST_PORT:-8000}/docs` (API),
MinIO console `:9001`.

**Ingestion + AI pipeline** (heavy — pulls torch/ultralytics; opt-in):

```bash
# Real Sentinel cameras (needs RTSP credentials in .env):
SENTINEL_RTSP_USERNAME=... SENTINEL_RTSP_PASSWORD=... \
  docker compose --profile ai up pipeline

# Mock ANPR demo (no credentials needed — uses committed demo clips):
PIPELINE_REGISTRY=data/demo_camera_registry.json \
PIPELINE_CAMERAS=mockcam01,mockcam02,mockcam03 \
  docker compose --profile ai up pipeline
```

See [`DEMO_RUNBOOK.md`](DEMO_RUNBOOK.md) for the full demo flow.

### Migrations / seed (manual, outside compose)

```bash
cd database && DATABASE_URL=postgresql+psycopg2://sentinel:sentinel@localhost:5432/sentinel \
  alembic -c alembic.ini upgrade head

cd backend && DATABASE_URL=... ADMIN_PASSWORD=... python ../scripts/seed_db.py   # idempotent
```

### Bare-metal (no Docker)

```bash
pip install -r backend/requirements.txt -r requirements-ai.txt
# 1. Postgres+PostGIS running, DATABASE_URL exported
alembic -c database/alembic.ini upgrade head
python scripts/seed_db.py                                  # ADMIN_PASSWORD required
cd backend && uvicorn app.main:app --port 8000             # backend
cd frontend && npm ci && npm run dev                       # dashboard :3000
python scripts/run_pipeline_service.py --cameras cam04,cam06   # ingestion + AI
```
