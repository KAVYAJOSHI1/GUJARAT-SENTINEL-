# Pre-Push Validation — `penultimate`

**Date:** 2026-09-04
**Branch under test:** `penultimate` @ `9807557`
**Task:** validation only — nothing pushed, no branches modified, no code changed.

---

## RECOMMENDATION: ✅ SAFE TO PUSH

The two merges are structurally sound, introduce **no regressions**, lose **no
functionality**, and leave `main` and both source branches untouched. Every
`FAILURE`-class problem searched for was absent. The remaining issues are all
either **environmental** (Docker daemon down; live DB/PostGIS/MinIO not running)
or **pre-existing cross-branch gaps** that are present on the source branches
themselves and were not created by this integration.

`penultimate` is an integration branch, not `main` — pushing it for team review
is appropriate. See "Follow-up before this stack is demo-ready" at the end.

> One untracked file exists in the working tree: **`report.md`** (and this file,
> `PRE_PUSH_VALIDATION.md`) — validation artifacts generated on request. They are
> untracked and will **not** be pushed unless you `git add` them.

---

## 1. Git state

```
$ git status
On branch penultimate
Your branch is ahead of 'origin/penultimate' by 38 commits.
Untracked files:  report.md
nothing added to commit but untracked files present

$ git rev-list --left-right --count origin/penultimate...penultimate
0    38          # 0 behind, 38 ahead — never pushed, nothing to pull
```

| Branch | Local | `origin/…` | Verdict |
|---|---|---|---|
| `penultimate` | `9807557` | `dd48630` | 38 ahead / 0 behind — **local only, not pushed** |
| `feature/vanshal-backend` | `ce8a309` | `ce8a309` | **SAME — untouched** |
| `feature/vishakha-investigation` | `5134f3e` | `5134f3e` | **SAME — untouched** |
| `main` | `dd48630` | `dd48630` | **SAME — nothing merged, nothing pushed** |

`git reflog --all` shows **only** two operations on `penultimate` (the two merge
commits) and the creation of the two local helper branches straight from their
`origin/…` refs. **No commits were ever created on any source branch or on
`main`.** Working tree is clean apart from the untracked report files.

---

## 2. The two merges

```
$ git rev-list --parents -n 1 99b7635
99b7635  dd48630  ce8a309      # parent1 = penultimate tip, parent2 = vanshal tip ✓

$ git rev-list --parents -n 1 9807557
9807557  99b7635  5134f3e      # parent1 = merge-1 commit, parent2 = vishakha tip ✓

$ git merge-base --is-ancestor ce8a309 penultimate   → true   (vanshal IS an ancestor)
$ git merge-base --is-ancestor 5134f3e penultimate   → true   (vishakha IS an ancestor)
```

| Merge commit | `--stat` summary |
|---|---|
| `99b7635` `Merge branch 'feature/vanshal-backend'` | 78 files, **+5,664 / −3** (the −3: `.gitignore` union, `docker-compose.yml` restore, `README.md` kept-ours) |
| `9807557` `Merge branch 'feature/vishakha-investigation'` | 55 files, **+7,295 / −0** |

Combined vs `main`: **132 files changed, +12,959 / −3.**

---

## 3. No functionality lost

Tree-level comparison of the integrated branch against each source branch, on the
functional paths:

```
$ git diff --stat feature/vanshal-backend    HEAD -- backend/ database/ ai/ \
                                                     ingestion/ scripts/ tests/ \
                                                     requirements-ai.txt data/
  (empty — byte-identical)

$ git diff --stat feature/vishakha-investigation HEAD -- frontend/ "GujaratPoliceDashboard (2).jsx"
  (empty — byte-identical)
```

Every functional file from both branches is present **verbatim** — the merges
were "clean" mechanically, with conflicts confined to root docs/config only.

### Entry-point / import inspection (not just file existence)

| Area | Check | Result |
|---|---|---|
| Backend | `from app.main import app` (cwd `backend/`) | **OK** |
| Backend routers | aggregated once in `app/api/v1/__init__.py`; `main.py` includes `api_router` + `ws_router` once each | **OK — no duplicate routes** (verified programmatically, see §5) |
| Backend models | `from app.models import User, Camera, VehicleEvent, Alert, Watchlist, AuditLog` | **OK** (6 tables) |
| Backend schemas | `app.schemas.{alert,auth,camera,common,event,vehicle}` | **OK** |
| Backend config | `app.config.settings` loads; `APP_NAME`, `API_V1_PREFIX=/api/v1`, `DATABASE_URL` present | **OK** |
| Backend DB | `app.database` engine builds (dialect: `postgresql`) — no connection attempted | **OK (static)** |
| Alembic | `alembic -c database/alembic.ini history` / `heads` → single head `0001` | **OK** |
| AI | imports of `vehicle_detector, plate_locator, preprocess, consensus, ocr_engine, normalizer, rtsp_adapter, frame_interface, pipeline` | **OK** |
| Ingestion | imports of `catalogue_ingest, stream_manager, reconnect, stream_health, models, config` | **OK** |
| Frontend | `App.jsx` route table (5 routes + catch-all), all relative imports resolve, `npm run build` | **OK** (build passes, §7) |

---

## 4. Python environment & dependencies

```
$ python --version   → Python 3.11.9
$ pip --version      → pip 26.1.2
```

### Required dependency sets

| Subsystem | Source of truth | Notes |
|---|---|---|
| Backend API | `backend/requirements.txt` (14 pinned pkgs: fastapi, uvicorn, sqlalchemy, sqlmodel, geoalchemy2, psycopg2-binary, alembic, minio, python-jose[cryptography], passlib[bcrypt], pydantic, pydantic-settings, python-multipart, websockets) | — |
| AI pipeline | `requirements-ai.txt` (numpy, opencv-python, **ultralytics**, **torch**, requests, fastapi, uvicorn; paddleocr/easyocr commented-out optional) | torch already present in env |
| Ingestion | subset of `requirements-ai.txt` (opencv, numpy, requests, fastapi, uvicorn) | — |
| Tests | union of the above (`tests/test_ai_pipeline.py` needs ultralytics+cv2+numpy; `tests/test_camera_registry.py` needs only stdlib) | — |

### What was installed (missing packages only, additive — nothing upgraded/downgraded)

Installed at the **exact pins** from `backend/requirements.txt` (they were entirely absent):
`sqlmodel==0.0.22`, `geoalchemy2==0.15.2`, `minio==7.2.9`,
`python-jose==3.3.0`, `passlib==1.7.4` (+ transitive: bcrypt, ecdsa,
pycryptodome, argon2-cffi).

Installed for AI: `ultralytics==8.4.138` (`>=8.3` per file; + polars, thop).

**No committed dependency file was modified. No package versions were changed to
make anything pass.** `pip install -r backend/requirements.txt` was deliberately
**not** run, because the environment already carries newer versions of the
shared libs (see WARNING W3) and forcing the pins would have downgraded the
user's global environment.

### Re-run results

```
$ python -m pytest -q
...................                                    19 passed in 25.59s

$ cd backend && python -c "from app.main import app; print('Backend import OK')"
Backend import OK
```

Both previously-BLOCKED items now **PASS**.

---

## 5. Backend validation

`app` imports; all routers registered exactly once; **no duplicate route
definitions** (checked with a `Counter` over `(methods, path)` tuples → `[]`).

### Registered routes

| Method | Path |
|---|---|
| POST | `/api/v1/auth/login` |
| GET | `/api/v1/cameras` |
| GET | `/api/v1/cameras/geojson` |
| GET | `/api/v1/cameras/{camera_id}` |
| POST | `/api/v1/cameras` |
| PATCH | `/api/v1/cameras/{camera_id}` |
| DELETE | `/api/v1/cameras/{camera_id}` |
| POST | `/api/v1/events/ai-detection` |
| GET | `/api/v1/vehicles/search` |
| GET | `/api/v1/alerts` |
| PATCH | `/api/v1/alerts/{alert_id}` |
| GET | `/api/v1/watchlist` |
| POST | `/api/v1/watchlist` |
| DELETE | `/api/v1/watchlist/{watchlist_id}` |
| WS | `/ws/alerts` |
| GET | `/health` |
| GET | `/docs`, `/redoc`, `/openapi.json` |

- **Models / schemas / config:** import cleanly (§3 table).
- **Database config:** `settings.DATABASE_URL` resolves; SQLAlchemy engine
  constructs (PostgreSQL dialect). No live DB required or attempted for import
  validation.
- **Alembic config:** valid — `script_location=migrations`, `prepend_sys_path=.`,
  `env.py` pulls `settings.DATABASE_URL` and `SQLModel.metadata`; `alembic
  history`/`heads` list a single head `0001` ("cameras, vehicle_events,
  watchlist, alerts, users, audit_logs"); migration file parses.
- **Auth:** `get_current_user` uses `OAuth2PasswordBearer(auto_error=True)` — all
  `/api/v1/*` routes except `/auth/login` **enforce** a JWT and return 401
  without one.
- **Env vars documented:** `backend/.env.example` (20 keys) + root `.env.example`
  + `docker-compose.yml` `environment:` block. `app/config.py` provides defaults
  for all of them.

Live PostgreSQL/PostGIS/MinIO were **not** started; DB-touching request behaviour
(actual queries, migration apply) is **BLOCKED** (B2), not failing.

---

## 6. AI & ingestion validation

| Component | Import | Init | Notes |
|---|---|---|---|
| `VehicleDetector` (YOLOv8) | **OK** | **OK** | `ai/weights/yolov8n.pt` present locally (6.5 MB, git-ignored). `detect()` on a blank 640² frame returns `[]` cleanly. |
| `PlateLocator` | OK | OK | — |
| `ImagePreprocessor` | OK | OK | — |
| `MultiFrameConsensus` | OK | OK | — |
| `OCREngine` | OK | OK | paddleocr/easyocr absent → logs the documented warning and activates the **contour-OCR fallback**. Not an error. |
| `PlateNormalizer` | OK | OK | — |
| `RTSPStreamAdapter` / `FrameInput` | OK | (exercised by tests) | — |
| `AIPipeline` | OK | — | — |
| `StreamManager` / `StreamWorker` | OK | — | — |
| `ReconnectSupervisor` (`ingestion/reconnect.py`) | OK | — | — |
| `HealthRegistry` (`ingestion/stream_health.py`) | OK | **OK** | `HealthRegistry(window_size=60)` constructs. |
| `data/camera_registry.json` | — | — | valid JSON, **30 camera entries** (matches `test_camera_registry.py` expectations). |

```
$ python -m pytest -q      →  19 passed
```

- `paddleocr` / `easyocr` are **optional** (commented out in `requirements-ai.txt`)
  and the code path degrades gracefully — reported, not treated as a failure.
- No models were downloaded on purpose; `yolov8n.pt` was already resolvable
  locally, so `VehicleDetector` could be fully instantiated and exercised.

---

## 7. Frontend validation

```
$ cd frontend && npm ci        → OK (clean install from committed lockfile)
$ npm run build                → ✓ built in 13.13s
                                 vite v5.4.21, 2087 modules transformed
                                 dist/index.html + 5 asset chunks emitted
```

Only warning: one chunk > 500 kB (`index-*.js` 826 kB) — a bundle-size advisory,
**pre-existing**, present identically on the source branch.

| Check | Result |
|---|---|
| Broken imports / unresolved modules | none — build resolves all 2087 modules |
| `vite.config.js` | valid — dev server `:3000`, proxies `/api → :8000` and `/ws → ws://:8000`, `build.outDir=dist`, sourcemaps on |
| `package.json` scripts | `dev`, `build`, `preview` only |
| API base URL | `import.meta.env.VITE_API_BASE_URL || "/api/v1"` — sensible; dev relies on the Vite proxy |
| Env vars | `frontend/.env.example` documents `VITE_API_BASE_URL`, `VITE_WS_URL` (both optional, blank-by-default) |
| Routes | 5 (`/`, `/cameras`, `/alerts`, `/investigation`, `/map`) + `*` → redirect; all page components imported and exist |
| Duplicate components | none |
| Dead/unused files | `src/pages/InvestigationPlaceholder.jsx` defined but never imported (W4) |
| Test / lint / type-check config | **none exists** — no eslint/prettier/tsconfig/jest/vitest, no `test`/`lint` npm scripts. Reporting the absence, not inventing one. |

---

## 8. Frontend ↔ Backend API contract

Base path `/api/v1`. Every frontend data call is wrapped in a `safe()` /
simulator fallback, so a miss **degrades to mock data**, it does not crash the UI.

| Frontend endpoint | Method | Backend route | Status |
|---|---|---|---|
| `/cameras` | GET | `GET /api/v1/cameras` | **MATCH** |
| `/cameras/geojson` | GET | `GET /api/v1/cameras/geojson` | **MATCH** (minor: Feature `id` sits at feature level, frontend also looks in `properties`; coords/name/status align) |
| `/vehicles/search?plate=&from=&to=` | GET | `GET /api/v1/vehicles/search?plate=&limit=` | **MATCH (functional)** — response shape (`sightings[]`, `total_sightings`, `is_watchlisted`) aligns with `normalizeVehicleSearch`; `from`/`to` date params are silently ignored server-side |
| `/ws/alerts` | WS | `WS /ws/alerts` | **MATCH** |
| `/dashboard/stats` | GET | *(no route — no dashboard router)* | **MISSING** → mock stats. *Genuinely not implemented anywhere in the backend.* |
| `/alerts/recent` | GET | `GET /api/v1/alerts` (`?limit=`, ordered `created_at DESC`) | **MISMATCH (path)** — equivalent data exists at `/alerts`; frontend path 404s → mock. *Not a separate route; it's the same data under a different name.* |
| `/alerts/{id}/acknowledge` | POST | `PATCH /api/v1/alerts/{alert_id}` (body `{status}`) | **MISMATCH (method + path)** — acknowledge logic exists as a PATCH; frontend POST 404s → optimistic UI update |
| `/vehicles/evidence/{id}` | GET (as `<img src>`) | *(no route)* | **MISSING as a route.** Evidence is delivered instead via `snapshot_url` fields inside the `/vehicles/search` payload (MinIO/object-store URLs). `EvidenceModal` reads those `snapshot_url` values (works) **and** also builds a `/vehicles/evidence/{id}` URL as a fallback (won't resolve). `fetchEvidence()` handles the load error with a placeholder image. |
| `/auth/login` | *(not called — no login flow in frontend)* | `POST /api/v1/auth/login` | backend-only |

### Verdict on the three previously-flagged endpoints

- **`/vehicles/evidence/{id}`** — genuinely **not** implemented as a backend
  route. Partially covered by `snapshot_url` in search results.
- **`/dashboard/stats`** — genuinely **not** implemented (no dashboard module at all).
- **`/alerts/recent`** — **not** implemented under that path; the functionality
  is `GET /api/v1/alerts`.

**All three gaps exist on the source branches independently** (vishakha/isha
frontend was built mock-first against `docs/API_CONTRACTS.md` from the `testing`
branch; vanshal's backend implements a subset). The merge neither caused nor
worsened them. **This is a validation pass — no implementation was changed.**

> Additional pre-existing gap: the frontend `axios` instance sends **no
> `Authorization` header** and there is **no token storage or login flow**, while
> every backend data route **requires** a JWT. In a live deployment all
> authenticated calls would 401 and the UI would run entirely on mock/simulated
> data until auth is wired. (W2)

---

## 9. Docker validation

```
$ docker version         → Client 29.6.1 present
$ docker compose version → v5.3.0 present
$ docker info            → FAILS: "cannot connect ... dockerDesktopLinuxEngine
                            ... daemon [not] running"
```

| Command | Result |
|---|---|
| `docker compose config --quiet` | **PASS — compose file is valid** (only warning: obsolete top-level `version:` key) |
| `docker build -t gujarat-sentinel ./backend` | **NOT RUN — Docker daemon unavailable.** Remains **unverified**. Nothing was modified. |

### `docker-compose.yml` structure review (via rendered `docker compose config`)

| Service | Image / build | Ports | Healthcheck | Notes |
|---|---|---|---|---|
| `postgis` | `postgis/postgis:15-3.3` | `5432:5432` | `pg_isready -U sentinel -d sentinel` (5s/10) | mounts `database/init_postgis.sql` into `/docker-entrypoint-initdb.d/` ✓ |
| `minio` | `minio/minio:latest` | `9000:9000`, `9001:9001` | `mc ready local` (5s/10) | root creds `minioadmin/minioadmin` (dev placeholder) |
| `backend` | `build: ./backend` (`Dockerfile`) | `8000:8000` | — (none) | `depends_on` both services `condition: service_healthy` ✓; `env_file: ./backend/.env.example`; `DATABASE_URL` → `postgresql+psycopg2://sentinel:sentinel@postgis:5432/sentinel`; command runs **`alembic ... upgrade head` then `uvicorn app.main:app --reload`** ✓; bind-mounts `./backend` → `/app` |

Backend references PostgreSQL/PostGIS ✓, MinIO ✓, healthchecks on the data
services ✓, migrations-on-start ✓, ports ✓, env vars ✓. `Dockerfile` is a
standard `python:3.11-slim` + `gcc`/`libpq-dev` + `pip install -r
requirements.txt` — unaffected by the merge.

Minor observations (not blockers): the `backend` service has no healthcheck of
its own; `env_file` points at a file named `.env.example`; `version:` key is
obsolete.

---

## 10. Repository hygiene

| Check | Result |
|---|---|
| Conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`) in tracked tree — **including `.md`** | **none** (`git grep` over `HEAD`, all extensions) |
| `git diff --check` (working tree) | **clean** |
| `git diff main...HEAD --check` | only **trailing whitespace** in `ai/anpr/plate_locator.py`, `ai/detection/vehicle_detector.py`, `scripts/rtsp_ai_demo.py`, `tests/test_ai_pipeline.py`, `GujaratPoliceDashboard (2).jsx`, `frontend/.gitignore` — verified **byte-identical to the source branches** (e.g. `feature/vanshal-backend:ai/anpr/plate_locator.py` line 56 has the same trailing spaces; `tests/test_ai_pipeline.py` is 0-diff vs the branch). **Pre-existing, not merge-introduced.** (W5) |
| Committed `.env` / credentials / API keys / private keys | **none** — only `*.env.example` templates + `database/migrations/env.py` (Alembic, not an env file). All values in the templates are placeholders (`sentinel:sentinel`, `minioadmin`, `CHANGE_ME_IN_PRODUCTION`). |
| Secret-pattern scan (`-----BEGIN`, `AWS_SECRET`, `api_key=...`, `password=...`) over tracked non-doc files | **no matches** |
| Committed `node_modules/`, `dist/`, build output | **none** (`git ls-files` clean; `.gitignore` covers them) |
| Committed model artifacts (`*.pt`, `*.pth`, `*.onnx`) | **none** — `ai/weights/yolov8n.pt` and root `yolov8n.pt` exist on disk but are **git-ignored** (`git check-ignore` confirms) |
| Untracked in working tree | `report.md`, `PRE_PUSH_VALIDATION.md` (validation artifacts — will not be pushed unless added) |

---

## 11. Final regression assessment

### ✅ PASS — verified successfully

1. Git integrity — `penultimate` @ `9807557`; `main` and both feature branches
   byte-for-byte unchanged vs `origin`; no commits on any source branch; reflog clean.
2. Merge structure — `99b7635` parents `(dd48630, ce8a309)`; `9807557` parents
   `(99b7635, 5134f3e)`; both feature tips are ancestors of `penultimate`.
3. No functionality lost — `backend/ database/ ai/ ingestion/ scripts/ tests/
   data/ requirements-ai.txt` identical to `feature/vanshal-backend`; `frontend/`
   identical to `feature/vishakha-investigation`.
4. `python -m pytest -q` → **19 passed** (was BLOCKED).
5. Backend `from app.main import app` → **OK** (was BLOCKED).
6. Backend: routers registered once, **no duplicate routes**, 17 routes + WS +
   health; models/schemas/config/alembic all valid.
7. AI + ingestion: all modules import and initialize; YOLO detector runs;
   OCR fallback works; camera registry = 30 entries.
8. Frontend `npm ci` + `npm run build` → **PASS** (2087 modules).
9. `docker compose config` → **valid**; compose wiring (db, minio, healthchecks,
   migrations, ports, env) correct.
10. No conflict markers; no secrets, credentials, `node_modules`, build output,
    or model weights committed.

### ⏸ BLOCKED — could not be tested here (environment/services)

- **B1 — `docker build ./backend`**: Docker daemon not running. Image build
  unverified. (`docker compose config` passed; Dockerfile reviewed statically.)
- **B2 — Live runtime behaviour**: no PostgreSQL/PostGIS/MinIO instance, so actual
  DB queries, `alembic upgrade head` against a real DB, MinIO evidence storage,
  and end-to-end request/response were not exercised. Import- and config-level
  validation only.
- **B3 — `backend/requirements.txt` exact pin set**: validation ran against the
  environment's newer shared libs (see W3), not the pinned versions.

### ⚠️ WARNING — pre-existing, NOT caused by this merge

- **W1 — Frontend↔backend contract gaps**: `/dashboard/stats` (no route),
  `/alerts/recent` (data is at `/alerts`), acknowledge is `PATCH /alerts/{id}`
  not `POST /alerts/{id}/acknowledge`, `/vehicles/evidence/{id}` (no route;
  partial coverage via `snapshot_url`). All degrade to mock via `safe()`. Present
  on the source branches.
- **W2 — No frontend auth**: no token/login flow; all protected backend routes
  would 401 in a live setup → UI runs on mock data. Present on the source branches.
- **W3 — Dependency-pin drift**: `backend/requirements.txt` pins (fastapi 0.115.0,
  sqlalchemy 2.0.35, pydantic 2.9.2, alembic 1.13.2, …) are well behind the
  environment (fastapi 0.136.3, sqlalchemy 2.0.50, pydantic 2.13.4, …). Backend
  imports and routes are fine on the newer set, but the pinned set itself was not
  exercised. Pre-existing in the committed file.
- **W4 — Dead file**: `frontend/src/pages/InvestigationPlaceholder.jsx` is never
  imported. From the vishakha branch.
- **W5 — Trailing whitespace** in several `ai/`, `scripts/`, `tests/` files and
  `frontend/.gitignore`. Byte-identical to the source branches.
- **W6 — Stray root file**: `GujaratPoliceDashboard (2).jsx` (443-line prototype)
  sits at repo root. Committed on the vishakha branch (`d835b01`).
- **W7 — compose nits**: obsolete `version:` key; `env_file` points at
  `./backend/.env.example`; `backend` service has no healthcheck.

### ❌ FAILURE — integration problems introduced by the merge

**None found.**

- No conflict markers, no unresolved merges, no unmerged paths.
- No lost commits or files from either branch.
- No duplicate route/model/class definitions introduced.
- No broken imports introduced (backend imports, frontend build both pass).
- No configuration corrupted (compose valid, alembic valid, vite valid).
- The conflict resolutions (`.gitignore` union, `docker-compose.yml` restore,
  `README.md` kept-ours, `DEVELOPER_README.md` concatenation, `frontend/README.md`
  kept-theirs, `.env.example` kept-ours) are all intact and sensible.

---

## Follow-up before this stack is demo-ready (NOT push blockers)

1. Wire the frontend auth flow (login → store JWT → `Authorization: Bearer`
   header on `http`), or the UI stays on mock data. (W2)
2. Reconcile the API contract: add `GET /api/v1/dashboard/stats`, decide
   `/alerts` vs `/alerts/recent`, align acknowledge method, and either add
   `GET /api/v1/vehicles/evidence/{id}` or make the frontend use `snapshot_url`
   exclusively. (W1)
3. Run `docker build ./backend` and a full `docker compose up` once the daemon is
   available. (B1/B2)
4. Decide whether to refresh `backend/requirements.txt` pins to match a supported
   set, or pin the environment to the file. (W3)
5. Cleanup commit (separate from the merges): remove
   `InvestigationPlaceholder.jsx`, relocate/remove `GujaratPoliceDashboard (2).jsx`,
   strip trailing whitespace, drop compose `version:` key. (W4/W5/W6/W7)

---

## Appendix — commands run (validation only, no mutations)

```
git status / branch -vv / log --graph / rev-list --parents / merge-base --is-ancestor
git rev-list --left-right --count / reflog --all / diff --stat / diff --check / grep
python --version ; pip --version
pip install sqlmodel==0.0.22 geoalchemy2==0.15.2 minio==7.2.9 \
            python-jose[cryptography]==3.3.0 passlib[bcrypt]==1.7.4      # missing → pinned
pip install "ultralytics>=8.3"                                          # missing → per file
python -m pytest -q                                                     # 19 passed
python -c "from app.main import app"  (cwd backend/)                    # OK
python -c "<enumerate routes / import models,schemas,config,database>"  # OK, no dup routes
alembic -c database/alembic.ini history / heads                         # single head 0001
python -c "<import+init ai/* and ingestion/*>"                          # OK
cd frontend && npm ci && npm run build                                  # built OK
docker version / compose version / info / compose config                # config valid; daemon down
```

No `git` mutating command, no `pip` upgrade/downgrade of existing packages, no
edits to tracked files.
