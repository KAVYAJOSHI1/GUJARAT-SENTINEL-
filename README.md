# SENTINEL — CCTV Integration & Video Analytics Platform

### Gujarat Police Innovation Hackathon 2026

![Sentinel Banner](https://img.shields.io/badge/Gujarat_Police-Hackathon_2026-blue?style=for-the-badge)
![Architecture](https://img.shields.io/badge/Architecture-Hybrid_Models_1--5-emerald?style=for-the-badge)
![Status](https://img.shields.io/badge/Documentation-Master_Branch-purple?style=for-the-badge)

---

## 1. Executive Overview

**SENTINEL** is a CCTV video analytics and intelligence platform prototype built for the **Gujarat Police Innovation Hackathon 2026**. As implemented today it is a **single-node Docker Compose PoC** (see `SENTINEL_System_Audit_Report.md` for a full, code-verified teardown): it ingests real Sentinel RTSP camera feeds plus optional local mock-camera clips, runs automated vehicle detection, ANPR, and OCR, correlates detections across cameras by matched plate string, matches sightings against a watchlist, and visualizes vehicle trajectories on PostGIS-powered Leaflet maps.

The architecture is designed with the seams (stateless backend, per-camera isolation, a clean ingestion/AI/backend contract) a larger deployment would need — **ROADMAP, not implemented today**: `SCALABILITY.md`'s statewide **~80,000 camera** / Kubernetes / Kafka / Triton architecture is a target design, evaluated against no infrastructure that exists in this repository yet (no K8s manifests, no Kafka topics, `device="cpu"` hardcoded everywhere). The system currently runs as one process pool against `docker-compose.yml`, correctly scoped to its stated **~50-camera PoC** target.

---

## 2. Platform Capability Matrix

| Feature Domain | Technical Implementation | Operational Impact |
| :--- | :--- | :--- |
| **Stream Ingestion** | RTSP over TCP, WebRTC, HLS, PTS Timestamping, Exponential Backoff | Resilient ingestion across erratic network environments |
| **AI Analytics** | YOLOv8 Vehicle Detection + EasyOCR (PaddleOCR optional) + Multi-Frame Consensus | ANPR accuracy is **not yet benchmarked against a real labeled dataset** (none exists locally — real-camera accuracy therefore *cannot* be stated statistically, only qualitatively). `scripts/evaluate_anpr.py` has a synthetic-font mode (measured this pass: **87.5% exact / 98.3% char**, up from 70.8% / 85.8% — but rendered fonts are out-of-distribution and its own output refuses to let those be quoted as real accuracy) and a real-`--dataset` mode for when labeled footage exists. No ">95%" or any accuracy figure should be cited as real until that run is done. See §3d below and `SENTINEL_System_Audit_Report.md` §3. |
| **Cross-Camera Correlation** | ByteTrack Spatial-Temporal Indexing + Normalized Plate Matching | Chronological vehicle journey reconstruction across cameras |
| **Watchlist & Alerts** | FastAPI Engine + 5-Min Cooldown Deduplication + WebSockets | Sub-second alert delivery to command center operators |
| **GIS & Investigation** | PostGIS Spatial Point Layers + Leaflet Polyline Vector Mapping | Interactive visual map trajectories & automated PDF evidence reports |

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
