# SENTINEL — 4-Day End-to-End Implementation Plan

This document outlines the day-by-day implementation strategy for delivering the **SENTINEL** CCTV Integration & Video Analytics Platform within the 4-day hackathon timeline.

---

# DAY 1 — Foundation & Core Ingestion Pipeline

### Primary Target
**Government CCTV Stream Ingestion ➔ AI Vehicle Detection**

### Modules & Tasks
- **Rishit (Ingestion)**:
  - Implement `/api/ingest` catalogue parser for camera metadata.
  - Setup OpenCV/FFmpeg stream ingestion using RTSP over TCP.
  - Establish PTS timestamp synchronization.
- **Kavya (AI)**:
  - Load pretrained YOLOv8 detector (`yolov8n.pt`).
  - Extract vehicle bounding boxes (`car`, `truck`, `bus`, `motorcycle`).
- **Vanshal (Backend & DB)**:
  - Initialize FastAPI backend service & Docker environment.
  - Execute PostgreSQL + PostGIS schema migration scripts.
- **Isha (Frontend)**:
  - Setup React.js project scaffolding and top navigation layout.
  - Build mock Stat Cards for dashboard overview.
- **Vishakha (GIS)**:
  - Setup Leaflet interactive map component with Dark Matter tiles.

### End-of-Day Milestone
```text
Government Stream ──► Video Frame ──► YOLO Vehicle Detection Bounding Box
```

---

# DAY 2 — Tracking, ANPR & Event Engine

### Primary Target
**Vehicle Track ➔ Plate Region Proposal ➔ OCR ➔ Event Database Ingestion**

### Modules & Tasks
- **Prajin (Tracking)**:
  - Integrate ByteTrack multi-object tracker with YOLO detection bounding boxes.
  - Assign local persistent track IDs (`Track #42`) per camera feed.
- **Kavya (AI & ANPR)**:
  - Implement plate region proposal locator and crop extraction.
  - Integrate PaddleOCR for plate character extraction.
  - Build multi-frame consensus voting logic to eliminate OCR character misreads.
- **Vanshal (Backend & DB)**:
  - Build `/api/v1/events/ai-detection` ingestion endpoint.
  - Connect MinIO object storage for snapshot and plate crop uploads.
- **Vishakha (GIS & Investigation)**:
  - Build vehicle search bar input and basic search result cards.

### End-of-Day Milestone
```text
Vehicle Detection ──► ByteTrack Track ID ──► Plate Crop ──► OCR ──► Multi-Frame Consensus ──► Database Event
```

---

# DAY 3 — Hero Feature: Cross-Camera Intelligence, GIS & Alerts

### Primary Target
**Vehicle Search (`GJ01AB1234`) ➔ Chronological History ➔ GIS Route ➔ Watchlist Alert Dispatch**

### Modules & Tasks
- **Prajin & Vanshal (Correlation & Backend)**:
  - Build cross-camera chronological identity query (`GET /api/v1/vehicles/search?plate=GJ01AB1234`).
  - Implement Watchlist lookup engine and alert record generator.
  - Build WebSocket alert dispatcher (`ws://localhost:8000/ws/alerts`).
- **Vishakha (GIS & Investigation)**:
  - Render connected polyline vectors on Leaflet map for target vehicle journey.
  - Build Evidence Viewer Modal displaying high-res snapshots and plate crops.
- **Isha (Frontend)**:
  - Connect WebSocket alert listener to main dashboard for instant popup toasts.
  - Implement Live Camera Grid view with HLS/video preview fallbacks.

### End-of-Day Milestone
```text
Search "GJ01AB1234" ──► Chronological Camera Trajectory ──► Leaflet Polyline Route ──► Watchlist Match Alert Toast
```

---

# DAY 4 — System Hardening, Testing & Hackathon Demonstration

### Primary Target
**System Resilience Verification, Reconnection Stress Testing, UI Polish & Final Demo**

> [!WARNING]
> **Strict Rule**: DO NOT introduce major new features or architectural redesigns on Day 4. Focus strictly on stability, bug fixes, and demo preparation.

### Modules & Tasks
- **Full Team**:
  - Execute Government Feed resilience tests (simulate camera disconnects & verify exponential backoff reconnection).
  - Verify multi-camera H.264 / H.265 ingestion stability.
  - Final UI styling pass: harmonize dark theme glassmorphism aesthetics.
  - Prepare high-resolution presentation slides and live demonstration fallback recordings.
  - Execute final Docker Compose build verification.

### End-of-Day Milestone
**Complete working PoC demonstration meeting all hackathon requirements.**
