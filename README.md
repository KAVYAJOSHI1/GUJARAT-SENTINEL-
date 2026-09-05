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

## 3. Team & Repository Branch Matrix

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

## 4. Master Documentation Index

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
