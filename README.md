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
| **AI Analytics** | YOLOv8 Vehicle Detection + EasyOCR (PaddleOCR optional) + Multi-Frame Consensus | ANPR accuracy is **not yet benchmarked against a real labeled dataset** — `scripts/evaluate_anpr.py` supports both a synthetic-font mode (not representative) and a real-`--dataset` mode, and its own output explicitly refuses to let the synthetic numbers be quoted as real accuracy. No ">95%" or any other accuracy figure should be cited until that real-data run has actually been done; see `SENTINEL_System_Audit_Report.md` §3 (ANPR EVALUATION) for the exact benchmark plan. |
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
CPU/RAM trend-over-time leak detection, the 1/5/10/20/30-camera load ladder
itself (the harness supports it; running all five tiers back-to-back and
publishing the breakdown point wasn't done in this pass), and anything at
the real `cam04`/`cam06` Sentinel source (unreachable from this environment
when this was written — the harness works identically against it once
reachable).

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
- [`AI_ARCHITECTURE.md`](AI_ARCHITECTURE.md): YOLOv8, plate crop localization, CLAHE, PaddleOCR & consensus voting.
- [`CCTV_INTEGRATION.md`](CCTV_INTEGRATION.md): `/api/ingest`, RTSP over TCP, PTS frame timing & backoff engine.
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
