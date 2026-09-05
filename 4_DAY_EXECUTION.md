# SENTINEL — 4-Day Execution & Development Roadmap

---

## 1. Day-by-Day Technical Milestones

- **Day 1 — Workspace & Infrastructure Initialization**:
  - Initialize Docker Compose stack (PostgreSQL + PostGIS, MinIO).
  - Setup API contracts and initial database schemas.
  - Setup developer feature branches and initial execution guides.

- **Day 2 — Ingestion & AI Pipeline Development**:
  - Build RTSP over TCP stream ingestion workers with PTS timestamping.
  - Build YOLOv8 vehicle detection and EasyOCR ANPR pipeline.
  - Build FastAPI REST backend endpoints.

- **Day 3 — Integration, Tracking & Watchlist Engine**:
  - Build ByteTrack object tracking and multi-frame consensus voting logic.
  - Build Watchlist cross-referencing engine with 5-minute alert cooldown deduplication.
  - Connect WebSocket alert push notifications to React command center.

- **Day 4 — GIS Mapping, System Polish & PR Merge**:
  - Build Leaflet vector polyline map trajectory overlays.
  - Execute end-to-end integration tests on `testing` branch.
  - Finalize PDF evidence report export and demonstrate PoC.
