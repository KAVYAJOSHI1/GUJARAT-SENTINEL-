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
