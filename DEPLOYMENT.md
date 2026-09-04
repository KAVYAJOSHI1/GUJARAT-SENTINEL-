# SENTINEL — Production Deployment & Orchestration Guide

---

## 1. Environment Startup Steps (Testing / Production Branch)

On the integration branch (`testing`), full stack deployment is managed via Docker Compose:

```bash
# 1. Clone Repository & Checkout Testing Branch
git clone git@github.com:KAVYAJOSHI1/GUJARAT-SENTINEL-.git
cd GUJARAT-SENTINEL-
git checkout testing

# 2. Configure Environment Variables
cp .env.example .env

# 3. Launch Containerized Services
docker-compose up --build -d
```

---

## 2. Containerized Port Mappings

- **PostgreSQL + PostGIS**: `localhost:5432`
- **MinIO Object Storage**: `localhost:9000` (Console: `localhost:9001`)
- **FastAPI Backend Services**: `localhost:8000`
- **Stream Ingestion Manager**: `localhost:8001`
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
SENTINEL_RTSP_USERNAME=... SENTINEL_RTSP_PASSWORD=... \
  docker compose --profile ai up pipeline
```

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
