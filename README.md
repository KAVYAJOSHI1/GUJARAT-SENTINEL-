# SENTINEL — CCTV Integration & Video Analytics Platform

### Gujarat Police Innovation Hackathon 2026

![Sentinel Banner](https://img.shields.io/badge/Gujarat_Police-Hackathon_2026-blue?style=for-the-badge)
![Architecture](https://img.shields.io/badge/Architecture-Hybrid_Models_1--5-emerald?style=for-the-badge)
![Status](https://img.shields.io/badge/Documentation-Master_Branch-purple?style=for-the-badge)

---

## 1. Executive Overview

**SENTINEL** is a CCTV video analytics and intelligence platform prototype built for the **Gujarat Police Innovation Hackathon 2026**. As implemented today it is a **single-node Docker Compose PoC** (see `SENTINEL_System_Audit_Report.md` for a full, code-verified teardown): it ingests real Sentinel RTSP camera feeds plus optional local mock-camera clips, runs automated vehicle detection, ANPR, and OCR, correlates detections across cameras by matched plate string and (optionally) visual re-identification, matches sightings against a watchlist, escalates through a full incident/case investigation workflow, answers natural-language questions through a deterministic-first AI copilot, and visualizes vehicle trajectories on PostGIS-powered Leaflet maps and a synchronised evidence/journey/timeline workspace.

What started as the 7-phase ANPR + watchlist pipeline documented in §3 below has since grown, on this same branch (`penultimate`), into a full command-center application: an **operational layer** (incidents, cases, notifications, audit trail, saved searches, a work queue), an **AI intelligence layer** (copilot, natural-language search, AI summaries, anomaly detection — all deterministic-first, no LLM required), an **advanced video-intelligence layer** (visual re-ID, cross-camera correlation, traffic/heatmap analytics, wrong-way and restricted-zone detection, a multi-step investigation agent), **real-video hardening** (honest LIVE/DEGRADED/RECORDED/OFFLINE camera playback, explicit ANPR failure reasons, character-level temporal fusion), a unified **SENTINEL Command Center** front end, and a transparent **capacity/scale-engineering pass** that measures — never assumes — how this exact codebase behaves under load and what it would honestly take to reach the ~80,000-camera roadmap. §3i onward documents each of these the same way §3–3h does: IMPLEMENTED vs. ROADMAP, every number traceable to a script or test you can re-run.

The architecture is designed with the seams (stateless backend, per-camera isolation, a clean ingestion/AI/backend contract) a larger deployment would need — **ROADMAP, not implemented today**: `SCALABILITY.md` / `docs/SCALE_TO_80000.md`'s statewide **~80,000 camera** / Kubernetes / Kafka / Triton architecture is a target design, evaluated against no infrastructure that exists in this repository yet (no K8s manifests, no Kafka topics, `device="cpu"` hardcoded everywhere, "regions" in `ai/regions.py` are a labeled-SIMULATED grouping with no real network boundary). The system currently runs as one process pool against `docker-compose.yml`, correctly scoped to its stated **~50-camera PoC** target — §3m's own transparent capacity model, fed by real measurements on this hardware, is explicit that reaching 80,000 cameras needs materially more workers (and ideally GPUs) than exist here today.

---

## 2. Platform Capability Matrix

| Feature Domain | Technical Implementation | Operational Impact |
| :--- | :--- | :--- |
| **Stream Ingestion** | RTSP over TCP, WebRTC, HLS, PTS Timestamping, Exponential Backoff | Resilient ingestion across erratic network environments |
| **AI Analytics** | YOLOv8 Vehicle Detection + EasyOCR (PaddleOCR optional) + Multi-Frame Consensus | ANPR accuracy is **not yet benchmarked against a real labeled dataset** (none exists locally — real-camera accuracy therefore *cannot* be stated statistically, only qualitatively). `scripts/evaluate_anpr.py` has a synthetic-font mode (measured this pass: **87.5% exact / 98.3% char**, up from 70.8% / 85.8% — but rendered fonts are out-of-distribution and its own output refuses to let those be quoted as real accuracy) and a real-`--dataset` mode for when labeled footage exists. No ">95%" or any accuracy figure should be cited as real until that run is done. See §3d below and `SENTINEL_System_Audit_Report.md` §3. |
| **Cross-Camera Correlation** | ByteTrack Spatial-Temporal Indexing + Normalized Plate Matching + optional visual Re-ID | Chronological vehicle journey reconstruction across cameras, incl. plate-unread vehicles (§3j) |
| **Watchlist & Alerts** | FastAPI Engine + 5-Min Cooldown Deduplication + WebSockets + escalation/assignment | Sub-second alert delivery to command center operators, with an auditable escalation trail |
| **GIS & Investigation** | PostGIS Spatial Point Layers + Leaflet Polyline Vector Mapping + Investigation Workspace | Interactive visual map trajectories, synced evidence/journey/timeline, automated PDF evidence reports |
| **Operational Layer** | Incidents, cases, notifications, saved searches, officer work queue, audit trail (§3i) | Structured investigation workflow, not just raw alerts |
| **AI Copilot & NL Search** | Deterministic-first tool-calling copilot + natural-language vehicle search + AI summaries + stopped-vehicle anomaly detection (§3i) | Works with **zero external LLM**; an optional LLM only re-words fact-checked answers, never runs its own SQL |
| **Video Intelligence** | Cross-camera correlation, traffic/heatmap analytics, wrong-way & restricted-zone detection, camera reliability scoring, multi-step investigation agent (§3j) | Answers "where else has this vehicle been" and "what's anomalous right now" from evidence, not guesswork |
| **Real-Video Playback** | LIVE/DEGRADED/RECORDED/OFFLINE-labeled camera player, explicit ANPR failure reasons, character-level temporal plate fusion (§3k) | Operators always see what kind of feed they're looking at — never a silent fake-live loop |
| **Command Center** | Unified landing dashboard, grouped nav + Ctrl+K palette, live monitoring wall, sectioned work queue (§3l) | One coherent app instead of a set of disconnected pages |
| **Scale & Security Hardening** | Fair per-camera scheduler, transparent 80k-camera capacity model, ANPR failure diagnostics, idempotent event ingestion, RBAC/JWT/SQLi/path-traversal audit (§3m–3o) | Every scale/security claim is a measured number or a passing test, not an assertion |

---

## 3. Pipeline Observability & Async Event Delivery

**IMPLEMENTED** (this hardening pass): the AI pipeline's `requests.post` event
delivery used to run synchronously inside `process_frame()` — a slow/down
backend added up to 5s of stall per event on the single inference thread.
`ai/pipeline.py` now hands events off to a **bounded queue + background
sender thread**; a full queue (backend/sender can't keep up) drops the new
event and **counts it** — it never silently disappears, and it never blocks
detection.

```
AI pipeline (YOLO/OCR/consensus)
        │  (non-blocking put)
        ▼
  bounded event queue (SENTINEL_EVENT_QUEUE_SIZE, default 500)
        │  (background thread, existing retry/buffer logic unchanged)
        ▼
  event sender  ──POST──▶  backend
```

**Metrics** — `AIPipeline.get_metrics()` (superset of the pre-existing
`get_benchmark_stats()`) reports, all from real counters/samples, never
estimated: event-queue depth (current + observed max), events
enqueued/sent/dropped (by cause: queue-full, backend-rejected, retry-buffer-
full), YOLO/OCR/event-send/compute/end-to-end latency as count + avg + p50 +
p95 (monotonic-clock durations — never PTS), per-camera frame/event counts,
and CPU%/RSS if `psutil` is installed. `ingestion.stream_health.HealthRegistry`
gained a matching `last_reconnect_duration_s` per camera (reconnect *count*
already existed). `scripts/run_pipeline_service.py`'s existing periodic STATS
log line now prints these instead of the old buffer-length heuristic — no new
observability stack, this is the same "existing health/stats mechanism" the
audit asked to reuse.

**Benchmark harness** — `scripts/benchmark_pipeline.py` reuses
`PipelineService` (no parallel ingestion path) and samples it periodically
for a fixed duration, then prints a human-readable + JSON report:

```bash
.venv/bin/python scripts/benchmark_pipeline.py --cameras cam04,cam06 --duration 60
.venv/bin/python scripts/benchmark_pipeline.py --all --duration 30 --no-backend
.venv/bin/python scripts/benchmark_pipeline.py --cameras MOCK_CAM01,MOCK_CAM02 \
    --registry data/trafficdataset_camera_registry.json --duration 30 --json-out bench.json
```

The same command scales to 1 / 5 / 10 / 20 / 30 cameras by changing
`--cameras`/`--all` (build a bigger mock fleet first with
`scripts/generate_mock_camera_registry.py --count N` if needed) — running 30
cameras is the caller's explicit choice, not something this script does on
its own.

**MEASURED, not a target** (2 MOCK cameras, 30s, CPU inference, against the
real docker-compose backend — see `SENTINEL_System_Audit_Report.md` for the
methodology; re-run `scripts/benchmark_pipeline.py` yourself before quoting
any of these numbers in a different environment):

| Metric | Result |
| :--- | :--- |
| Event delivery | 15/15 generated events delivered (`events_sent_ok`), **0 dropped** of any kind |
| Event-queue max depth | 1 (of 500) — the async sender easily kept up; delivery was never the bottleneck |
| Event send latency | p50 17ms, p95 25ms (localhost backend) |
| YOLO latency | p50 45ms, p95 107ms |
| OCR latency | p50 165ms, p95 493ms |
| Ingestion frame-queue | filled to its max (500) — confirms the **already-known, unrelated** single-CPU-consumer-thread bottleneck (§6/§7 of the audit), not a regression from this change |

**ROADMAP, not implemented / not run here**: sustained multi-hour soak tests,
and anything at the real `cam04`/`cam06` Sentinel source (unreachable from
this environment both when this was written and when the load ladder below
was run — the harness works identically against it once reachable).

---

## 3b. Camera Scalability Load Ladder (1 / 5 / 10 / 20 / 30 — MEASURED)

**MEASURED** — a real 1/5/10/20/30-MOCK-camera ladder was run (not
estimated), one `scripts/benchmark_pipeline.py` invocation per tier, 45s
each, `--no-backend` (isolates AI/pipeline CPU capacity from network
variance, per the audit's own methodology), same 8-core host as §3:

```bash
.venv/bin/python scripts/generate_mock_camera_registry.py --count 30
.venv/bin/python scripts/benchmark_pipeline.py --cameras MOCK_CAM01 \
    --registry data/trafficdataset_camera_registry.json --duration 45 --no-backend
# ...repeated with --cameras MOCK_CAM01..05 / ..10 / ..20 / ..30
```

| N cameras | input FPS (sum) | processed FPS (total) | dropped frames | frame-queue max | CPU avg/max % | RSS max | YOLO p50/p95 ms | OCR p50/p95 ms | E2E p50/p95 ms | cameras that got ≥1 processed frame |
| :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| 1 | 30 | 1.18 | 6 | 500/500 | 667/733 | 4039 MB | 37/60 | 168/346 | 3007/11937 | 1/1 |
| 5 | 150 | 1.31 | 153 | 500/500 | 660/703 | 4449 MB | 39/68 | 147/345 | 11247/35487 | 5/5 |
| 10 | 300 | 1.20 | 371 | 500/500 | 682/725 | 4939 MB | 42/64 | 155/339 | 12456/40185 | 5/10 |
| 20 | 600 | 1.09 | 787 | 500/500 | 692/720 | 5841 MB | 42/62 | 177/378 | 13559/38334 | 5/20 |
| 30 | 900 | 1.04 | 1186 | 500/500 | 700/723 | 6747 MB | 43/96 | 176/418 | 15169/44051 | 5/30 |

All 30 mock cameras ingested successfully at every tier (every worker
reached `status=ONLINE`, one clean initial connect each, zero ingestion
errors/crashes) — ingestion itself scales cleanly to 30 concurrent
connections. Event delivery stayed healthy throughout (event-queue depth
never exceeded 1/500 at any tier; `--no-backend` means `events_sent_ok`
reads 0 by the script's own documented convention, not a delivery failure).

**Bottleneck, from these numbers alone:**
- **The frame queue saturates (500/500) already at N=1.** This is not a
  multi-camera-only problem: even one camera's raw 30fps input outpaces the
  single AI consumer thread on this clip (dense multi-vehicle frames).
- **Total processed FPS is flat (~1.0–1.3) across every tier.** Going from 1
  to 30 cameras did not change the pipeline's aggregate throughput at all —
  conclusive evidence of a single hard ceiling (the one `FrameConsumer`
  thread), not a per-camera or queue-size limit.
- **CPU is already at its ceiling at N=1** (667% avg of a possible ~800% on
  this 8-core host) and stays flat (660–700%) through N=30 — CPU is the
  limiting resource, and it does not get more saturated with more cameras
  because it is already maxed out by the compute cost of processing frames
  from as few as one busy camera.
- **OCR (p50 147–177ms) consistently costs ~4x more than YOLO (p50 37–43ms)
  per operation** — OCR is the dominant per-vehicle compute cost, though at
  these camera counts most cameras never process enough frames to reach the
  existing OCR-throttling threshold (3 votes) in the first place.
- **Only 5 of N cameras ever get a single processed frame once N≥10** (25 of
  30 cameras: zero frames processed in 45s). Root cause, from reading
  `ingestion/stream_manager.py`/`ai/adapter/ingestion_bridge.py`: workers
  start sequentially and the shared `frame_queue` is pure FIFO with no
  eviction of stale entries — whichever cameras' frames fill the queue's
  500 slots first (a function of worker start order, not any per-camera
  cap) occupy essentially the entire queue for the whole run, because the
  consumer drains at ~1 frame/sec against ~900 incoming/sec combined at
  N=30. This is a **fairness** artifact of a plain FIFO queue under massive
  sustained overload, distinct from the raw CPU ceiling above.
- **RAM grows roughly linearly with camera count** (4.0 GB → 6.7 GB, N=1→30)
  — proportional to the number of concurrent `StreamWorker`/OpenCV capture
  threads, not a leak (each run is a fresh process; there is no
  within-run growth trend evidence either way from a single snapshot per
  tier — see "not run" below).
- **Frame drops scale roughly linearly with camera count** (6 → 1186,
  N=1→30), consistent with more producers competing for the same
  saturated single consumer + FIFO queue.

**Optimization decision**: no pipeline code change was made. Every
candidate considered (configurable worker count, OCR throttling, frame
skipping, batching, moving OCR off the main path) either doesn't address
what was actually measured (most starved cameras never reach the
frame-count where OCR throttling would matter) or requires more than a
small, contained change to fix safely (true parallelism needs a
thread-safety review of the currently single-consumer-assumed
`AIPipeline` state; fixing the FIFO fairness issue needs a different
queue/eviction data structure, a bigger change than "smallest safe" for
this pass). See `SENTINEL_System_Audit_Report.md` for the deferred
GPU/worker-pool architecture this genuinely requires.

**NOT measured in this pass** (do not assume, do not extrapolate): a
sustained multi-hour run at any tier (RAM-growth-over-time / leak
detection needs one, not a single end-of-run snapshot); the real
`cam04`/`cam06` Sentinel RTSP source (unreachable from this environment);
any tier with a live (non-`--no-backend`) backend under this much load; any
GPU configuration.

---

## 3c. Parallel AI Worker Pool (Phase 2C — IMPLEMENTED, not recommended on this host)

**MEASURED, not fabricated**: `SENTINEL_AI_WORKERS` (default `1`, unchanged
behavior) now supports camera-sharded, multi-process AI workers with a
fair per-camera round-robin scheduler (`ai/worker_pool.py`) — see
`SCALABILITY.md` §4 for the full architecture, isolation guarantees, and
measured results. Headline finding: on this 8-core shared test host,
`SENTINEL_AI_WORKERS=2` or `=4` measured **worse** than the `=1` baseline
at every camera-count tier tested (0-0.06 processed FPS vs. 0.7-1.1 FPS),
because the host has no spare CPU for a second real YOLO+EasyOCR process
alongside ingestion — confirmed as host CPU oversubscription (isolated
component tests all scale correctly), not an architecture defect. **Do not
enable `SENTINEL_AI_WORKERS>1` in production without re-benchmarking on
the actual target hardware first.**

---

## 3d. ANPR / Plate-Recognition Accuracy Pass (Phase 3 — IMPLEMENTED)

Targeted improvements to the existing plate pipeline (plate locator →
preprocessing → OCR → Indian-format normalisation → temporal consensus),
each tied to an audit finding, with the **honest UNKNOWN behaviour
deliberately preserved** — nothing here turns an unreadable plate into a
guessed one.

**Changes:**
- **Plate localisation** (`ai/anpr/plate_locator.py`): the original
  Canny→contour search is kept *unchanged*; a second candidate source
  (CLAHE contrast-enhancement + morphological closing) is added alongside
  it. Audit finding: `cv2.contourArea()` massively under-counts a thin
  border/frame contour (observed: 17 px² for a ~27,000 px² region), so the
  correct candidate was being rejected by the area filter and the code
  fell back to a fixed-fraction crop that clips real characters. The
  closed-edge candidate merges characters + border into one solid,
  correctly-measured blob. Also: mild rotation deskew (only fires on a
  genuinely tilted candidate), top-2 ranked candidates, a slightly wider
  fallback window.
- **OCR** (`ai/ocr/ocr_engine.py`): `extract_best()` now early-exits once a
  variant scores clearly well (≥0.92) instead of always running all 3–4
  preprocessing variants — this is the per-vehicle multivariant-OCR cost
  Phase 2C flagged as the pipeline's dominant per-frame cost. Ambiguous
  crops still try every variant.
- **Temporal consensus** (`ai/anpr/consensus.py`): a per-vote
  `plate_quality` weight (the plate *locator's* own confidence — real
  contour match vs. crude fallback crop) now feeds the weighted vote,
  distinct from the existing format-validity weight. A vote built on a
  fallback crop counts for less.
- **Normalisation** (`ai/ocr/plate_format.py`): graduated correction cap —
  ≤1 confusion fixed on the "don't lower validity" rule; 2–3 only if the
  result *strictly* validates (real state code + exact layout); ≥4 refused
  outright. Audit finding: the old rule fabricated plates from arbitrary
  text (`"RANDOMTEXT"` → `"RAN0OM73X7"`, `"12345678"` → `"IZ3A5678"`).
  Those now pass through unchanged and stay invalid.

**MEASURED — `scripts/evaluate_anpr.py` synthetic set (24 rendered plates,
same 8-core host). Rendered fonts are OUT OF DISTRIBUTION — this measures
pipeline wiring, NOT real CCTV accuracy:**

| Metric | Before | After |
| :--- | :-: | :-: |
| Exact-plate match | 70.8% (17/24) | **87.5% (21/24)** |
| Character accuracy | 85.8% | **98.3%** |
| Valid-format rate (of reads) | — | 21/24 strictly valid |
| UNKNOWN rate | 0% | 0% (all synthetic plates are readable) |
| Mean OCR latency / plate | 640.8 ms | **472 ms** (−26%) |
| Plate localised | 100% | 100% |

Remaining 3 synthetic misses are genuine single-character OCR confusions
on the rendered font (`3`↔`S`, `J`↔`u`, a split-digit segmentation error),
not localisation failures — appropriately left as honest errors rather
than force-corrected.

**REAL SENTINEL CAMERAS — QUALITATIVE ONLY (no labeled data, so no
statistics):** short spot-checks on cam04 / cam06 / cam09 / cam15 / cam20
(~900 frames, ~53 vehicles detected, 8 AI events). Every event resolved to
**UNKNOWN** — these are distance/area-surveillance feeds where plates are
genuinely not resolvable in frame — and **zero hallucinated plate strings**
were produced. Vehicle detection, OCR attempts, evidence capture, and the
event→backend path all ran correctly; the pipeline honestly reports what
it cannot read. The positive "readable plate → correct plate" path is
exercised by `tests/test_ai_to_backend.py` and the synthetic evaluation,
not by these particular real feeds.

**ROADMAP (not done — needs data/labels this repo does not have):** a
fine-tuned plate-region detector (vs. the current classical-CV locator) and
a fine-tuned Indian-plate OCR head both require a labeled Sentinel plate
dataset that does not exist locally; until it does, real-camera ANPR
accuracy can only be reported qualitatively.

**Known model limitations (future work):**

- **Auto-rickshaws / three-wheelers.** The YOLOv8n class set and the
  plate-aspect-ratio prior in `ai/anpr/plate_locator.py` are tuned for cars
  and two-wheelers; three-wheeler plates (smaller, lower-mounted, often
  angled) are detected less reliably and read less often.
- **Visual vehicle re-identification.** Cross-camera correlation is done
  purely by plate-string match. A vehicle whose plate is never read on any
  camera does **not** get stitched into a journey by appearance/colour/model
  — there is no Re-ID embedding model. This caps journey recall exactly
  where ANPR is weakest.

---

## 3e. Security & Production Hardening (Phase 4 — IMPLEMENTED)

Closes the outstanding `SENTINEL_System_Audit_Report.md` §10/§16 security
findings. Full detail: `SECURITY.md` §2 and audit report Part II §4b. No
camera-performance / GPU / distributed-system work (explicitly out of
scope).

| Area | What it does | Config / endpoint |
| :--- | :--- | :--- |
| **Login rate limit** | Failed `/auth/login` attempts counted per `(ip, username)`; **429 + `Retry-After`** after 5 in 300s; a successful login clears it. Generic 429 body (no user-existence oracle, no credential echo). | `LOGIN_RATE_LIMIT_*` env |
| **CORS** | Explicit origin allow-list; a `"*"` entry is dropped (with a warning) unless `ENV` is a development value; `allow_credentials` off when list is `"*"`. | `CORS_ALLOW_ORIGINS`, `ENV` |
| **WebSocket ticket** | `/ws/alerts` now needs a **short-lived `purpose="ws"` ticket** (~60s), fetched from `POST /api/v1/auth/ws-ticket` — the long-lived session JWT is never put on the WS wire. | `WS_TICKET_TTL_SECONDS` |
| **Media ticket** | Evidence-image / mock-video `?token=` now carries a **short-lived `purpose="media"` ticket** (~120s) from `POST /api/v1/auth/media-ticket`, not the session JWT. `Authorization: Bearer` header path unchanged. | `MEDIA_TICKET_TTL_SECONDS` |
| **Retention** | Periodic purge of `vehicle_events` older than **30 days** (configurable; `0` disables). Rows referenced by an alert are never deleted; `watchlist` / `alerts` / `audit_logs` untouched. Also admin-only `POST /api/v1/admin/retention/purge`. | `VEHICLE_EVENT_RETENTION_DAYS`, `RETENTION_SWEEP_*` |
| **Audit** | Added `LOGIN_RATE_LIMITED`, `RETENTION_PURGE`; tests assert the audit `detail` column never holds a password / JWT / ticket / RTSP credential. | — |

**No DB migration** (tickets are stateless JWTs; the rate limiter is
in-memory; retention only deletes rows). **Still ROADMAP:** RS256 signing,
TLS-in-app, encryption at rest, **distributed** (cross-replica) rate
limiting, GPU/Kafka/K8s.

---

## 3f. Vehicle Intelligence & Investigation (Phase 5 — IMPLEMENTED)

Strengthens the plate-search → camera-journey → evidence flow. No changes
to RTSP ingestion, the worker pool, camera performance, or ANPR internals.
No GPS/routes/locations are invented — this is a **camera-sighting** trail,
labelled as such everywhere.

| Area | Change |
| :--- | :--- |
| **Vehicle metadata** | `canonical_vehicle_type()` (`backend/app/services/vehicle_types.py`) folds the pipeline's YOLO classes + common synonyms onto one consistent spelling (`car`/`motorcycle`/`bus`/`truck`/…) at ingest. `None` stays `None` — never invented; an unrecognised real value is kept, not upgraded. `vehicle_type` now flows consistently: DB → `/vehicles/search` + `/vehicles/events/recent` → timeline chip + profile card + PDF/CSV. |
| **Vehicle journey** | `/vehicles/search` gains a `journey` block derived purely from the real sighting rows: `first_seen`, `last_seen`, `span_seconds`, `distinct_cameras`, `geolocated_sightings`, `vehicle_types`, `is_single_sighting`, `has_journey` (≥2 distinct geolocated cameras). Sightings are always chronological ascending; each carries an explicit `has_location`. Single / no-coordinate / unknown-plate cases are reported honestly (no fabricated trail). |
| **Investigation UI** | Timeline rows now show camera id, location, timestamp, **plate confidence** (was blank on real data — the frontend was reading the wrong field), and a **vehicle-type chip**. Profile card shows vehicle type + an honest journey-status line. Map panel renamed "Camera Sighting Trail" with a status that says plainly when there's nothing to connect. Watchlist flag now reads the backend's top-level `is_watchlisted` (was always false on real data). |
| **Analytics** | New `GET /api/v1/analytics/overview` — live aggregates over the real tables: detections by type, detections by camera (top N, windowed), top observed plates (UNKNOWN excluded), hourly activity, watchlist matches (total + windowed), active alerts, readable-vs-UNKNOWN counts. Rendered in a **Vehicle Intelligence** dashboard panel that shows an explicit "DATA UNAVAILABLE" state on failure — **never** mock numbers. |

**No DB migration** (no schema change — `vehicle_type` column already
existed; everything else is query-time). Tests: `backend/tests/` +3
(`test_vehicle_journey`, `test_analytics`, `test_vehicle_types`).

---

## 3g. Database Scalability & Query Performance (Phase 6 — MEASURED)

Benchmarked the exact queries `/vehicles/search`, `/vehicles/events/recent`,
`/analytics/overview` and the retention sweep issue, against a **synthetic
1,000,000-row** `vehicle_events` table (`scripts/db_benchmark.py` — a
standalone script; it never touches app code and only writes a disposable
`sentinel_bench` DB). Host: same 8-core dev box, Postgres 15 / PostGIS in
Docker. Numbers are p50 of 5 warm runs; the table was `VACUUM ANALYZE`d
before every measurement.

**Migration `0004` — indexes added (chosen from the EXPLAIN plans, nothing
speculative):**

| Index | Serves | Why |
| :--- | :--- | :--- |
| `ix_ve_ts_plate (timestamp, plate_number_normalized)` | analytics: top plates / distinct plates in window | covering → index-only scan, no heap fetch for the plate value |
| `ix_ve_ts_camera_code (timestamp, camera_code)` | analytics: detections by camera in window | covering → index-only scan (with the query rewrite below) |
| `ix_ve_vehicle_type (vehicle_type)` | analytics: detections by type (all-time) | parallel index-only scan instead of a heap seq scan |
| `ix_alerts_vehicle_event_id` | retention anti-join + the FK reference check | the model always declared it; migration `0001` never created it |

Migration `0004` also **drops the duplicate GiST spatial index** on both
`location` columns (GeoAlchemy2 auto-creates `idx_<table>_location`,
migration `0001` additionally created `ix_<table>_location_gist` — two
identical GiST indexes doubling spatial-index maintenance on every
`vehicle_events` insert, for an index no query currently uses). One is kept
(roadmap: proximity search). And the unused index on the raw
`vehicle_events.plate_number` column was removed from the model.

**Query rewrites in `analytics.py` (identical responses, fewer scans):**
- the 3 separate windowed scalar queries (total / readable / distinct
  plates) → **one** query with `count(*) FILTER (...)`.
- "detections by camera" → aggregate on `camera_code` first (index-only),
  then look up the ~30 camera names for just the top N — instead of
  `GROUP BY camera_code, Camera.name` over a join, which forced a heap
  fetch of every windowed row.

**MEASURED — `/analytics/overview` sub-queries at 1,000,000 rows:**

| Sub-query | BEFORE (p50) | AFTER (p50) | plan change |
| :--- | :-: | :-: | :--- |
| top plates in window | 150 ms | **39 ms** | bitmap-heap → index-only |
| detections by camera in window | 150 ms | **18 ms** | bitmap-heap + join → index-only + name lookup |
| detections by type (all-time) | 95 ms | **52 ms** | seq scan → parallel index-only |
| distinct plates in window | 257 ms | **149 ms** | bitmap-heap → index-only |
| windowed total/readable/distinct | 3 queries, ~272 ms | **1 query, ~152 ms** | consolidated |
| `COUNT(*)` all-time | 28 ms | 28 ms | unchanged (already index-only) |
| hourly activity buckets | 21 ms | 20 ms | unchanged (already index-only) |
| **endpoint total (sum of sub-queries)** | **~620 ms** | **~315 ms** | **≈ 2×** |

**Vehicle investigation — already fast, left alone:**

| Query | 10 K rows | 100 K rows | 1 M rows | plan |
| :--- | :-: | :-: | :-: | :--- |
| `/vehicles/search` (plate → chronological sightings) | ~1 ms | ~1 ms | **~2 ms** | index scan on `ix_vehicle_events_plate_ts_composite` |
| `/vehicles/events/recent` (dashboard feed) | ~0.4 ms | ~0.4 ms | **~0.5 ms** | backward index scan on the timestamp index |

The existing `(plate_number_normalized, timestamp)` composite already gives
an ordered index scan for the `WHERE plate = ? ORDER BY timestamp` pattern
— no new index needed, confirmed by EXPLAIN at every size.

**Retention** — the Phase 4 semantics are unchanged (same rows deleted,
alert-referenced rows always kept). The single-statement `DELETE` of a
large backlog (measured: **613 K rows in one 23.8 s transaction** — long
lock, one giant WAL record, autovacuum starvation) is now issued in
**bounded 10 K-row batches, committing each** (measured: same 613 K rows in
~30 s across 62 small transactions). The batch subquery is
`ORDER BY timestamp LIMIT` so it walks the timestamp index oldest-first.

**Connection pool** (`app/database.py` / `app/config.py`): added
`DB_POOL_RECYCLE_SECONDS` (default 1800 — replaces a silently-dropped idle
connection), a server-side `DB_STATEMENT_TIMEOUT_MS` (default 15000 — a
runaway query is cancelled, not left pinning a pooled connection), and
`application_name=sentinel-backend` for `pg_stat_activity`. `pool_size` /
`max_overflow` / `pool_pre_ping` were already configured and are unchanged.

**Remaining DB bottlenecks (honest):**
- `count(DISTINCT plate)` over the window (~149 ms at 1 M) is now the single
  largest analytics cost — inherently O(rows-in-window); an approximate
  count (HyperLogLog) would fix it but is out of scope (no new extensions).
- All-time `COUNT(*)` / `GROUP BY vehicle_type` are full index-only scans
  (~28 / 52 ms at 1 M) that grow with total table size — the 30-day
  retention default keeps the table bounded, so at steady state they stay
  small; a very long retention window would make them the ceiling.
- Single Postgres instance, no partitioning / read replica — the
  `SCALABILITY.md` roadmap, not attempted here.
- Pre-existing model↔migration index drift: several `Field(index=True)`
  flags on the models were never emitted as migrations, so
  `alembic revision --autogenerate` is noisy. Phase 6 did not widen this
  (its new indexes are in both places) and slightly narrowed it; a full
  reconciliation is a separate task.

---

## 3h. Command Center & Observability (Phase 7 — IMPLEMENTED)

Closes the gap between "the AI pipeline instruments itself" and "an
operator can actually see it". No RTSP / YOLO / OCR / ANPR / worker-pool
code touched — `scripts/run_pipeline_service.py` just gained a metrics-push
hop, the same pattern ingestion already uses for camera health.

| Area | What it does |
| :--- | :--- |
| **AI pipeline self-report** | `POST /api/v1/pipeline/status` (ingest auth) — the pipeline POSTs a snapshot of `AIPipeline.get_metrics()` every stats interval into the new `pipeline_status` table (migration `0005`, one upserted row per service): processed FPS, frames, vehicles, events generated/delivered/**dropped**, event-queue depth/max, YOLO+OCR **p50/p95**, CPU/RSS, per-camera frame/event counts. A missing metric is stored **NULL**, never a fabricated 0. |
| **System health aggregate** | `GET /api/v1/dashboard/health` (JWT) — real timed `SELECT 1` DB probe; camera counts by *effective* status + `stale` / `never_reported` / oldest-health-age; AI-pipeline status (`online` / `stale` / `unknown`, from the report's freshness) + its metrics; event-flow freshness (last-event age, 15-min readable/UNKNOWN counts); alert counts (total / active / acknowledged / **HIGH-CRITICAL active**). `dashboard/stats` is unchanged. |
| **Command-center dashboard** | New **`IncidentBar`** pins unhandled HIGH/CRITICAL watchlist alerts to the top — plate, camera, location, time, one-click **Trace → vehicle journey**. New **`SystemHealthPanel`** (replaces the old derived-only `SystemStatus`) and **`AiPipelinePanel`** (FPS, detections, events, queue, YOLO/OCR p50/p95, CPU/RSS). REAL / MOCK labels preserved everywhere. |
| **Camera health** | Cards show per-camera stream-health-push age and, distinctly, whether the AI pipeline has actually processed a frame from it (**"connected, no AI frames yet"** — connected ≠ AI-processed). Stale health-push shows an explicit STALE marker. |
| **Honesty** | Every panel renders an explicit **"unavailable"** / **"no report"** / **"HEALTH FEED DOWN"** state when the backend data is missing — it never silently falls back to fabricated numbers. |

**No behaviour change** to alerts / acknowledgement / watchlist / vehicle
investigation / GIS / evidence. Tests: `backend/tests/` +2
(`test_pipeline_status`, `test_dashboard_health` — 11 tests). Full backend
**111 passed**; AI/ingestion **143 passed / 8 skipped**; frontend build
clean.

**Remaining:** `pipeline_status` is a single latest-snapshot row (no time
series / trend charts); no Prometheus `/metrics`, no tracing. The AI
pipeline shows `unknown` until it runs with a reachable `--backend-url`
(a `--no-backend` dry run never reports).

---

## 3i. Operational Investigations & Deterministic AI Layer (IMPLEMENTED)

Two additive layers on top of the "protected" camera→YOLO→ByteTrack→ANPR→
vehicle_events→watchlist→alert pipeline above (its internals were not
touched):

**Operational layer** (migrations `0006`/`0007`) — `incidents`,
`incident_notes`/`evidence`, `cases`, `case_notes`/`evidence`,
`notifications`, `saved_searches`, `camera_health_history`; watchlist
gained `description`/`effective_from`/`updated_by_user_id` + full CRUD +
CSV import/export; alerts gained assign/escalate/resolve + an `ESCALATED`
status. New APIs: `/incidents/*`, `/cases/*`, `/notifications/*`,
`/admin/audit`, `/admin/users`, `/search/*` (unified advanced + global
quick search, `pg_trgm` GIN partial-plate indexes), `/saved-searches/*`,
`/work-queue`, `/reports/*` (9 CSVs), `/alerts/{id}/escalate|assign|resolve`.
Frontend: `/incidents`, `/cases`, `/system`, `/admin`, `/search`,
`/watchlists`, `/my-work`, `/reports`. RBAC: any authenticated role can
view; ADMIN/OFFICER can mutate; the audit center is ADMIN-only. Every
operational row links to an alert/vehicle_event/camera/user by FK — it
never denormalises pipeline state, and evidence is always a pointer to a
real `vehicle_events` row, never a copied file.

**AI layer** (migration `0008`) — **deterministic-first**: `AI_LLM_PROVIDER`
defaults to `deterministic` (works with **zero external LLM**); an
optional `openai` provider only re-words an already fact-checked answer
and can pick one of a fixed tool set — it never gets DB access and never
writes SQL, and any LLM error falls back to the deterministic path.
`backend/app/services/ai/` (`nlq.py`, `tools.py`, `llm.py`, `copilot.py`,
`summary.py`, `behavior.py`, `confidence.py`). APIs:
`/ai/{investigate,search,status,suggestions}`,
`/ai/{incidents,cases}/{id}/summary`, `/ai/anomalies[/scan,/{id}/review]`.
A **stopped-vehicle anomaly detector** runs a grouped aggregate purely
over `vehicle_events` (never video) against configurable
seconds/detections/displacement thresholds and raises a real
`Alert(source=ANOMALY)` through the existing alert workflow. Frontend:
`/copilot`, `/anomalies`, an NL box on `/search`, an AI Summary panel on
incident/case detail. Offline demo data is idempotent
(`scripts/seed_ai_demo.py`, `SEED_AI_DEMO=1`).

**Hackathon-readiness polish** on top of both: `/vehicles/search` now
returns a `journey.transitions[]` block — one **INFERRED** move per
consecutive camera pair, with great-circle `distance_meters` +
`estimated_speed_kmh` computed only when both cameras are geolocated and
suppressed (with a note) when the numbers would be physically nonsensical
(<50 m apart, dt≤0, >200 km/h). Sightings are always labelled `CONFIRMED`
vs. transitions `INFERRED` — the UI never blurs a real detection into a
guessed movement. A read-only camera console (`/cameras/manage`) and
`./scripts/reset_demo.sh` (`--full` for a complete teardown+rebuild) round
out demo operability.

Tests as of this pass: backend **191 passed** (+4 for the polish alone).
No pipeline/ANPR/ingestion/security-model changes in this section.

---

## 3j. Advanced Video Intelligence — Phase 14 (IMPLEMENTED)

A 7-commit layer answering "what else can we tell from the video, beyond
plate matching" — additive, no rewrite of any Phase 1–7 pipeline code. It
deliberately works within a real constraint: **no ML libraries in the
backend container** (torch/cv2/numpy stay pipeline-only) and
**`postgis:15-3.3` has no pgvector** — so visual re-identification uses a
pluggable embedding backend behind one interface: a deterministic
`attr-baseline-v1` (pure-Python, weighted type+colour+plate-seeded texture
unit vector — no neural network, no training data needed) by default, or
an optional real `TorchEmbeddingBackend` (mobilenet_v3_small/resnet50,
GPU-auto) added in Phase 15E; either way, matching is a bounded
brute-force cosine search, never a fabricated similarity score.

| Capability | What it does | API / migration |
| :--- | :--- | :--- |
| **Visual Re-ID** | Cosine-similarity vehicle matching by appearance, for vehicles whose plate was never read | `/ai/reid/*`, `GET /ai/reid/status`; migration `0009` `vehicle_embeddings` |
| **Cross-camera correlation** | Learns real camera-to-camera transition-time statistics from observed traffic, used to sanity-check journeys | `/ai/correlation/*`; migration `0010` `camera_transition_stats` |
| **Traffic & heatmap** | Aggregate density/flow analytics rendered on the GIS layer | `/analytics/traffic/*` |
| **Wrong-way / restricted-zone detection** | Direction-of-travel and zone-boundary anomaly scans, config'd per camera | `/ai/anomalies/scan` (`kinds=[]`), `PATCH /cameras/{id}/behavior-config`; migration `0011` adds `WRONG_WAY`/`RESTRICTED_ZONE` anomaly kinds |
| **Multi-step investigation agent** | 13 bounded, **read-only** tools an operator (or the copilot's DEEP mode) can chain to answer a compound question, plus explicit gap detection ("what's missing from this trail") | `/ai/investigation/{run,gaps}` |
| **Camera reliability & investigation graph** | Per-camera health/quality scoring; a graph view linking vehicles↔cameras↔incidents↔cases | `/ai/camera-intelligence[/{code}]`, `/ai/graph` |

Frontend gained `/traffic`, `/camera-intelligence`, `/graph`, a Visual
Matches panel on `/investigation`, a DEEP toggle on `/copilot`, and
per-anomaly-kind labels on `/anomalies`. All background loops (transition
recompute, extended anomaly scans) are off by default in tests. **Test-DB
gotcha**: migration `0011` alters an existing enum/table in place, which
`create_all`-based test setup does not apply — the test database must be
recreated after that migration lands. Tests: backend **269 passed**
(+77 this phase); acceptance smoke `p14smoke.py` (28 checks).

---

## 3k. Real Video Intelligence & Live Demo Hardening — Phase 15 (IMPLEMENTED)

Eight commits (15A–15H) moving from "the pipeline can process a video
file" to "an operator sees an honestly-labelled real feed." Migrations
`0012` (camera stream URLs), `0013` (ANPR quality/failure-reason columns,
backfilled `"OK"` on existing rows), `0014` (`is_demo` flags) — each
verified to round-trip cleanly.

- **Honest camera playback** (`app/services/camera_stream.py`,
  `CameraPlayer.jsx`, `hls.js`): a `GET /cameras/{id}/stream` profile
  picks the best real source in order **webrtc > hls > recorded >
  snapshot** and reports an explicit mode — **LIVE / DEGRADED / RECORDED
  / OFFLINE** — never a silent fallback that looks live when it isn't. A
  bare snapshot is always labelled *"LAST FRAME — NOT A LIVE FEED."*
- **Explicit ANPR failure reasons** (`ai/anpr/quality.py`): every
  unreadable plate now classifies *why* — `NO_PLATE` / `LOW_RESOLUTION` /
  `BLUR` / `OCCLUDED` / `OCR_DISAGREEMENT` / `INVALID_FORMAT` /
  `LOW_CONFIDENCE` — instead of a bare `UNKNOWN`. Feeds directly into the
  Phase 18 diagnostics below.
- **Character-level temporal fusion** (`ai/anpr/plate_track_state.py`): a
  bounded, TTL/LRU-limited per-track store builds character-level
  consensus across a vehicle's multiple OCR reads and only overrides the
  existing consensus when the fused result is both stable and
  higher-confidence — it never lowers accuracy.
- **Consolidated vehicle profile & workspace**: `GET /vehicles/profile`
  + the first `/workspace` investigation view (later rebuilt in Phase 16).
- **Real Torch Re-ID backend** (`REID_BACKEND=attribute|torch`,
  `GET /ai/reid/status`) — reports its actual backend/device/embedding
  dimension; the backend container (no torch installed) correctly reports
  `attribute/cpu`, never a fabricated GPU claim.
- **Video-quality scoring** — a distinct axis from camera *reliability*
  (`video_quality_score` 0–100, GOOD/FAIR/POOR/UNKNOWN), surfaced in
  `/ai/camera-intelligence`.
- **System metrics & ANPR dashboard**: `GET /system/metrics/summary`,
  `GET /analytics/anpr` + `/anpr-intelligence` page; `feed_source()`
  (`app/services/feed_source.py`) badges every sighting **DEMO > MOCK >
  REAL**, so nothing pretends a seeded demo row is a live detection.

Tests: backend **306 passed** (+~40); AI/ingestion **169 passed, 8
skipped** (+26). Acceptance smoke `p15smoke.py`. See
`docs/REAL_VIDEO_PIPELINE.md`, `docs/VEHICLE_REID.md`.

---

## 3l. SENTINEL Command Center — Phase 16 (IMPLEMENTED)

Turned the app from a set of separate pages into one command-center
product. No new migration (schema head stays at `0014` through this
phase). Five commits, 16A/B/C/F/G/H:

- **`GET /api/v1/command-center/summary`** — one bounded, read-only
  aggregation composed from the existing system-metrics + indexed
  queries; renders as the new landing page (`CommandCenterPage.jsx`), with
  the original Phase 10 dashboard preserved at `/dashboard`. A shared
  primitives library (`primitives.jsx`) gives every panel across the app
  the same badges/cards/buttons.
- **Grouped navigation + command palette**: `Navbar.jsx` groups every
  route under COMMAND / INVESTIGATE / INTELLIGENCE / OPERATIONS / ADMIN
  (all existing routes preserved, none removed); `CommandPalette.jsx`
  (Ctrl+K) routes to any entity or hands a typed phrase straight to the
  copilot; `?` opens a shortcut cheat-sheet.
- **Two real bugs fixed here, not just features added**: the live
  dashboard WebSocket was silently failing its handshake in Chromium
  because `ConnectionManager.connect()` never echoed back the offered
  subprotocol; and a missing/unresolvable evidence snapshot returned a
  bare 404 instead of an honest placeholder image + `X-Evidence-Status`
  header (HTTP 200), which had been breaking evidence carousels.
- **Rebuilt `/workspace`** (`LiveInvestigationWorkspace.jsx`): one header
  (vehicle + plate + status badges) driving a synchronised evidence
  carousel ⇄ journey map ⇄ timeline via a single selected-index state,
  with CONFIRMED sightings in solid green and INFERRED transitions in
  dashed amber everywhere — never visually conflated. `?evt=` persists the
  selection in the URL.
- **Live monitoring wall** (`/live-monitoring`, 1×1 to 4×4 grid) — each
  tile shows its own honest `CameraPlayer` mode, FPS, AI status, and any
  active alert overlay, with an ALERTS-ONLY filter.
- **Sectioned officer work queue** (`/my-work`) — URGENT / ESCALATED /
  ASSIGNED TO ME / OVERDUE / RECENT, with RBAC-gated `[OPEN]`/`[ACK]`/
  `[ASSIGN ME]` actions.
- **Headless-browser validation**: `Dockerfile.e2e` +
  `scripts/browser_test.sh` + `frontend/e2e/*.mjs` run a real Chromium
  against the live stack.

Tests: backend **331 passed** (was 309), AI/ingestion **169 passed**,
browser suite **23/23 passed**.

---

## 3m. Real-Time Multi-Camera Scheduling & Transparent Capacity Model — Phase 17 (MEASURED)

Directly answers the FIFO-starvation finding from §3b ("only ~5 of 30
cameras ever got a processed frame") for the **default, recommended**
single-consumer configuration (`SENTINEL_AI_WORKERS=1`) — §3c's
multi-process worker pool already fixed the same bug, but only for a path
already measured **not** recommended on constrained hardware.

- `ai/scheduler.py` (`FairCameraScheduler`): bounded per-camera queues,
  4 priority classes via smooth-weighted round robin, named drop reasons.
  At equal priority it reproduces §3c's existing round-robin/latest-wins
  behaviour exactly — nothing about the current default changes unless
  configured otherwise.
- `ai/sampling.py` (adaptive per-camera FPS), `ai/modes.py`
  (`DETECTION`/`TRACKING`/`ANPR`/`ALERT` — default `ANPR` is
  byte-for-byte the original pipeline, verified against the full existing
  test suite), `ai/ocr_executor.py` (bounded async OCR, opt-in via
  `SENTINEL_ASYNC_OCR=1`), `ai/degradation.py` (HEALTHY/DEGRADED/OVERLOADED
  from measurable thresholds), `ai/scheduled_consumer.py` (opt-in
  fair-scheduled alternative to the default FIFO consumer, **same
  one-thread CPU profile** — `--fair-scheduler` / `SENTINEL_FAIR_SCHEDULER=1`).
- `ai/capacity.py` + `ai/regions.py`: the actual transparent worked
  calculation the roadmap needs — `measured_worker_capacity × workers =
  estimated_capacity`, every assumption (target FPS, ANPR%, redundancy,
  headroom, GPU speedup) named, overridable, and echoed back rather than
  silently folded into a number that looks measured. `GET
  /api/v1/system/capacity` (JWT-auth) serves it from a committed benchmark
  file with an explicitly-labeled conservative fallback.

**MEASURED on one 8-core CPU-only workstation, 2026-09-09**
(`docs/PHASE17_BENCHMARK.md` — reproduce with `scripts/benchmark_phase17.py`):

| Tier | Result |
| :--- | :--- |
| Scheduler fairness alone (no decode/AI), 10–500 simulated cameras | ~1.0 aggregate FPS sustained at every tier, near-zero RSS growth — the scheduling layer itself is fair and memory-bounded |
| Real decode only (no AI), real mock-video streams | 30–50 concurrent streams decode cleanly at full real-time per-camera FPS with **zero drops**; at 100 configured only 60 reached ONLINE within 20s (a connection-startup limit, not steady-state decode capacity) — 250/500 not attempted, honestly, rather than extrapolated |
| Transparent 80k-camera capacity model, this hardware | At a demanding 2 FPS/camera ANPR-heavy target: **131,293 workers required** — i.e. more workers than cameras, an unflattering but correct restatement of the CPU ceiling in §3b. At a lighter 0.5 FPS / 10% ANPR target: **23,031 workers**. An 8× GPU speedup (explicitly `gpu_speedup_verified: false` — no GPU was available to test) brings that to **2,879 GPUs**. None of these numbers should be read as "SENTINEL supports N cameras today" — they are what the transparent formula outputs from a real baseline plus named assumptions. |

Honest limitations stated in the doc itself: `--fair-scheduler` measured
**worse** than plain FIFO for raw AI throughput on this host (GIL
contention, not fully root-caused); AI-PROCESSED throughput was only
re-validated at N≤10 (re-running the already-known N=30 CPU ceiling from
§3b would add nothing); the regional split/bandwidth/storage estimates
are architectural placeholders, not measurements. See
`docs/SCALE_TO_80000.md` for the deployment-shape discussion these
numbers feed into.

---

## 3n. ANPR Diagnostics — Why Real Footage Returns UNKNOWN — Phase 18 (MEASURED)

Answers, with intermediate evidence rather than a bare UNKNOWN, why real
Sentinel camera footage under-reads plates. `scripts/anpr_diagnostics.py`
runs the real detect → locate → quality-assess → OCR → normalise →
temporal-fusion chain and reports every intermediate value, across
**three strata that are never combined into one number**
(`docs/PHASE18_ANPR_DIAGNOSTICS.md`):

| Stratum | n | Plate located | UNKNOWN rate | Notes |
| :--- | :-: | :-: | :-: | :--- |
| SYNTHETIC (rendered plates, ground truth known) | 30 | 100% | 0% | 70.0% exact / 96.1% char accuracy — measures pipeline wiring only, out-of-distribution font |
| REAL_HISTORICAL (archived real Sentinel-camera JPEGs, no ground truth) | 136 detections | 100% (of 135 detected) | **97.1%** | `OCCLUDED` is the dominant cause (105/132, 80%), then `LOW_RESOLUTION` (16), `LOW_CONFIDENCE` (9) |

The real government RTSP/HLS endpoints were confirmed unreachable from
this development environment during this phase (a raw TCP connect and an
HTTPS request both timed out) — the REAL_HISTORICAL stratum reuses 282
JPEGs captured in an earlier session's RTSP smoke test and is labelled
**PROVENANCE-UNCERTAIN**, never presented as certified live-feed accuracy.
This phase also fixed a real bug found by testing:
`PlateTrackState.expired()`'s `now or time.time()` treated a legitimate
`0.0` timestamp as falsy and evicted the entire plate-track store on the
next call — fixed to an explicit `is not None` check.

**Conclusion, stated plainly in the doc**: real-camera ANPR misses are
overwhelmingly explained by genuine occlusion/low-resolution surveillance
framing, not a fixable OCR bug — a fine-tuned plate detector/OCR head
needs a labeled Sentinel dataset that does not exist locally (§3d's own
conclusion, now with the evidence behind it).

---

## 3o. Failure Resilience, Idempotency & Government Demo Hardening — Phases 19–20 (IMPLEMENTED)

The last hardening pass before submission, organized around one
principle: **one camera failure must not take down the platform**, plus a
final security/idempotency audit.

- **Duplicate-event idempotency** (migration `0015`): the AI pipeline
  retries `POST /events/ai-detection` on any connection error or 5xx —
  including the case where the first attempt actually committed
  server-side but the response never arrived. `vehicle_events.event_id`
  (nullable, unique) plus a pre-insert existence check now makes retried
  delivery of the *same* real detection a no-op instead of a duplicate row
  and a duplicate watchlist alert.
- **Failure-injection tests** (`tests/test_failure_resilience.py`): a
  decoder that raises mid-stream is treated as a dropped frame, not a
  crash; a genuinely corrupt video file fails to open cleanly and the
  worker still reaches OFFLINE/RECONNECTING; `StreamManager.sync_cameras()`
  restarts a dead worker without touching a healthy one running alongside
  it.
- **50-camera rehearsal + designated-vehicle scenario**
  (`scripts/hackathon_rehearsal.py`) — bulk-onboards 50 MOCK cameras from
  this repo's own dataset, verifies GIS + feed assignment on all 50, then
  runs a real (unmodified) AI pipeline burst against a small, explicitly-
  printed subset — never silently presented as "50 cameras fully
  AI-processed" (§3m already measured the honest ceiling).
- **Security audit** (`backend/tests/test_security_audit.py`): JWT expiry/
  tamper/wrong-secret/malformed/deactivated-user all rejected cleanly;
  per-role RBAC verified on real mutating endpoints (OPERATOR blocked from
  camera/watchlist writes, OFFICER permitted); SQL-injection-shaped and
  path-traversal-shaped inputs proven inert; a real bug found and fixed —
  an unbounded `camera_id` could hit Postgres's own btree row-size limit
  and 500 instead of a clean 422, now capped with `Field(max_length=128)`.
  A repo-wide secret scan found zero hardcoded credentials.
- **One-command deterministic demo** (`scripts/hackathon_demo.sh`,
  `scripts/hackathon_health_check.py`) — resets/reseeds the demo dataset,
  verifies the designated-vehicle scenario, runs a full read-only
  infrastructure health check (backend/DB/camera registry/object
  storage/AI pipeline/watchlist/alerts/demo dataset/**real WebSocket
  handshake**), then prints an honest summary — a failing check prints
  "NOT VERIFIED", never a fabricated "READY".
- **Camera-delete 409**: deleting a camera with dependent
  detections/alerts/evidence now returns a clean `409
  CAMERA_HAS_DEPENDENT_RECORDS` instead of an unhandled 500 — refusing to
  silently cascade-delete real investigation evidence.

**Latest measured full-suite result in this section: backend 365 passed,
AI/ingestion 269 passed / 8 skipped, zero regressions** (commit `4e51f20`).
See `docs/GOVERNMENT_FEED_READINESS.md`, `docs/HACKATHON_DEMO_RUNBOOK.md`.

---

## 3p. Landing Experience & Submission Polish (IMPLEMENTED)

Final pre-submission pass, UI/asset-only — no backend, pipeline, or
security-model changes:

- A cinematic scroll-narrative pre-login landing page
  (`frontend/src/components/home/`, GSAP + ScrollTrigger + Lenis) replaces
  the placeholder landing screen, entirely scoped to its own `.hp-root` so
  the authenticated command-center theme is untouched. Its product-reveal
  and how-it-works sections embed real screenshots captured from a
  locally-running SENTINEL instance seeded with this repo's own
  deterministic demo dataset, and its correlation animation replays the
  real seeded `GJ18TC0450` journey — not mockups.
- `mediaTicket.js` evidence/media-ticket fetching was made reactive
  (`useMediaTicket()` pub-sub hook) — a hard page reload used to leave
  evidence images permanently broken because a component could render
  before the async ticket resolved and latch a non-retrying failure state.
- Demo-runbook and doc numbers (migration head, test counts, ANPR strata)
  reconciled against the state actually measured above; failure-demo and
  backup-plan sections added to `docs/HACKATHON_DEMO_RUNBOOK.md` for live
  evaluation.
- `pitch_video/` and `screenshots/`/`screen_shot/` hold the recorded
  product-demo video and screenshot suite produced for submission
  (`scripts/`, Playwright-based recording/capture scripts) — evaluation
  assets, not application code.

---

## 4. Team & Repository Branch Matrix

```text
                                main
                                  │
          MASTER SYSTEM DOCUMENTATION & ARCHITECTURE BLUEPRINTS ONLY
                                  │
                               testing
                                  │ (Central Integration Project & Docker Infrastructure)
        ┌───────────┬─────────────┼─────────────┬───────────┐
        │           │             │             │           │
        ▼           ▼             ▼             ▼           ▼
      Isha       Vishakha       Kavya        Prajin       Rishit & Vanshal
  (frontend)  (investigation)  (ai-anpr)   (tracking)    (stream / backend)
        │           │             │             │           │
        └───────────┴─────────────┼─────────────┴───────────┘
                                  │ Pull Requests
                                  ▼
                               testing
```

Everything from §3i onward (operational layer through submission polish)
was built after the initial cross-team merge, directly on `penultimate`
— the platform's current default branch and the one this README
describes.

---

## 5. Master Documentation Index

Explore the complete technical blueprints contained in this repository branch:

- [`ARCHITECTURE.md`](ARCHITECTURE.md): Hybrid Models 1–5 strategy & master data pipeline.
- [`API_CONTRACTS.md`](API_CONTRACTS.md): Standardized JSON schemas for REST APIs and WebSockets.
- [`AI_ARCHITECTURE.md`](AI_ARCHITECTURE.md): YOLOv8, plate crop localization, CLAHE, EasyOCR & consensus voting.
- [`CCTV_INTEGRATION.md`](CCTV_INTEGRATION.md): `POST /api/v1/cameras/sync` catalogue, RTSP over TCP, PTS frame timing & backoff engine.
- [`DEMO_RUNBOOK.md`](DEMO_RUNBOOK.md): exact fresh-clone startup + the mock ANPR demo flow (`GJ18TC0450`) and real-camera fallback.
- [`DATABASE_ARCHITECTURE.md`](DATABASE_ARCHITECTURE.md): PostgreSQL 15 + PostGIS 3.3 schemas & spatial indexing.
- [`SCALABILITY.md`](SCALABILITY.md): 50 camera PoC to 80,000 camera statewide expansion **roadmap** (not yet implemented — see the doc's own top-of-file note).
- [`SECURITY.md`](SECURITY.md): JWT (HS256) authentication, RBAC roles, audit logging — each line tagged IMPLEMENTED vs ROADMAP.
- [`SENTINEL_System_Audit_Report.md`](SENTINEL_System_Audit_Report.md): full code-verified audit of what's actually implemented vs. documented, with file:line citations.
- [`DEPLOYMENT.md`](DEPLOYMENT.md): Docker Compose orchestration & environment configuration.
- [`INFRASTRUCTURE.md`](INFRASTRUCTURE.md): Hardware sizing, GPU memory allocations & network bandwidth budgets.
- [`WATCHLIST_AND_ALERTS.md`](WATCHLIST_AND_ALERTS.md): Watchlist lookup, alert cooldown deduplication & WebSocket push.
- [`GIS_AND_INVESTIGATION.md`](GIS_AND_INVESTIGATION.md): CartoDB Leaflet mapping, polyline route vectors & PDF report generation.
- [`TESTING.md`](TESTING.md): Stream failure injection suite, unit tests & load benchmarks.
- [`4_DAY_EXECUTION.md`](4_DAY_EXECUTION.md): Day 1–4 day-by-day implementation roadmap.
- [`SUBMISSION_REQUIREMENTS.md`](SUBMISSION_REQUIREMENTS.md): Hackathon evaluation rubric compliance.
- [`TEAM_TASKS.md`](TEAM_TASKS.md): Detailed task breakdown for each team member.
- [`SYSTEM_STATUS.md`](SYSTEM_STATUS.md): Living status log of every phase, deferred item, and known gap.

**Phase 8+ deep-dive docs** (`docs/`), each following the same
IMPLEMENTED-vs-ROADMAP / reproducible-command discipline as §3i–3p above:

- [`docs/HACKATHON_ARCHITECTURE.md`](docs/HACKATHON_ARCHITECTURE.md) / [`docs/HACKATHON_DEMO_RUNBOOK.md`](docs/HACKATHON_DEMO_RUNBOOK.md): the 2-minute demo script, failure-demo, and backup plan.
- [`docs/AI_INVESTIGATION_COPILOT.md`](docs/AI_INVESTIGATION_COPILOT.md) / [`docs/AI_SEARCH.md`](docs/AI_SEARCH.md) / [`docs/AI_DEMO_RUNBOOK.md`](docs/AI_DEMO_RUNBOOK.md): the deterministic-first copilot, NL search, and its own demo flow.
- [`docs/AI_BEHAVIOR_ANALYTICS.md`](docs/AI_BEHAVIOR_ANALYTICS.md) / [`docs/BEHAVIOR_ANALYTICS.md`](docs/BEHAVIOR_ANALYTICS.md): stopped-vehicle, wrong-way, and restricted-zone anomaly detection.
- [`docs/ADVANCED_VIDEO_INTELLIGENCE.md`](docs/ADVANCED_VIDEO_INTELLIGENCE.md) / [`docs/VEHICLE_REID.md`](docs/VEHICLE_REID.md) / [`docs/CROSS_CAMERA_INTELLIGENCE.md`](docs/CROSS_CAMERA_INTELLIGENCE.md) / [`docs/TRAFFIC_INTELLIGENCE.md`](docs/TRAFFIC_INTELLIGENCE.md) / [`docs/CAMERA_RELIABILITY.md`](docs/CAMERA_RELIABILITY.md) / [`docs/INVESTIGATION_AGENT.md`](docs/INVESTIGATION_AGENT.md): Phase 14's Re-ID, correlation, traffic, reliability, and agent components.
- [`docs/REAL_VIDEO_PIPELINE.md`](docs/REAL_VIDEO_PIPELINE.md) / [`docs/LIVE_INVESTIGATION.md`](docs/LIVE_INVESTIGATION.md) / [`docs/ANPR_PIPELINE.md`](docs/ANPR_PIPELINE.md): Phase 15's honest camera playback, workspace, and ANPR quality pipeline.
- [`docs/PHASE17_BENCHMARK.md`](docs/PHASE17_BENCHMARK.md) / [`docs/SCALE_TO_80000.md`](docs/SCALE_TO_80000.md): the fair scheduler and the transparent, measured 80,000-camera capacity model.
- [`docs/PHASE18_ANPR_DIAGNOSTICS.md`](docs/PHASE18_ANPR_DIAGNOSTICS.md): the SYNTHETIC/MOCK/REAL_HISTORICAL ANPR failure-reason breakdown behind §3n.
- [`docs/GOVERNMENT_FEED_READINESS.md`](docs/GOVERNMENT_FEED_READINESS.md): real RTSP/HLS endpoint reachability status and what's still required to go live on government feeds.
- [`docs/gis_metadata.md`](docs/gis_metadata.md): camera GIS coordinate/registry metadata reference.
