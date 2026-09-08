# SENTINEL — System Status (single source of truth)

**Branch:** `penultimate` · **Last verified:** 2026-09-08 · **Verification host:** 8-core shared Linux desktop, CPU-only, Docker Compose stack.

> **2026-09-08 — Operational platform enhancement.** Added an operational
> layer on top of the existing CCTV/ANPR/watchlist/alert pipeline (which is
> unchanged): **Incident Management**, **Case Management**, **Evidence
> linking**, a read-only **Audit / Activity center**, and an operational
> **Notification center**, plus command-center wiring for all of it.
> Migration `0006` (8 new tables, additive only). Backend + demo-flow tests
> added and passing. See §A rows tagged *(2026-09-08)* and §I.
>
> **2026-09-08 — Phase 13: hackathon readiness & polish.** No new major
> feature and no migration. **Journey Intelligence** — the vehicle journey
> now returns explicit CONFIRMED (observed) sightings chained by INFERRED
> camera-to-camera transitions carrying time gap, and — only when both
> cameras are geolocated — great-circle distance and a plausibility-checked
> estimated speed (never fabricated). A lightweight **Camera Management
> console** (`/cameras/manage`) — table over the existing `/cameras` data
> with REAL/MOCK, effective health, last heartbeat and last detection; no
> credential handling. `/cameras` + `/vehicles/search` now expose `is_mock`
> (naming-convention derived) and `last_detection_at`. NL-search interpreted
> filters shown as human chips; Reports gained a client-side **PDF** option
> (CSV unchanged); command-center **AI Anomalies** KPI; per-route browser
> tab titles; `./scripts/reset_demo.sh` one-command demo reset. New docs:
> `docs/HACKATHON_DEMO_RUNBOOK.md` (2-minute script), `HACKATHON_ARCHITECTURE.md`,
> `GOVERNMENT_FEED_READINESS.md`, `SCALE_TO_80000.md`. See §A rows tagged
> *(Phase 13)* and §L.
>
> **2026-09-08 — Phase 12: AI intelligence layer.** Added an
> **Investigation Copilot** (natural-language questions → deterministic
> parse → validated tools → grounded answer), **natural-language CCTV
> search** (extends the existing Advanced Search), **AI incident/case
> summaries**, and **stopped-vehicle anomaly detection** (feeds the
> existing alert workflow). Deterministic-first — **no external LLM
> required**; an optional OpenAI provider only re-words answers. Migration
> `0008` (`anomaly_events` table + `alerts.source`/nullable `watchlist_id`).
> An **offline demo seed** makes it all demonstrable from `docker compose
> up`. See §A rows tagged *(Phase 12)*, §K, and `docs/AI_*.md`.
>
> **2026-09-08 — Phase 11: advanced operational features.** Added
> **Unified Advanced Search** + **Global Quick Search**, **Saved
> Investigations**, an **Advanced Watchlist Management** console (CSV
> import/export, effective/expiry windows), **Alert Escalation** workflow,
> **Incident & Case timelines** (derived from audit + linked rows),
> **Officer Work Queue**, a **Reports Center** (9 CSV reports), and
> **Camera Health History** with real ONLINE↔OFFLINE transition
> notifications. Migration `0007` (2 new tables, additive columns +
> `pg_trgm`). See §A rows tagged *(Phase 11)* and §J. Deferred items are
> listed in §D "Phase 11 follow-ups".

This document is the authoritative statement of what is implemented, what is
verified, what is partial, and what is future. It is deliberately conservative:
where something has not been demonstrated it is marked as such. Companion docs:
[`DEMO_RUNBOOK.md`](DEMO_RUNBOOK.md) (how to reproduce the demo),
[`SUBMISSION_REQUIREMENTS.md`](SUBMISSION_REQUIREMENTS.md) (requirement status),
[`SENTINEL_System_Audit_Report.md`](SENTINEL_System_Audit_Report.md) (full engineering audit),
[`SCALABILITY.md`](SCALABILITY.md) (measured load ladder + roadmap),
[`docs/HACKATHON_DEMO_RUNBOOK.md`](docs/HACKATHON_DEMO_RUNBOOK.md) (2-minute demo script),
[`docs/GOVERNMENT_FEED_READINESS.md`](docs/GOVERNMENT_FEED_READINESS.md) (feed-return checklist).

Legend: **Implemented** = code exists and is wired · **Verified** = exercised
this pass with the result recorded in §F · **Partial** = works with a stated
limit · **Future** = not present.

---

## A. WORKING / VERIFIED

Everything in this section was exercised on 2026-09-05 (commands and results in §F).

| Area | Status | Notes |
| :--- | :--- | :--- |
| **Docker / deployment** | Verified | `docker compose down -v && docker compose up --build -d` brings up postgis + minio + backend + frontend from zero volumes. Backend entrypoint runs `alembic upgrade head` (`0001→0008`), the admin seed, then (compose default `SEED_AI_DEMO=1`) the idempotent AI demo seed. Re-verified from an empty volume this pass. |
| **Database** | Verified | PostgreSQL 15 + PostGIS 3.3. Migrations `0001`–`0008` apply cleanly on a fresh volume (and full downgrade→upgrade round-trips). `0006` = operational layer (8 tables); `0007` = Phase 11 (2 tables + additive cols + `pg_trgm`); `0008` = Phase 12 — `anomaly_events` table, `alerts.source` enum col + `alerts.anomaly_event_id`, `alerts.watchlist_id` made nullable (an ANOMALY alert has no watchlist entry). Additive only; no existing table redesigned. |
| **Authentication / security** | Verified | JWT (HS256) login; RBAC (ADMIN/OFFICER/OPERATOR); login rate-limit (5 fails / 300s → 429); explicit CORS allow-list; short-lived scoped tickets for WebSocket handshake (`purpose="ws"`, ~60s) and media `<img>`/`<video>` (`purpose="media"`, ~120s) so the session JWT never rides the WS wire or a URL. |
| **Backend APIs** | Verified | Core: `/health`, `/api/v1/auth/*`, `/cameras/*` (+ `/{id}/health/history`), `/vehicles/search` + `/evidence`, `/watchlist/*` (CRUD + CSV), `/alerts/*` (+ `/assign`/`/escalate`/`/resolve`), `/incidents/*` (+ `/timeline`), `/cases/*` (+ `/timeline`, `/report`), `/notifications/*`, `/dashboard/{stats,health}`, `/pipeline/status`, `/analytics/*`, `/admin/*` (`/audit`, `/users`). Phase 11: `/search/{vehicles,global}`, `/saved-searches/*`, `/work-queue`, `/reports/*`. **Phase 12: `/api/v1/ai/{investigate,search,status,suggestions}`, `/ai/incidents/{id}/summary`, `/ai/cases/{id}/summary`, `/ai/anomalies` (+ `/scan`, `/{id}/review`).** |
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
| **Demo acceptance flow** *(2026-09-08)* | Verified | Full chain — detect → watchlist match → alert → acknowledge → create incident → assign → trace vehicle (journey) → attach evidence → add remark → create case → attach incident + evidence + note → CSV case report → resolve incident → close case — is one passing end-to-end test (`backend/tests/test_demo_acceptance_flow.py`), all real persisted state. Re-verified after Phase 11 against a fresh migrated Docker stack. |
| **Unified Advanced Search** *(Phase 11)* | Verified | `POST /api/v1/search/vehicles` — bounded query over `vehicle_events`⋈`cameras` with exact/partial plate (pg_trgm GIN), vehicle type, camera, location, date + wall-clock time band, watchlist status, has-alert/incident/case, confidence, REAL/MOCK; sort latest/earliest/confidence/camera; pagination; per-row live watchlist/alert/incident/case links. Audited (`ADVANCED_SEARCH`). Tests: `test_advanced_search.py` (3). |
| **Global Quick Search** *(Phase 11)* | Verified | `GET /api/v1/search/global?q=` — grouped hits across VEHICLES / CAMERAS / INCIDENTS / CASES / ALERTS / EVIDENCE, each linking to its page. Navbar search box (debounced). |
| **Saved Investigations** *(Phase 11)* | Verified | `saved_searches` table — criteria only, never result sets; re-run live on open. Per-user (ADMIN sees all). CRUD + audit. Tests in `test_phase11_workflow.py`. |
| **Advanced Watchlist Management** *(Phase 11)* | Verified | `watchlist` gains `description` / `effective_from` / `updated_by_user_id`. Console: filter (category / priority / effective·pending·expired·inactive) + sort + pagination; add / edit / activate / deactivate; **CSV import** (validates plate format, category, dates, in-file dupes → created/updated/skipped/invalid summary; `dry_run`) and **CSV export**. `effective_from` is enforced by the matching engine's shared `active_watchlist_clause()`. GJ18TC0450 demo entry (no window) unaffected — verified. Tests: `test_watchlist_management.py` (7). |
| **Alert Escalation workflow** *(Phase 11)* | Verified | `AlertStatus` gains `ESCALATED`; `alerts` gains assignment + escalation columns. `POST /alerts/{id}/assign` · `/escalate` (records `escalated_by/at/reason` + CRITICAL notification) · `/resolve` (`resolved_by/at`). The watchlist engine still only ever creates `NEW` alerts. Audited. Tests in `test_phase11_workflow.py`. |
| **Incident & Case timelines** *(Phase 11)* | Verified | `GET /incidents/{id}/timeline` and `/cases/{id}/timeline` — chronological entries **derived** from `audit_logs`, the entity's own timestamps, its notes / evidence links and the vehicle's camera sightings; category filter (ALERT/INCIDENT/CASE/EVIDENCE/NOTE/VEHICLE/STATUS/ACTIVITY). No new event table. Tests in `test_phase11_workflow.py`. |
| **Officer Work Queue** *(Phase 11)* | Verified | `GET /api/v1/work-queue` — role-aware: ADMIN sees all open work, OFFICER sees work assigned to them + unassigned NEW/ESCALATED alerts; counts + priority/newest/oldest sort. Tests in `test_phase11_workflow.py`. |
| **Reports Center** *(Phase 11)* | Verified | `GET /api/v1/reports` + `GET /api/v1/reports/{key}.csv` — 9 reports (vehicle-detections, watchlist-matches, alerts, incidents, cases, camera-activity, camera-health, vehicle-journey, daily-summary), each a bounded PostgreSQL aggregate; date-range / camera / department / plate / severity filters; CSV export; audited (`REPORT_EXPORT`). Tests: `test_phase11_reports_and_camera_health.py`. |
| **Camera Health History** *(Phase 11)* | Verified | `camera_health_history` table — one row per real effective-status transition, written by the health-push endpoint and by a lightweight 30 s in-process staleness watcher (`CAMERA_HEALTH_WATCH_*`). `CAMERA_OFFLINE` / `CAMERA_RECOVERED` notifications on the operationally-significant edges, deduped against the last row. `GET /cameras/{id}/health/history`. Tests: `test_phase11_reports_and_camera_health.py`. |
| **AI Investigation Copilot** *(Phase 12)* | Verified | `POST /api/v1/ai/investigate` — NL question → deterministic intent/entity parse (`nlq.py`) → one of 9 validated `InvestigationTools` → bounded existing-DB query → answer + timeline + map points + related alert/incident/case links + FACT/INFERENCE confidence. Grounded: every result row is a real DB row (test-asserted); empty → "not available in recorded evidence"; no-plate journey questions refused. Audited `AI_INVESTIGATION`. Tests: `test_ai_copilot.py` (7), `test_ai_nlq.py` (8). |
| **Natural-language CCTV search** *(Phase 12)* | Verified | `POST /api/v1/ai/search` — NL → `VehicleSearchQuery` → the **same** `execute_vehicle_search()` the Advanced Search uses. Returns the generated `filters` verbatim (explainability) + the enriched results. Added filters: `vehicle_color`, `unknown_only`, `min_duration_seconds` (per-track dwell). Audited `AI_SEARCH`. Tests: `test_ai_search_and_summary.py`. |
| **AI incident / case summary** *(Phase 12)* | Verified | `POST /api/v1/ai/{incidents\|cases}/{id}/summary` — deterministic structured summary from existing rows (incident/case, linked alert, notes, evidence, the vehicle's sightings) + investigation gaps. Labelled "AI-GENERATED SUMMARY"; missing data → "Not available in recorded evidence." Audited. |
| **Stopped-vehicle anomaly detection** *(Phase 12)* | Verified | `BehaviorAnalyticsService.scan_stopped_vehicles` — one grouped aggregate over stored ByteTrack `vehicle_events` (never video). Threshold-configurable. Each hit → `anomaly_events` row **+ an `Alert(source=ANOMALY)`** that flows through the existing acknowledge/assign/escalate/promote workflow, **+ notification**, **+ WS frame**. Idempotent (unique `(camera,track,first_seen)`). Periodic in-process scan + `POST /ai/anomalies/scan` (ADMIN/OFFICER). Tests: `test_ai_behavior.py` (4). |
| **AI offline demo** *(Phase 12)* | Verified | `scripts/seed_ai_demo.py` (compose `SEED_AI_DEMO=1`) seeds 8 cameras + a GJ18TC0450 journey + watchlist alert + `INC-<yr>-9001` + `CASE-<yr>-9001` + a stopped-vehicle track, then runs the real detector — all via production code paths. The full AI layer works with government CCTV disconnected and no LLM key (deterministic provider). Verified end-to-end on a fresh `docker compose up`. |
| **Test suites** | Verified | Backend **191 passed** (187 prior + 4 Phase 13 `test_phase13_polish.py`); AI/ingestion 143 passed, 8 skipped. Counts in §F. |
| **Journey Intelligence** *(Phase 13)* | Verified | `/api/v1/vehicles/search` journey now returns `transitions[]` — one INFERRED move per consecutive pair of sightings at different cameras, with `time_diff_seconds`, and `distance_meters` + `estimated_speed_kmh` **only** when both cameras are geolocated. Speed dropped when < 50 m apart, ≤ 0 s, or > 200 km/h (note explains why). `confidence_level` HIGH/MEDIUM/LOW by time gap + geolocation. Sightings carry `kind="CONFIRMED"`, `vehicle_color`, `is_mock`. Derived on read; no schema change. `haversine_m` shared via `app/services/geo.py`. Tests: `test_phase13_polish.py` (4). |
| **Camera Management console** *(Phase 13)* | Verified | `/cameras/manage` — table over the existing `/cameras` payload: search, REAL/MOCK + status filters, effective health, last heartbeat, `last_detection_at` (one bulk group-by, no N+1), coords, FPS; row → the existing camera modal. Read-only; no RTSP/credential surface. `CameraRead` gained `is_mock` + `last_detection_at`. |
| **Demo reset / polish** *(Phase 13)* | Verified | `./scripts/reset_demo.sh` (in-place, demo rows only) / `--full` (teardown+rebuild). `seed_ai_demo.py --reset` deletes only demo rows in FK-safe order — verified idempotent. NL-search filter chips, Reports PDF (client-side jsPDF; CSV primary/unchanged), AI-Anomalies KPI, per-route tab titles. |

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

**Phase 12 (AI) — deliberately out of scope / deferred:**

- **Visual Re-ID, face recognition, VLM/LLM reasoning, new ANPR models, AI agents** — explicitly excluded by the phase brief; a later AI phase.
- **Multi-model behaviour analytics** — only the ONE detector (stopped/loitering vehicle) was built, per the brief. Wrong-way / speeding / red-light / crowd anomalies are not.
- **`vehicle_events.vehicle_color` population** — the column, the NL parser ("white car") and the search/Copilot filter all exist; the live detector does not yet emit colour, so colour filters only match rows that carry it (the demo seed does). Additive when a colour classifier is added — no schema change.
- **LLM tool-calling loop** — the OpenAI provider can pick ONE tool and re-word the answer; a multi-step agentic loop is not built (and not needed — the deterministic intent→tool mapping covers the supported questions).
- **AI-pipeline-degradation / storage-warning notifications** — camera offline/recovered + anomaly notifications exist; pipeline/storage-threshold types do not.

**Phase 11 follow-ups** (deliberately scoped to P0 + selected P1; not
started unless noted):

- **Camera Management console** (F4) — a dedicated per-camera admin page: edit metadata, an explicit "maintenance mode" state, recent-incidents / recent-detections panels. Today: camera CRUD via `PATCH /cameras/{id}`, effective status, and the new health-history section in the camera modal; enable/disable is via status. `camera_health_history` provides the "previous state" the console would show.
- **GIS operational layers + filters** (F10) — layer toggles (active alerts / active incidents / case locations) and REAL·MOCK / online·offline / department / severity / date filters on the map. Today: the Investigation map shows cameras + the chronological camera-sighting trail; no layer/filter panel.
- **Journey Replay UI polish** (F11) — numbered markers, a timeline scrubber, per-sighting evidence preview in the transport bar. Today: play/pause/reset + click-to-focus (map↔timeline) already work in the Investigation console; the scrubber and numbered-marker styling are not added.
- **Operational analytics dashboard** (F17) — a dedicated police-ops charts page (detections/matches/incidents/cases per day, busiest cameras, camera availability, TODAY/7d/30d/custom). Today: `GET /api/v1/analytics/overview` + the Reports Center `daily-summary` CSV cover the underlying aggregates; no dedicated charts screen.
- **Global Activity Feed widget** (F18) — a live "09:31 Officer X acknowledged Alert …" stream on the command center. Today: the Admin Audit Center is the full activity log; the compact feed widget is not added.
- **Data export / retention admin panel** (F16) — a UI for `POST /admin/retention/purge` + retention config + last-purge status + selective record export. Today: the endpoint exists and is audited; no admin screen. Watchlist and case/report CSV exports exist.
- **PDF report output** — Reports Center exports CSV for all 9 reports; PDF is deferred (the vehicle-journey PDF from the earlier phase still works client-side).
- **User / role / department administration** — `GET /api/v1/admin/users` (read-only) exists for assignment dropdowns; full user CRUD + department/region association is not built.
- **AI-pipeline-offline / storage-warning notifications** — `CAMERA_OFFLINE` / `CAMERA_RECOVERED` are implemented (real transitions). Pipeline-degradation and storage-quota notification types are not (would need thresholds on the existing `/dashboard/health` signals).

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
| Backend | `cd backend && DATABASE_URL=…/sentinel_test pytest -q` | **191 passed** (~103 s) — 187 prior + 4 Phase 13 (`test_phase13_polish` 4: confirmed-vs-inferred transitions, implausible-speed suppression, camera `is_mock`/`last_detection_at`, single-sighting → no transitions) |
| Migration round-trip | `alembic upgrade head` on empty DB, then `downgrade 0006` → `upgrade head` | **OK** — `0001…0008` up/down/up clean. `alembic check` warns about the intentional mutual `alerts ↔ anomaly_events` FK cycle (SQLAlchemy sort limitation; runtime-safe — the migration creates `anomaly_events` first). Only pre-existing SQLModel-vs-migration index-naming noise otherwise. |
| Fresh Docker + Phase 12 acceptance | `docker compose down -v && SEED_AI_DEMO=1 up -d --build`; drive the API | **PASS (22/22)** — AI status = deterministic/offline; Copilot "where was GJ18TC0450 seen" → 5 grounded results + timeline + map + related alert + `AI MATCH: HIGH`; no-hallucination (result ids ⊆ real ids); journey; last-6-hours window; empty → "not available in recorded evidence"; NL search → filters + results; incident + case AI summary; seeded stopped-vehicle anomaly + its ANOMALY alert in the feed; re-scan idempotent; RBAC 401; `AI_*` audit rows. |
| Fresh Docker + Phase 10/11 regression | same stack | **PASS** — the full GJ18TC0450 demo acceptance flow (detect→alert→ack→incident→assign→trace→evidence→case→report→resolve→close→audit) + all Phase 11 smokes still green. |
| AI / ingestion | `PYTHONPATH=backend:. .venv/bin/pytest tests/ -q` | **143 passed, 8 skipped** (~39 s) — unchanged (`behavior.py` only swaps its local haversine for the shared `app/services/geo.py`; no `ai/` or ingestion file touched). |
| Fresh Docker + Phase 13 acceptance | `./scripts/reset_demo.sh --full`; drive the API on `:8001` | **PASS (16/16)** — login; `/vehicles/search?plate=GJ18TC0450` → 5 CONFIRMED sightings (colour + `is_mock=false`) + 4 INFERRED transitions with distance > 0, plausible speed, HIGH/MEDIUM/LOW confidence; `/cameras` → `is_mock` + `last_detection_at`; reports CSV still 200; Copilot grounded (5 results, HIGH/MEDIUM); NL search → `vehicle_color=white` + `time_from=21:00`; anomaly present; `/ai/*` needs auth (401); `AI_INVESTIGATION`/`AI_SEARCH`/`VEHICLE_SEARCH` audit rows. |
| Fresh Docker + Phase 10/11/12 regression | same stack (`smoke.py`, `p11smoke.py`, `p12smoke.py`) | **PASS** — full GJ18TC0450 demo acceptance flow + all Phase 11 smokes + all 21 Phase 12 checks green on pristine demo data. (The p10/p11 smokes ingest extra GJ18TC0450 sightings, so re-run `./scripts/reset_demo.sh` before a demo.) |
| Real cam04 / cam06 smoke | (Phase 11 run — not re-run) | RTSP auth OK, both ONLINE, YOLO+ByteTrack, plates `UNKNOWN`. Phase 13 changes nothing in ingestion/RTSP/ANPR. |
| Frontend build | `docker compose exec frontend npm run build` | **OK** — 2120 modules, `dist/` built. Dockerised dev-server transforms `CameraManagementPage.jsx`, `JourneyIntelligence.jsx`, updated `SearchPage.jsx` (0 errors); `/cameras/manage` + every existing route serve 200. **Not** a rendered browser click-test (Chrome extension unavailable). |

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

---

## J. PHASE 11 — ADVANCED OPERATIONAL FEATURES (2026-09-08)

### Data model (migration `0007`, additive only)

| Change | Purpose |
| :--- | :--- |
| `saved_searches` (table) | Saved Investigations — `params` JSON is criteria only, never a result set |
| `camera_health_history` (table) | Append-only camera effective-status transition log (FEATURE 5) |
| `watchlist.description`, `.effective_from`, `.updated_by_user_id` | Watchlist management console (FEATURE 3); `effective_from` enforced by `active_watchlist_clause()` |
| `alerts.assigned_to_user_id`, `.escalated_by_user_id`, `.escalated_at`, `.escalation_reason`, `.resolved_by_user_id`, `.resolved_at` | Alert escalation workflow (FEATURE 6) |
| `AlertStatus` enum gains `ESCALATED` (`ALTER TYPE … ADD VALUE`) | " |
| `pg_trgm` extension + GIN indexes `ix_ve_plate_trgm`, `ix_watchlist_plate_trgm` | Bounded partial-plate `ILIKE` search |

Nothing in the CCTV / ANPR / ByteTrack / watchlist-match / alert-generation
pipeline was redesigned. The one read-side change is
`watchlist_engine.active_watchlist_clause()` gaining an `effective_from`
term (NULL = effective immediately, so every prior entry — including the
GJ18TC0450 demo entry — is unaffected; verified by test + CSV-import smoke).

### API added

`POST /search/vehicles` · `GET /search/global` · `GET|POST /saved-searches`,
`GET|PATCH|DELETE /saved-searches/{id}` · `GET /watchlist` (now
filtered/sorted/paginated) · `PATCH /watchlist/{id}` ·
`POST /watchlist/{id}/activate` · `GET /watchlist/categories` ·
`GET /watchlist/export.csv` · `POST /watchlist/import.csv` ·
`POST /alerts/{id}/assign|escalate|resolve` ·
`GET /incidents/{id}/timeline` · `GET /cases/{id}/timeline` ·
`GET /work-queue` · `GET /reports` + `GET /reports/{key}.csv` ·
`GET /cameras/{id}/health/history`. Every list is bounded + paginated;
every mutation is RBAC-guarded (`ADMIN`/`OFFICER` for watchlist & alert
workflow, owner-or-`ADMIN` for saved searches, any authenticated for
read/search) and audited (`ADVANCED_SEARCH`, `SAVED_SEARCH_*`,
`WATCHLIST_UPDATED/ACTIVATED/IMPORT/EXPORT`, `ALERT_ASSIGNED/ESCALATED/RESOLVED`,
`REPORT_EXPORT`).

### Background task

`app.main._camera_staleness_watcher_loop` — a single in-process asyncio
task, every `CAMERA_HEALTH_WATCH_INTERVAL_S` (30 s), recomputes each
camera's effective status and records a `camera_health_history` row +
`CAMERA_OFFLINE`/`CAMERA_RECOVERED` notification on a real transition.
Dedup against the last history row means a camera that stays offline never
re-notifies. Bounded query (all cameras). Off in the test suite
(`CAMERA_HEALTH_WATCH_ENABLED=false`); transitions are tested directly.

### Frontend

New routes: `/search` (Advanced Search + saved investigations),
`/watchlists` (management console), `/my-work` (Officer Work Queue),
`/reports` (Reports Center). Navbar gains those tabs + a debounced
**Global Quick Search** box. Incident & Case detail pages gain a
filterable **Timeline** panel. Alert cards gain an **Escalate** action and
show escalation state. The camera modal shows **health history**. Dashboard
quick actions extended (Advanced Search / My Work / Watchlists / Reports).
All new calls degrade to explicit error/empty states — no mock fallback.

### Not done this phase

See §D "Phase 11 follow-ups" — Camera Management console, GIS layer
filters, Journey Replay polish, operational-analytics charts page, Activity
Feed widget, retention/export admin panel, PDF report output.

---

## K. PHASE 12 — AI INTELLIGENCE LAYER (2026-09-08)

Full detail in `docs/AI_ARCHITECTURE.md`, `docs/AI_INVESTIGATION_COPILOT.md`,
`docs/AI_SEARCH.md`, `docs/AI_BEHAVIOR_ANALYTICS.md`, `docs/AI_DEMO_RUNBOOK.md`.

### Core principle

The AI layer is **read-only over the existing entities**. It adds no
ingestion path. When government CCTV resumes, new `vehicle_events` flow
through the unchanged pipeline and every AI feature picks them up with no
code change.

### Data model (migration `0008`, additive only)

| Change | Purpose |
| :--- | :--- |
| `anomaly_events` (table) | one row per stopped-vehicle detection; every figure derived from stored ByteTrack `vehicle_events` |
| `alerts.source` (`alertsource` enum, default `WATCHLIST`) | the watchlist engine still only writes `WATCHLIST`; `BehaviorAnalyticsService` writes `ANOMALY` |
| `alerts.watchlist_id` → **nullable** | an `ANOMALY` alert has no watchlist entry |
| `alerts.anomaly_event_id` (nullable FK) | links an anomaly alert to its `anomaly_events` row |
| enums `anomalystatus`, `anomalykind`, `confidencelevel` | |

`AlertRead` gains `source` / `anomaly_event_id` and `watchlist_id` is now
`Optional` (regression-tested — the ANOMALY alert lists cleanly in
`GET /api/v1/alerts`).

### Components (`app/services/ai/`)

`nlq.py` (deterministic parser) · `tools.py` (`InvestigationTools` — 9
validated bounded read functions) · `llm.py` (`LLMProvider` /
`DeterministicProvider` / `OpenAIProvider`) · `copilot.py` · `summary.py` ·
`behavior.py` · `confidence.py`.

### API (`/api/v1/ai/*`)

`POST /investigate` · `POST /search` · `POST /incidents/{id}/summary` ·
`POST /cases/{id}/summary` · `GET /anomalies` · `POST /anomalies/scan`
(ADMIN/OFFICER) · `POST /anomalies/{id}/review` (ADMIN/OFFICER) ·
`GET /suggestions` · `GET /status`. All JWT-authenticated. Audited:
`AI_INVESTIGATION`, `AI_SEARCH`, `AI_INCIDENT_SUMMARY`, `AI_CASE_SUMMARY`,
`AI_ANOMALY_SCAN`, `AI_ANOMALY_REVIEW`.

### LLM safety

No external LLM required (`AI_LLM_PROVIDER=deterministic` default). The LLM
never gets DB access, never writes SQL — it only re-words a fact-checked
answer (given only the structured facts) and can pick one of the fixed
tools by name; the backend validates params and runs the query. Any LLM
error → transparent deterministic fallback. `OPENAI_API_KEY` is env-only,
never returned by any endpoint.

### Background task

`_anomaly_scan_loop` in `app/main.py` — every `AI_ANOMALY_SCAN_INTERVAL_S`
(300 s) runs the stopped-vehicle detector over recent events. Off in the
test suite. Idempotent.

### Offline demo

`scripts/seed_ai_demo.py` (compose `SEED_AI_DEMO=1`, idempotent) seeds 8
cameras + a GJ18TC0450 journey + watchlist alert + `INC-<yr>-9001` +
`CASE-<yr>-9001` + a stopped-vehicle track, then runs the real detector.
All production code paths. A judge runs `docker compose up` and
demonstrates the full AI layer with no live CCTV and no LLM key.

### Frontend

`/copilot` (chat + suggestions + interpreted filters + confidence chip +
timeline + GIS mini-map + related links) · `/anomalies` (list + scan +
review) · NL search box on `/search` · "Generate AI Summary" on incident &
case detail · "Ask AI about this vehicle" on the Investigation console ·
"AI Anomaly Events" panel + "AI Copilot" quick action on the command
centre · `AI ANOMALY` tag on anomaly alert cards · Navbar `Copilot` /
`Anomalies` tabs. Every AI call degrades to an explicit error/empty state —
no mock fallback.

### Not done this phase

See §D "Phase 12 (AI) — deliberately out of scope / deferred".

---

## L. PHASE 13 — HACKATHON READINESS & POLISH (2026-09-08)

Polish pass. **No new major feature, no migration, no change to ANPR /
RTSP ingestion / worker strategy / watchlist→alert / security.** All new
values are derived on read from existing rows.

### Journey Intelligence (`app/api/v1/vehicles.py`, `schemas/vehicle.py`)

- `VehicleJourneySummary.transitions[]` — one `JourneyTransition` per
  consecutive pair of sightings **at different cameras**:
  `time_diff_seconds`; `distance_meters` (great-circle) and
  `estimated_speed_kmh` **only when both cameras have coordinates**.
- Speed is suppressed (with a human-readable note) when cameras are
  < 50 m apart, timestamps are non-increasing, or the implied speed is
  > 200 km/h (plate misread / clock skew).
- `confidence_level` — HIGH (≤ 20 min + geolocated), MEDIUM (≤ 60 min),
  LOW (> 60 min or bad timestamps).
- Sightings now carry `kind="CONFIRMED"`, `vehicle_color`, `is_mock`.
- `kind` is `CONFIRMED` for sightings, `INFERRED` for transitions — a
  transition is never presented as observed fact.
- `haversine_m` extracted to `app/services/geo.py` (shared with the
  anomaly detector, which previously had its own copy).

### Camera Management (`app/api/v1/cameras.py`, `schemas/camera.py`)

- `CameraRead` gained `is_mock` (`^mock[_-]?cam` naming convention, never
  a schema flag — a real government feed cannot be mislabelled) and
  `last_detection_at`.
- `GET /cameras` computes `last_detection_at` for all cameras in **one**
  `GROUP BY` aggregate (no N+1).
- Frontend `/cameras/manage` — table console: search, REAL/MOCK + status
  filters, effective health, last heartbeat, last detection, coords, FPS;
  row → the existing `CameraModal`. Linked from the Camera Network header.
  No credential / device-management surface.

### Other polish

- **NL search** — interpreted filters rendered as human chips
  (`Colour: WHITE`, `Type: CAR`, `Time: after 21:00`, `Dwell ≥ N min`).
- **Reports** — client-side **PDF** export (jsPDF, already a dependency)
  alongside CSV. CSV is unchanged and remains primary.
- **Command centre** — `AI Anomalies` KPI card (NEW-status count).
- **UX** — per-route browser tab titles (`AppLayout.jsx`).
- **Demo reset** — `./scripts/reset_demo.sh` (in-place, demo rows only,
  FK-safe, idempotent) / `--full` (teardown + rebuild). Backed by
  `seed_ai_demo.py --reset`.

### Docs added

`docs/HACKATHON_DEMO_RUNBOOK.md` (2-minute click-by-click script + API-only
demo + troubleshooting), `docs/HACKATHON_ARCHITECTURE.md`,
`docs/GOVERNMENT_FEED_READINESS.md` (field-by-field live-event → column
map; the feed path is unchanged and needs only availability),
`docs/SCALE_TO_80000.md`.

### Government feed

Unchanged and verified ready — see `docs/GOVERNMENT_FEED_READINESS.md`.
No modification to government CCTV connectivity was made (feeds currently
unavailable). Journey distance/speed and camera `is_mock` all populate
automatically from the live pipeline's existing payload fields.

### Not done this phase

GIS layer-toggle panel, journey-replay scrubber, analytics charts page
(aggregates already available as CSV/endpoints) — deferred, listed in §D.
