# SENTINEL — Architecture (Hackathon submission)

Gujarat Police CCTV Integration & Video Analytics platform. One coherent,
synchronised system: **camera → detection → vehicle event → watchlist →
alert → incident → evidence → investigation → journey/GIS → case**, with an
AI intelligence layer reading the same rows.

Companion docs: `GOVERNMENT_FEED_READINESS.md`, `SCALE_TO_80000.md`,
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
  evidence blobs. Alembic migrations `0001→0008`. In-process background
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
  never a guess). No visual Re-ID (future).
* CPU throughput ~1 FPS aggregate across many feeds on the test host.
* Frontend verified at build + module-transform + API level (not a
  full rendered click-through — no browser automation available here).
* Deferred UI polish: GIS layer-toggle panel, journey-replay scrubber,
  operational-analytics charts page (aggregates exist as CSV/endpoints).

## 10. Demo sequence

`HACKATHON_DEMO_RUNBOOK.md` §4 — the 2-minute click-by-click script.
