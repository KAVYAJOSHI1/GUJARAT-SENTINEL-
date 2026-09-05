# SENTINEL — Demo Runbook

Step-by-step for demoing the platform end to end from a **fresh clone**, with
the exact commands, the expected results, and recovery steps if something is
off. Read [`SUBMISSION_REQUIREMENTS.md`](SUBMISSION_REQUIREMENTS.md) first for
the honest capability status.

TL;DR of what the demo shows: a watch-listed plate (`GJ18TC0450`) is read by
the AI pipeline off three mock cameras → a real-time alert fires → it arrives
on the command center over WebSocket → the evidence snapshot is captured → the
vehicle's journey is stitched across the three cameras → the route draws on the
GIS map.

---

## 0. Prerequisites

- Docker + Docker Compose v2 (`docker compose version`).
- ~8 GB free disk (the AI pipeline image pulls torch / ultralytics / easyocr).
- Ports `3000`, `8000`, `5432`, `9000`, `9001` free — or override them in
  `.env` (`FRONTEND_HOST_PORT`, `BACKEND_HOST_PORT`, `POSTGRES_HOST_PORT`,
  `MINIO_HOST_PORT`, `MINIO_CONSOLE_HOST_PORT`).
- No GPU required — the pipeline runs CPU-only.

Everything the mock demo needs is committed to the repo:

| Asset | Path | Notes |
| :--- | :--- | :--- |
| Demo video clips | `demo_assets/clips/mockcam0{1,2,3}.mp4` | H.264/MP4, ~0.5 MB each, 20 s, browser-playable |
| Mock camera registry | `data/demo_camera_registry.json` | 3 cameras, repo-relative clip paths |
| Watchlist seed | `SEED_WATCHLIST_PLATE` default in `docker-compose.yml` | `GJ18TC0450`, category "Stolen Vehicle (demo)" |

---

## 1. Fresh start

```bash
git clone <repo-url> && cd GUJARAT-SENTINEL

# Optional: cp .env.example .env and edit. Not required — compose has
# working defaults, and the backend prints a random admin password on
# first boot if ADMIN_PASSWORD is unset.

# Wipe any previous state and bring up the core stack:
docker compose down -v
docker compose up -d --build
```

Wait for the backend to become healthy:

```bash
docker compose ps                       # backend -> "healthy"
curl -s localhost:8000/health           # {"status":"ok"}
```

On first boot the backend entrypoint runs `alembic upgrade head` then
`scripts/seed_db.py`, which idempotently creates:

- the admin user (`admin` / your `ADMIN_PASSWORD`, or the printed random one —
  grab it with `docker compose logs backend | grep -i password`);
- **one watchlist entry for `GJ18TC0450`** (because `SEED_WATCHLIST_PLATE`
  defaults to that plate in `docker-compose.yml`).

### Verify the seeded watchlist

```bash
# log in
TOKEN=$(curl -s localhost:8000/api/v1/auth/login \
  -H 'content-type: application/json' \
  -d '{"username":"admin","password":"<ADMIN_PASSWORD>"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

# the watchlist should contain GJ18TC0450
curl -s localhost:8000/api/v1/watchlist -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

Expected: one active entry, `plate_number_normalized: "GJ18TC0450"`,
`offense_category: "Stolen Vehicle (demo)"`, `priority_level: "HIGH"`.

To demo a **clean** deployment with no seed data, set `SEED_WATCHLIST_PLATE=`
(empty) in `.env` before `up`.

---

## 2. Run the mock ANPR pipeline (the main demo)

The pipeline is opt-in (compose profile `ai`) because its image is heavy.
Point it at the demo registry and the three mock cameras:

```bash
PIPELINE_REGISTRY=data/demo_camera_registry.json \
PIPELINE_CAMERAS=mockcam01,mockcam02,mockcam03 \
  docker compose --profile ai up -d --build pipeline

docker compose logs -f pipeline
```

Put those two `PIPELINE_*` lines in `.env` instead if you prefer — then it's
just `docker compose --profile ai up -d pipeline`.

### What you should see in the pipeline logs, within ~30–60 s

```
POST /cameras/sync -> 200 (3 cameras)
AI event  cam=mockcam01 track=1 plate=GJ18TC0450 ...
AI event  cam=mockcam02 track=1 plate=GJ18TC0450 ...
AI event  cam=mockcam03 track=1 plate=GJ18TC0450 ...
STATS | consumed=... fps=~10 | vehicles=... events=... sent=...
```

The clips loop, so events keep coming. Each clip is the **same vehicle**, so
the three cameras produce one cross-camera journey.

### Verify the full chain

Open the dashboard at **http://localhost:3000** and log in as `admin`.

1. **Alert** — a `GJ18TC0450` alert appears in the incident bar / alert list
   (priority HIGH). Also: `GET /api/v1/alerts` returns it.
2. **WebSocket** — the alert toast pops **without a page refresh** (the client
   holds a `/ws/alerts` connection via a short-lived ticket).
3. **Evidence** — open the alert → the snapshot image loads (served from MinIO,
   or the pipeline's local `evidence/` as fallback).
4. **Journey** — open the vehicle (`GJ18TC0450`) → the sightings show
   mockcam01 → mockcam02 → mockcam03 in time order, and the response carries a
   `journey` block (`distinct_cameras: 3`, `has_journey: true`)
   (`GET /api/v1/vehicles/search?plate=GJ18TC0450`).
5. **GIS** — the map draws the three mock-camera markers (around Ahmedabad,
   ~23.03–23.07 N) and a polyline connecting the journey.
6. **Live video** — each mock camera card plays its clip in the browser
   (`GET /api/v1/cameras/{id}/mock-video` streams the committed H.264 MP4).

---

## 3. Real-camera fallback

The default pipeline configuration is the **real** Sentinel cameras — nothing
about that changed:

```bash
# needs real RTSP credentials in .env (SENTINEL_RTSP_USERNAME / _PASSWORD)
docker compose --profile ai up -d pipeline
# default: PIPELINE_REGISTRY=data/camera_registry.json, PIPELINE_CAMERAS=cam04,cam06
```

Or bare-metal:

```bash
.venv/bin/python scripts/run_pipeline_service.py --cameras cam04,cam06 --no-backend --duration 60
```

### Honest expectation on real feeds

On the real Sentinel feeds we have access to (`cam04`, `cam06`), the pipeline
**detects and tracks vehicles correctly but reads no plates** — every event is
emitted as `plate=UNKNOWN`. These are wide-area surveillance feeds; the plates
are too small / blurred / oblique to resolve, and the pipeline is deliberately
built to report `UNKNOWN` rather than guess (**zero hallucinated plates**).

So the *readable-plate → alert → journey* chain is demoed on the curated mock
clips (§2). The real feeds demonstrate the ingestion + detection + tracking +
evidence + observability path with honest `UNKNOWN` reads. This is covered in
detail in `README.md` §3d and `SUBMISSION_REQUIREMENTS.md` §2.

---

## 4. Troubleshooting & recovery

| Symptom | Fix |
| :--- | :--- |
| `docker compose up` fails on a port | Set the clashing `*_HOST_PORT` in `.env`, `docker compose down`, retry. |
| Backend never healthy | `docker compose logs backend`. Usually Postgres still starting — it retries. Hard reset: `docker compose down -v && docker compose up -d --build`. |
| Watchlist empty after `up` | Confirm `SEED_WATCHLIST_PLATE` is not set to empty in `.env`. Re-run the seed: `docker compose exec backend python /scripts/seed_db.py`. |
| Pipeline: `camera(s) not in registry, skipped` | `PIPELINE_REGISTRY` didn't take. Pass it inline (§2) or check `.env`. Confirm the file exists: `docker compose exec pipeline ls data/demo_camera_registry.json`. |
| Pipeline: clip not found / `VideoCapture` fails | `docker compose exec pipeline ls demo_assets/clips/`. The clips are committed and also mounted read-only; if empty, the bind mount path is wrong — check `./demo_assets` exists in the repo root. |
| No `GJ18TC0450` events, only `UNKNOWN` | You're pointed at the real registry, not `data/demo_camera_registry.json`. Check the pipeline's startup log line listing the cameras and their sources. |
| Alert fires but no WebSocket toast | Browser console for `/ws/alerts` errors. The ticket is ~60 s TTL — a very slow first load can miss it; refresh the dashboard. |
| Mock video card doesn't play | `curl -s -o /dev/null -w '%{content_type}\n' "localhost:8000/api/v1/cameras/<id>/mock-video?token=<media-ticket>"` should say `video/mp4`. The committed clips are H.264 baseline/high, which every modern browser plays. |
| Evidence image 404 | MinIO not healthy, or snapshot upload failed — the backend falls back to `EVIDENCE_ROOT` (`/evidence`). Check `docker compose logs minio` and `docker compose exec backend ls /evidence`. |
| Start completely over | `docker compose --profile ai down -v` then repeat §1. `-v` wipes the Postgres and MinIO volumes; the next `up` re-seeds. |

### Useful commands

```bash
docker compose ps
docker compose logs -f backend
docker compose logs -f pipeline
docker compose exec backend python /scripts/seed_db.py      # re-seed (idempotent)
docker compose exec pipeline ls data demo_assets/clips      # verify demo assets in-container
curl -s localhost:8000/api/v1/dashboard/health -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

---

## 5. What is and isn't reproducible from a fresh clone

**Reproducible with nothing but the repo + Docker:**

- Full core stack, migrations, admin seed, `GJ18TC0450` watchlist seed.
- The mock ANPR demo (§2): committed clips → `GJ18TC0450` reads → alert →
  WebSocket → evidence → journey → GIS.
- Browser playback of the mock camera clips.

**Needs assets / access not in the repo:**

- Real Sentinel camera feeds — need RTSP credentials (and network reach to the
  RTSP server) in `.env`.
- The large `trafficdataset/` mock corpus and `demo_assets/mock_videos/*.avi`
  raw clips — git-ignored, machine-local. The small `demo_assets/clips/*.mp4`
  used by this runbook are the committed, portable subset.
- A labelled plate dataset for real ANPR accuracy benchmarking — does not
  exist locally (see `SUBMISSION_REQUIREMENTS.md` §2).
