# SENTINEL — CCTV Integration & Video Analytics Platform

### Gujarat Police Innovation Hackathon 2026

![Sentinel Banner](https://img.shields.io/badge/Gujarat_Police-Hackathon_2026-blue?style=for-the-badge)
![Architecture](https://img.shields.io/badge/Architecture-Hybrid_Models_1--5-emerald?style=for-the-badge)
![Status](https://img.shields.io/badge/Documentation-Master_Branch-purple?style=for-the-badge)

---

## 1. Executive Overview

**SENTINEL** is a enterprise-grade, vendor-neutral CCTV video analytics and intelligence platform engineered for law enforcement agencies. Built for the **Gujarat Police Innovation Hackathon 2026**, the system standardizes heterogeneous government CCTV streams across departmental boundaries, executes automated vehicle detection, ANPR, and OCR, correlates detections across disparate cameras, matches sightings against real-time watchlists, and visualizes vehicle trajectories on PostGIS-powered Leaflet maps.

The core architecture combines **Reference Models 1–5**, establishing a scalable foundation engineered to expand seamlessly from an initial **~50 camera PoC** to a statewide grid of **~80,000 cameras**.

---

## 2. Platform Capability Matrix

| Feature Domain | Technical Implementation | Operational Impact |
| :--- | :--- | :--- |
| **Stream Ingestion** | RTSP over TCP, WebRTC, HLS, PTS Timestamping, Exponential Backoff | Resilient ingestion across erratic network environments |
| **AI Analytics** | YOLOv8 Vehicle Detection + PaddleOCR + Multi-Frame Consensus | $>95\%$ ANPR plate recognition accuracy under motion blur |
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
- [`SCALABILITY.md`](SCALABILITY.md): 50 camera PoC to 80,000 camera statewide expansion blueprint.
- [`SECURITY.md`](SECURITY.md): JWT authentication, RBAC roles, AES-256 evidence encryption & audit logging.
- [`DEPLOYMENT.md`](DEPLOYMENT.md): Docker Compose orchestration & environment configuration.
- [`INFRASTRUCTURE.md`](INFRASTRUCTURE.md): Hardware sizing, GPU memory allocations & network bandwidth budgets.
- [`WATCHLIST_AND_ALERTS.md`](WATCHLIST_AND_ALERTS.md): Watchlist lookup, alert cooldown deduplication & WebSocket push.
- [`GIS_AND_INVESTIGATION.md`](GIS_AND_INVESTIGATION.md): CartoDB Leaflet mapping, polyline route vectors & PDF report generation.
- [`TESTING.md`](TESTING.md): Stream failure injection suite, unit tests & load benchmarks.
- [`4_DAY_EXECUTION.md`](4_DAY_EXECUTION.md): Day 1–4 day-by-day implementation roadmap.
- [`SUBMISSION_REQUIREMENTS.md`](SUBMISSION_REQUIREMENTS.md): Hackathon evaluation rubric compliance.
- [`TEAM_TASKS.md`](TEAM_TASKS.md): Detailed task breakdown for each team member.
