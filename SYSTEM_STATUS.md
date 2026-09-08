# SENTINEL — System Status (single source of truth)

**Branch:** `penultimate` · **Last verified:** 2026-09-08 · **Verification host:** 8-core shared Linux desktop, CPU-only, Docker Compose stack.

> **2026-09-08 — Operational platform enhancement.** Added an operational
> layer on top of the existing CCTV/ANPR/watchlist/alert pipeline (which is
> unchanged): **Incident Management**, **Case Management**, **Evidence
> linking**, a read-only **Audit / Activity center**, and an operational
> **Notification center**, plus command-center wiring for all of it.
> Migration `0006` (8 new tables, additive only). Backend + demo-flow tests
> added and passing. See §A rows tagged *(2026-09-08)* and §I.

This document is the authoritative statement of what is implemented, what is
verified, what is partial, and what is future. It is deliberately conservative:
where something has not been demonstrated it is marked as such. Companion docs:
[`DEMO_RUNBOOK.md`](DEMO_RUNBOOK.md) (how to reproduce the demo),
[`SUBMISSION_REQUIREMENTS.md`](SUBMISSION_REQUIREMENTS.md) (requirement status),
[`SENTINEL_System_Audit_Report.md`](SENTINEL_System_Audit_Report.md) (full engineering audit),
[`SCALABILITY.md`](SCALABILITY.md) (measured load ladder + roadmap).

Legend: **Implemented** = code exists and is wired · **Verified** = exercised
this pass with the result recorded in §F · **Partial** = works with a stated
limit · **Future** = not present.

---

## A. WORKING / VERIFIED

Everything in this section was exercised on 2026-09-05 (commands and results in §F).

| Area | Status | Notes |
| :--- | :--- | :--- |
| **Docker / deployment** | Verified | `docker compose down -v && docker compose up --build -d` brings up postgis + minio + backend + frontend from zero volumes. Backend entrypoint runs Alembic `0001→0005` then the idempotent seed. |
| **Database** | Verified | PostgreSQL 15 + PostGIS 3.3. Migrations `0001`–`0006` apply cleanly on a fresh volume (and downgrade/upgrade round-trips). `0004` = analytics covering indexes; `0005` = `pipeline_status`; `0006` = operational layer (`incidents`, `incident_notes`, `incident_evidence`, `cases`, `case_notes`, `case_incidents`, `case_evidence`, `notifications`) — additive only, FKs + query-shaped indexes, no change to existing tables. |
| **Authentication / security** | Verified | JWT (HS256) login; RBAC (ADMIN/OFFICER/OPERATOR); login rate-limit (5 fails / 300s → 429); explicit CORS allow-list; short-lived scoped tickets for WebSocket handshake (`purpose="ws"`, ~60s) and media `<img>`/`<video>` (`purpose="media"`, ~120s) so the session JWT never rides the WS wire or a URL. |
| **Backend APIs** | Verified | `/health`, `/api/v1/auth/*`, `/api/v1/cameras` (+ `/sync`, `/geojson`, `/health`, `/{id}/mock-video`), `/api/v1/vehicles/search` (+ `/evidence/{event_id}`, `/events/recent`), `/api/v1/watchlist`, `/api/v1/alerts`, `/api/v1/incidents/*`, `/api/v1/cases/*`, `/api/v1/notifications/*`, `/api/v1/dashboard/stats` (+ `active_incidents` / `open_cases`) + `/dashboard/health`, `/api/v1/pipeline/status`, `/api/v1/analytics/*`, `/api/v1/admin/*` (+ `/admin/audit`, `/admin/users`). |
| **Camera onboarding** | Verified | `POST /api/v1/cameras/sync` upserts a catalogue keyed by external `code`; the pipeline auto-syncs its registry on start (`-> 200 (3 cameras)` for the demo registry). 30 real cameras registered in `data/camera_registry.json`. |
| **AI: YOLO detection + tracking** | Verified | YOLOv8n (`ultralytics`) + ByteTrack, one worker. On the demo clips: ~9.5 processed FPS, YOLO p50 ≈ 55 ms. On real `cam04`: vehicles detected and tracked (4 in a 90 s window). |
| **ANPR / OCR (curated clips)** | Verified | Heuristic plate locator → EasyOCR → multi-frame consensus → Gujarat-format normalisation. Reads `GJ18TC0450` reliably off all three demo clips, in Docker and bare-metal. OCR p50 ≈ 187 ms/plate (CPU). |
| **Watchlist / alerts** | Verified | Seeded `GJ18TC0450` (category "Stolen Vehicle (demo)", HIGH). Every matching event raises an `Alert`; `app/services/cooldown.py` suppresses duplicates for the same (plate, camera) within `ALERT_COOLDOWN_SECONDS` (default 300). 4 alerts raised across the demo run (1 per camera + 1 after cooldown). |
| **WebSocket** | Verified | `/ws/alerts` requires the scoped ticket as a subprotocol; rejects before `accept()` without it. A live `{"type":"ALERT","plate_number":"GJ18TC0450",...}` frame was received on an authenticated client when a post-cooldown alert fired. |
| **Evidence** | Verified | Per-event snapshot uploaded to MinIO; `GET /api/v1/vehicles/evidence/{event_id}` returned `image/jpeg` (176 KB, 810×1080) via the scoped media ticket. Local-disk (`EVIDENCE_ROOT`) fallback exists for snapshots that never reached MinIO. |
| **Vehicle investigation / journey** | Verified | `GET /api/v1/vehicles/search?plate=GJ18TC0450` → `total_sightings`, `is_watchlisted: true`, ordered `sightings` (mockcam01→02→03), and a derived `journey` block (`distinct_cameras: 3`, `has_journey: true`, `span_seconds`). |
| **GIS** | Verified | `GET /api/v1/cameras/geojson` returns a PostGIS FeatureCollection (3 demo cameras at 23.03/23.05/23.07 N with live status); sightings carry lat/long for the map polyline. |
| **Mock / demo pipeline** | Verified | Committed H.264 clips `demo_assets/clips/mockcam0{1,2,3}.mp4` + tracked `data/demo_camera_registry.json` (repo-relative paths) + `PIPELINE_REGISTRY` / `PIPELINE_CAMERAS` env → the whole demo runs in Docker from a fresh clone. |
| **Mock video in browser** | Verified | `GET /api/v1/cameras/{id}/mock-video` streams the committed clip as `video/mp4`; the file is standard H.264/MP4 and decodes cleanly (playable in any modern browser `<video>`). |
| **Observability** | Verified | `GET /api/v1/dashboard/health` — DB probe (latency), camera effective-status counts, AI-pipeline freshness (`online`/`stale`/`unknown` from the `pipeline_status` push), event-flow freshness, alert counts. Every field a live measurement or `NULL`. Pipeline stale threshold now `PIPELINE_STALE_AFTER_S` (default 30 s = 3× the 10 s push interval). |
| **Frontend build** | Verified | `npm run build` succeeds; `dist/` produced. (Large-bundle warning only.) |
| **Incident management** *(2026-09-08)* | Verified | `POST /api/v1/incidents` promotes an alert (or a manual observation) into an `incidents` row that links back to the alert / vehicle_event / camera by FK — no denormalised copies. Assign, status lifecycle (`NEW→ACKNOWLEDGED→INVESTIGATING→RESOLVED→CLOSED`) with `acknowledged_by/at` + `resolved_by/at` stamps, officer remarks, evidence links. Backend-filtered + paginated list. Every mutation audited. RBAC: view = any authenticated, mutate = ADMIN/OFFICER. Tests: `backend/tests/test_incidents.py` (9). |
| **Case management** *(2026-09-08)* | Verified | `cases` + `case_incidents` + `case_evidence` + `case_notes`. Unified detail view re-resolves every linked incident / evidence row live and derives a chronological timeline + the primary vehicle's live camera-sighting count on read. CSV case-report export (`GET /api/v1/cases/{id}/report?format=csv`). Tests: `backend/tests/test_cases.py` (8). |
| **Evidence linking** *(2026-09-08)* | Verified | `incident_evidence` / `case_evidence` are pointer rows to existing `vehicle_events` — the snapshot file is never duplicated; the frontend serves it through the existing evidence proxy + media ticket. Attach / detach audited. |
| **Audit / Activity center** *(2026-09-08)* | Verified | `GET /api/v1/admin/audit` (ADMIN only) — read-only projection over the **existing** `audit_logs` table (no second audit system), filter by action / user / resource / date / detail substring, paginated, actor username resolved. Tests: `backend/tests/test_audit_center.py` (3). |
| **Notification center** *(2026-09-08)* | Verified | `notifications` table, single writer `app/services/notifications.py` (best-effort, never blocks the caller). Rows produced **only** by real backend events — a watchlist match creating an alert, an incident/case created or assigned. Broadcast vs directed (`target_user_id`) visibility; read / read-all / unread-count. Tests: `backend/tests/test_notifications.py` (5). |
| **Demo acceptance flow** *(2026-09-08)* | Verified | Full chain — detect → watchlist match → alert → acknowledge → create incident → assign → trace vehicle (journey) → attach evidence → add remark → create case → attach incident + evidence + note → CSV case report → resolve incident → close case — is one passing end-to-end test (`backend/tests/test_demo_acceptance_flow.py`), all real persisted state. |
| **Test suites** | Verified | Backend 138 passed (112 baseline + 26 operational-layer); AI/ingestion 143 passed, 8 skipped. Counts in §F. |

---

## B. PARTIALLY WORKING

| Item | Works | Does not / limitation |
| :--- | :--- | :--- |
| **Real Sentinel camera ANPR** | RTSP Basic-auth succeeds; `cam04`/`cam06` reach `ONLINE`; frames decode; YOLO + ByteTrack run; events are generated and (with `--no-backend` off) delivered. | **No plates are read** — every real-feed event is `plate=UNKNOWN`. These are wide-area feeds; plates are too small/oblique/blurred. The pipeline is built to emit `UNKNOWN`, never a guess (zero hallucinated plates observed). |
| **`cam06` (H.265/HEVC)** | Connects, authenticates, reaches `ONLINE`. | HEVC decode is slow to first-frame on the test host; only ~7 frames in a 90 s smoke window, 0 events that run. Not a regression — no ingestion/decode code was changed this pass. |
| **Multi-worker AI (`SENTINEL_AI_WORKERS>1`)** | Code path exists (worker pool). | Measured **no throughput benefit** and, in one configuration, worse end-to-end throughput than the single-consumer path (SCALABILITY.md §4). Default is 1 worker. Do not raise it in production without re-benchmarking. |
| **Pipeline throughput (CPU)** | ~9.5 FPS total on 3 demo clips; ~1.0–1.3 FPS total across a 5–30 camera load ladder (SCALABILITY.md §3–4). | CPU-bound single consumer thread; not real-time for 30 live 25–30 FPS feeds. Adequate for the PoC and the demo. |
| **WebSocket alert payload** | Delivers `type`, `alert_id`, `plate_number`, `camera_id`/`camera_code`, `priority_level`, `created_at` live. | Its `snapshot_url` field is an absolute container path (`/repo/evidence/live/...`), not a fetchable URL. The UI uses the REST evidence proxy (`/api/v1/vehicles/evidence/{event_id}`, verified working) instead, so this is cosmetic. |
| **`SEED_WATCHLIST_*`** | Seeds one demo plate idempotently on first boot. | Single plate only; not a bulk watchlist import path. |
| **Analytics endpoints** | Implemented and covered by backend tests. | Not re-exercised against live demo data this pass beyond the test suite. |

---

## C. NOT WORKING / BLOCKED

| Item | Reason | Impact |
| :--- | :--- | :--- |
| Real-camera end-to-end **readable-plate** demo | No real feed available to us produces a resolvable plate; no labelled dataset exists locally. | The "plate → alert → journey" story is demoed on curated mock clips, not live Sentinel feeds. Documented openly in `DEMO_RUNBOOK.md` §3 and `README.md` §3d. |
| ANPR accuracy **statistics** | No real labelled plate dataset. | Cannot state a real-camera accuracy number. Synthetic-font eval (`scripts/evaluate_anpr.py`) gives 87.5% exact / 98.3% char on 24 rendered plates — explicitly out-of-distribution, not a CCTV figure. |

No other component was observed failing this pass.

---

## D. NOT YET IMPLEMENTED

Operational-layer follow-ups (the 2026-09-08 phase deliberately scoped to a
coherent core — incidents / cases / evidence links / audit view /
notifications — and left these for a later pass; nothing below is started):

- **Unified advanced search** screen (one interface across plate / camera / department / date / severity / watchlist category / incident / case / confidence / real-mock with sortable, paginated results). Today: the existing per-domain searches (vehicle search, incident list filters, case list filters, audit filters) each work but are separate.
- **Watchlist management** upgrade — effective/expiry dates in the UI, bulk CSV import/export, expired-entry indication, category taxonomy. Backend watchlist model already has `expires_at` + `active` and the engine enforces them; the management UI is still add/list/deactivate only.
- **User / role / department administration** screens. `GET /api/v1/admin/users` (read-only, for assignment dropdowns) was added; full CRUD + department/region association is not.
- **Camera management** UI upgrade (edit metadata, maintenance mode, per-camera recent incidents/detections panels).
- **Alert workflow** escalation state + configurable per-rule cooldown (current alert model is `NEW/ACKNOWLEDGED/RESOLVED`; incidents carry the richer lifecycle).
- **Reports section** (8 named report types with date/camera/department/severity filters, PDF+CSV). Today: vehicle-journey PDF/CSV (existing) + case-report CSV (new).
- **GIS operations** layer toggles for incidents / case locations and camera-status/severity/date filters on the map.
- **System notification** types for camera-offline / camera-recovered / AI-pipeline-offline / storage-warning (would need a background state-diff watcher). Current notifications are event-driven only (watchlist match, incident/case created + assigned).

Pre-existing gaps:

- Visual vehicle **re-identification** (matching the same vehicle across cameras with no readable plate). Cross-camera correlation is plate-string only.
- Trained / fine-tuned **plate-region detector** and **Indian-plate OCR head** (current locator is classical CV; OCR is stock EasyOCR).
- Bulk watchlist import / management UI beyond the single seed plate.
- Broader vehicle-class handling — auto-rickshaws / three-wheelers are detected less reliably (class set + plate-aspect prior tuned for cars and two-wheelers).
- Append-only / immutable audit trail (a normal audit table exists; it is not tamper-evident).
- Encryption at rest for evidence; RS256 JWTs; distributed (cross-process) rate limiting.
- Any distributed-infrastructure component (see §E).

---

## E. FUTURE / PRODUCTION ROADMAP

Explicitly **not built** — target design only (see `SCALABILITY.md`, which is labelled a roadmap at the top of the file):

- **GPU acceleration** for YOLO + OCR (`device="cpu"` is hardcoded today).
- **Scalable multi-worker / edge architecture** — per-camera edge inference, horizontal backend scaling.
- **Message queues** — Kafka / Redis Streams between ingestion, AI, and backend (currently in-process queues).
- **Kubernetes / HA deployment** — no manifests, no replicas; single `docker-compose.yml`.
- **Observability stack** — Prometheus / Grafana / OpenTelemetry (today: one aggregate `/dashboard/health` endpoint + structured logs).
- **Database partitioning / read replicas** for `vehicle_events` at statewide volume.
- **Trained ANPR models** + a **real labelled ANPR dataset** for benchmarking.
- **Visual Re-ID** embedding model.
- **TLS termination, encryption at rest, RS256 signing, distributed rate limiting.**
- **Production-scale 30+ camera live AI processing** in real time (current CPU throughput is ~1 FPS aggregate on the test host).

---

## F. VERIFIED TEST RESULTS (2026-09-05)

### Automated suites

| Suite | Command | Result |
| :--- | :--- | :--- |
| Backend | `cd backend && DATABASE_URL=…/sentinel_test pytest -q` | **138 passed** (~59 s) — 112 baseline + 26 operational-layer (`test_incidents` 9, `test_cases` 8, `test_notifications` 5, `test_audit_center` 3, `test_demo_acceptance_flow` 1) |
| Backend on **migrated** schema | `DATABASE_URL=…/sentinel_migtest` (alembic `upgrade head`) `pytest test_incidents test_cases test_notifications test_audit_center test_demo_acceptance_flow` | **26 passed** — app runs identically on a migration-built DB, not just `create_all` |
| Migration round-trip | `alembic upgrade head` on empty DB, then `downgrade 0005` → `upgrade head` | **OK** — `0001…0006`, 8 new tables, `alembic check` shows no drift on the new tables |
| AI / ingestion | `.venv/bin/python -m pytest tests/ -q` | **143 passed, 8 skipped** (~52 s) — unchanged (events ingest only gained a best-effort notification write) |
| Frontend build | `cd frontend && npm run build` | **OK** — `dist/` built (~5 s) |

### Fresh-volume Docker

```
docker compose --profile ai down -v
docker compose up -d --build
```
- Alembic: `0001 → … → 0006` applied on empty volume (entrypoint runs `alembic upgrade head`).
- Seed: `created user 'admin' (ADMIN)` · `created watchlist entry 'GJ18TC0450'`.
- `GET /health` → `{"status":"ok"}`.

### Dockerized mock ANPR chain

```
PIPELINE_REGISTRY=data/demo_camera_registry.json \
PIPELINE_CAMERAS=mockcam01,mockcam02,mockcam03 \
  docker compose --profile ai up -d pipeline
```

| Step | Result |
| :--- | :--- |
| Clip resolution | `mockcam01/02/03 -> /repo/demo_assets/clips/mockcam0N.mp4` |
| Registry sync | `POST /cameras/sync -> 200 (3 cameras)` |
| OCR | `EasyOCR ready`; `torchvision::nms` error **resolved** (CPU torch+torchvision pinned to matching builds) |
| Plate reads | `AI event cam=mockcam01 plate=GJ18TC0450`, `…mockcam02…`, `…mockcam03…` |
| Pipeline metrics | processed_fps ≈ 9.5 · YOLO p50 55 ms / p95 94 ms · OCR p50 187 ms / p95 580 ms · events_generated == events_delivered · 0 dropped |
| Alerts | 4 × `GJ18TC0450` HIGH NEW (`/api/v1/alerts`) |
| Dashboard health | `ai_pipeline.status: "online"`, `events.readable_last_15min: 3`, `events.unknown_last_15min: 0`, `cameras.online: 3` |
| WebSocket | live `{"type":"ALERT","plate_number":"GJ18TC0450","camera_code":"mockcam01","priority_level":"HIGH"}` frame received on an authenticated client |
| Evidence | `GET /api/v1/vehicles/evidence/{event_id}` → `image/jpeg`, 176 KB, 810×1080 (from MinIO) |
| Journey | `GET /api/v1/vehicles/search?plate=GJ18TC0450` → `total_sightings` ≥ 3, `is_watchlisted: true`, `journey.distinct_cameras: 3`, `journey.has_journey: true`, sightings ordered mockcam01→02→03 |
| GIS | `GET /api/v1/cameras/geojson` → 3 features at (72.58,23.03)/(72.60,23.05)/(72.62,23.07), status ONLINE |
| Mock video | `GET /api/v1/cameras/{id}/mock-video` → `video/mp4`, 497 728 B, decodes cleanly |

### Real camera smoke (`.venv` bare-metal, RTSP creds from `.env`, `--no-backend`, 90 s)

```
.venv/bin/python scripts/run_pipeline_service.py --cameras cam04,cam06 --no-backend --duration 90
```

| Camera | RTSP auth | Status | Frames | Vehicles | Events | Plate result |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `cam04` (H.264) | OK (reconnect 21 s) | ONLINE | ~43 | 4 | 1 | **`UNKNOWN`** |
| `cam06` (H.265) | OK (reconnect 27 s) | ONLINE | ~7 | 0 | 0 | — (too few HEVC frames in window) |

No hallucinated plates. This is the documented, honest real-feed behaviour.

### Benchmarks (from earlier phases, not re-run this pass)

- Load ladder 5/10/20/30 cameras, 1 worker: total ~1.0–1.3 processed FPS, single-consumer-thread bound (`SCALABILITY.md` §3–4, `README.md` §3b).
- DB: analytics covering indexes added in migration `0004`; `scripts/db_benchmark.py` is the harness.

---

## G. KNOWN DEMO LIMITATIONS

1. **The readable-plate story uses mock data.** `demo_assets/clips/*.mp4` are curated clips containing a synthetic `GJ18TC0450` plate. They are **not** a live government feed and the UI always badges mock cameras as `MOCK`. Real Sentinel feeds (`cam04`, `cam06`) produce `UNKNOWN` plates — see §B/§C.
2. **CPU throughput.** OCR is ~187 ms/plate and total pipeline throughput is ~1 FPS aggregate across many cameras on the test host. The demo runs 3 looping 20 s clips, which is well within that budget; a 30-camera live deployment is not.
3. **First Docker build is heavy.** The pipeline image pulls torch + easyocr + ultralytics (~2.9 GB image, CPU-only). Allow time on first `--profile ai` build.
4. **Alert cooldown.** After the first alert for a (plate, camera), the next is suppressed for `ALERT_COOLDOWN_SECONDS` (300 s default) — a live WebSocket demo either shows the first burst or waits out the cooldown.
5. **`cam06`/HEVC** needs a longer warm-up than a 90 s smoke test to produce steady frames.

---

## H. HACKATHON REQUIREMENT STATUS

| Requirement | Status | Evidence / caveat |
| :--- | :--- | :--- |
| Onboard ~50 CCTV feeds | **PARTIAL** | `POST /api/v1/cameras/sync` + 3-shape catalogue parser; 30 real cameras registered. Not load-tested at 50 concurrent live feeds. |
| Live RTSP streams | **VERIFIED** | `cam04`/`cam06` authenticate and reach ONLINE; TCP-forced; reconnect/backoff. |
| Vehicle detection | **VERIFIED** | YOLOv8 + ByteTrack on both mock and real feeds. |
| ANPR / plate reading | **PARTIAL** | Verified on curated clips (`GJ18TC0450`). Real feeds → `UNKNOWN`; no accuracy benchmark. |
| Cross-camera tracking / journey | **VERIFIED** (plate-based) | `journey` block across 3 cameras. Visual Re-ID **NOT IMPLEMENTED**. |
| Real-time watchlist alerts | **VERIFIED** | Match → `Alert` → cooldown-deduped → WebSocket push. |
| GIS visualisation & trajectory | **VERIFIED** | PostGIS GeoJSON + ordered geolocated sightings. |
| Evidence capture | **VERIFIED** | MinIO snapshot + signed retrieval; disk fallback. |
| Command-center observability | **VERIFIED** | `/dashboard/health` live aggregate. |
| Statewide scale / distributed infra | **NOT IMPLEMENTED** | Roadmap only (`SCALABILITY.md`). |
| Encryption at rest / RS256 / immutable audit | **NOT IMPLEMENTED** | HS256, standard storage, normal audit table. |

Do not claim compliance beyond the "VERIFIED" rows.

---

## I. OPERATIONAL LAYER (2026-09-08)

### Data model (migration `0006`, additive only)

| Table | Purpose | Key FKs |
| :--- | :--- | :--- |
| `incidents` | alert (or manual obs.) promoted to tracked work | `alert_id → alerts`, `vehicle_event_id → vehicle_events`, `camera_id → cameras`, `*_user_id → users` |
| `incident_notes` | officer remarks (append-only in UI) | `incident_id`, `author_user_id` |
| `incident_evidence` | pointer: a `vehicle_events` row attached as evidence | `incident_id`, `vehicle_event_id` (unique pair) |
| `cases` | investigation folder | `*_user_id → users` |
| `case_notes` | officer notes | `case_id`, `author_user_id` |
| `case_incidents` | link: incident ↔ case | `case_id`, `incident_id` (unique pair) |
| `case_evidence` | pointer: `vehicle_events` row attached to a case | `case_id`, `vehicle_event_id` (unique pair) |
| `notifications` | operational events for the control room | `target_user_id → users` (NULL = broadcast) |

Enums: `incidentstatus`, `casestatus`, `notificationseverity` (new); `prioritylevel` reused.
`incident_number` / `case_number` are `PREFIX-YYYY-NNNN`, generated from a per-year count, UNIQUE.

### Synchronisation rule (enforced)

Operational rows never copy mutable alert / vehicle / camera state — they
store foreign keys and (for the vehicle of interest) the normalised plate
string. Detail views re-resolve live rows and derive counts / journeys /
timelines on read. So: changing an alert or acknowledging it does not
desync its incident; a case's linked incident relationship is a persisted
row; evidence stays a pointer to the one `vehicle_events` row and is served
through the existing MinIO/proxy path — no file duplication.

### Security / RBAC

- New endpoints all require a valid JWT (`get_current_user`).
- Mutations on incidents & cases require `ADMIN` or `OFFICER` (`require_roles`); `OPERATOR` is read-only. Frontend also hides mutation controls via `canManageOps()` (cosmetic; backend is the enforcement).
- `GET /api/v1/admin/audit` is `ADMIN`-only. `GET /api/v1/admin/users` is `ADMIN`/`OFFICER` (assignment dropdowns) and never returns password hashes.
- Every privileged mutation writes an `audit_logs` row (`INCIDENT_CREATE/UPDATE/STATUS/ASSIGN/NOTE_ADD/EVIDENCE_ADD/EVIDENCE_REMOVE`, `CASE_CREATE/UPDATE/ASSIGN/NOTE_ADD/INCIDENT_ADD/INCIDENT_REMOVE/EVIDENCE_ADD/EVIDENCE_REMOVE/REPORT_EXPORT`).
- No secrets added to source. No existing security control weakened.

### Frontend

New routes under the existing dark command-center shell: `/incidents`,
`/incidents/:id`, `/cases`, `/cases/:id`, `/system` (notification center +
system health), `/admin` (audit log, ADMIN only). Navbar gains those tabs +
a bell with unread count. "Create incident" appears on real (non-simulated)
alert cards. Dashboard gains *Active Incidents* / *Open Cases* stat cards,
quick actions, and *Live Incidents* / *Recent Cases* panels. All new API
calls degrade to an explicit error/empty state — no mock fallback rows.

### Not done this phase

See §D "Operational-layer follow-ups".
