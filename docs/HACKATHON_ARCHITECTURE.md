# SENTINEL — Architecture (Hackathon submission)

Gujarat Police CCTV Integration & Video Analytics platform. One coherent,
synchronised system: **camera → detection → vehicle event → watchlist →
alert → incident → evidence → investigation → journey/GIS → case**, with an
AI intelligence layer reading the same rows.

Companion docs: `GOVERNMENT_FEED_READINESS.md`, `SCALE_TO_80000.md`,
`PHASE17_BENCHMARK.md`, `PHASE18_ANPR_DIAGNOSTICS.md`,
`HACKATHON_DEMO_RUNBOOK.md`, `AI_ARCHITECTURE.md` (+ `AI_*`),
`SYSTEM_STATUS.md` (authoritative verified/partial/future list).

---

## 1. System architecture

```
┌──────────────┐   RTSP    ┌───────────────────┐   HTTP    ┌────────────────────┐
│ Gov / mock   │──────────►│ Ingestion + AI    │──────────►│ FastAPI backend     │
│ CCTV feeds   │           │ pipeline (Python) │  events   │ (PostgreSQL/PostGIS)│
└──────────────┘           │ YOLOv8 · ByteTrack│           │  + MinIO evidence   │
                           │ · ANPR/OCR        │           └─────────┬──────────┘
                           └───────────────────┘                     │ REST + WS
                                                                     ▼
                                                       ┌────────────────────────┐
                                                       │ React command centre    │
                                                       │ (Vite, dark UI)         │
                                                       └────────────────────────┘
```

* **Backend** — FastAPI + SQLModel, PostgreSQL 15 + PostGIS 3.3, MinIO for
  evidence blobs. Alembic migrations `0001→0015`. In-process background
  tasks: retention sweep, camera-health watcher, AI anomaly scan.
* **Ingestion/AI pipeline** — separate process (`scripts/run_pipeline_service.py`).
  Per-camera worker, TCP RTSP, reconnect/backoff. Emits detection events to
  `POST /events/ai-detection` (`X-Ingest-Key`).
* **Frontend** — React 18 + react-router + react-leaflet, one axios layer,
  dark command-centre design system.
* **Deploy** — single `docker-compose.yml` (postgis, minio, backend,
  frontend; `--profile ai` adds the pipeline).

## 2. Data flow

```
detection ─► vehicle_events ─┬─► watchlist engine ─► alerts ─► WebSocket ─► UI
                             │                          │
                             │                          └─► incidents ─► evidence ─► cases
                             │
                             ├─► advanced search / NL search / global search
                             ├─► vehicle journey (+ INFERRED transitions, GIS)
                             ├─► AI Copilot (validated tools)
                             ├─► AI incident/case summaries
                             └─► stopped-vehicle anomaly ─► anomaly_events ─► alerts(source=ANOMALY)

every privileged action ─► audit_logs   ·   every operational event ─► notifications
```

The backend is the **single source of truth**. No module denormalises
another's mutable state — links are foreign keys; derived views
(timelines, journeys, summaries) are recomputed on read.

## 3. Core tables

`cameras` · `vehicle_events` · `watchlist` · `alerts` · `users` ·
`audit_logs` · `pipeline_status` · `camera_health_history`
`incidents` (+ `incident_notes`, `incident_evidence`) ·
`cases` (+ `case_notes`, `case_incidents`, `case_evidence`) ·
`notifications` · `saved_searches` · `anomaly_events`

Indexes are query-shaped: composite `(plate_normalized, timestamp)` and
covering `(timestamp, …)` indexes for journey/analytics; `pg_trgm` GIN for
partial-plate search; GiST on the PostGIS point columns; status-board
composites on incidents/cases/anomalies.

## 4. AI architecture (see `AI_ARCHITECTURE.md`)

Read-only layer over the existing entities.

* **Deterministic-first** — a rule-based NL parser + templated answers work
  with **no external LLM**. An optional OpenAI provider only re-words a
  fact-checked answer and can pick one of 9 fixed tools; it never touches
  the DB or writes SQL; any error → deterministic fallback.
* **Grounded** — every Copilot result is a real row; empty → *"not
  available in recorded evidence"*; confidence is `HIGH/MEDIUM/LOW/
  INSUFFICIENT` with FACT vs INFERENCE clearly separated.
* **One anomaly detector** — stopped/loitering vehicle, from stored
  ByteTrack tracks (never video), feeding the existing alert workflow.

## 5. Security

JWT (HS256) auth; RBAC `ADMIN` / `OFFICER` / `OPERATOR`; per-endpoint
`require_roles`. Short-lived scoped tickets for the WebSocket handshake and
`<img>`/`<video>` media so the session JWT never rides a URL or a
subprotocol. Login rate-limit (5 fails / 300 s → 429). Explicit CORS
allow-list. Append-only `audit_logs` for every privileged action
(logins, searches, evidence access, watchlist / incident / case / anomaly
changes, all `AI_*` actions). Secrets (`JWT_SECRET_KEY`, `INGEST_API_KEY`,
`OPENAI_API_KEY`, RTSP creds) are env-only — never in source, never
returned by an API, never logged.

## 6. Scalability

See `SCALE_TO_80000.md`. Summary: the schema + indexes are built for
statewide `vehicle_events` volume (monthly range partitioning, covering
indexes, bounded queries); the compute path (edge inference, horizontal
backend, a queue between ingest and AI) is a documented target design, not
built for the PoC.

## 7. Offline demo

`SEED_AI_DEMO=1` (compose default) seeds a deterministic
`GJ18TC0450` scenario — cameras, journey, watchlist alert, incident, case,
stopped-vehicle anomaly — via the **real production code paths**. The whole
platform, AI included, is demonstrable from `docker compose up` with
government CCTV disconnected. `./scripts/reset_demo.sh` resets it.

## 8. Government-feed activation

`GOVERNMENT_FEED_READINESS.md`. Requires only feed availability + starting
the pipeline. No migration, no config flag, no architectural change.

## 9. Limitations

Authoritatively tracked in `SYSTEM_STATUS.md`. Headline items:

* Real wide-area feeds produce `UNKNOWN` plates (ANPR emits `UNKNOWN`,
  never a guess) — measured and explained, not just observed:
  `PHASE18_ANPR_DIAGNOSTICS.md` (97.1% UNKNOWN on 136 real-camera-code
  frames, dominant cause OCCLUDED / too-few-character-pixels, root-cause
  checked). No visual Re-ID for cross-camera correlation itself (appearance
  similarity exists as a separate, explicitly-capped signal).
* CPU throughput ~1 FPS aggregate across many feeds on the test host —
  `SCALE_TO_80000.md` / `PHASE17_BENCHMARK.md` for the full measured
  scheduler/capacity story.
* Frontend verified with a real headless-browser suite (Playwright,
  `frontend/e2e/`, `scripts/browser_test.sh`) — full click-through
  navigation, not just build/API-level checks (superseded the earlier
  "no browser automation available" limitation).
* Deferred UI polish: GIS layer-toggle panel, journey-replay scrubber,
  operational-analytics charts page (aggregates exist as CSV/endpoints).
* Real government RTSP/HLS endpoints are confirmed unreachable from this
  development environment (both timed out) — no fresh real-feed frame
  could be captured in Phase 18-20.

## 10. Demo sequence

`HACKATHON_DEMO_RUNBOOK.md` §4 — the 2-minute click-by-click script, or
`./scripts/hackathon_demo.sh` (§0 of that doc) for an automated,
self-verifying setup.

## 11. Phase 18-20 additions (ANPR diagnostics, failure resilience, security)

* **ANPR diagnostics** — `scripts/anpr_diagnostics.py` +
  `PHASE18_ANPR_DIAGNOSTICS.md`: explainable per-vehicle diagnostics
  (crop quality, OCR result, temporal fusion, one explicit failure
  reason) across SYNTHETIC / MOCK / REAL_HISTORICAL strata, never
  combined into one number. `ai/anpr/quality.py::PlateQuality
  .structured_result()` adds a multi-reason quality verdict; a real bug
  in temporal fusion's TTL expiry (`ai/anpr/plate_track_state.py`) was
  found and fixed by this work.
* **50-camera rehearsal + designated-vehicle scenario** —
  `scripts/hackathon_rehearsal.py`: bulk-onboards up to 50 mock cameras
  with GIS + feed assignment, runs a real (small-subset) AI pipeline
  burst, and verifies the full GJ18TC0450 demo chain (watchlist → alert
  → journey → investigation → evidence → incident → case → report) via
  live API calls. 18/18 checks pass end to end.
* **Failure resilience** — `tests/test_failure_resilience.py` +
  `backend/tests/test_failure_resilience.py`: camera decode exceptions,
  malformed streams, dead-worker restart, database/object-storage
  unavailability, all verified to degrade the one affected component
  cleanly rather than crash the platform.
* **Security hardening** — `backend/tests/test_security_audit.py`:
  session-JWT expiry/tampering, RBAC on real mutating endpoints,
  SQL-injection-shaped input safety, malformed/oversized requests. Two
  real bugs found and fixed: an unbounded `camera_id` reaching Postgres's
  btree-index limit (now a clean 422), and deleting a camera with linked
  detections raising an unhandled 500 (now a clean 409). A repo-wide
  secret scan found zero hardcoded credentials.
* **Deterministic demo + health check** — `scripts/hackathon_demo.sh`,
  `scripts/hackathon_health_check.py` (§0 of `HACKATHON_DEMO_RUNBOOK.md`).
