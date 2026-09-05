# SENTINEL — Master System Architecture Specification

---

## 1. Hybrid Architecture Strategy (Models 1–5 Integration)

SENTINEL unifies **Reference Models 1–5** into a cohesive enterprise architecture:

```text
                  [ Model 1: Edge Stream Ingestion ]
                 (RTSP/TCP workers, PTS timestamping)
                                  │
                                  ▼
                  [ Model 2: AI Analytics Engine ]
                (YOLOv8 + EasyOCR + Consensus Voting)
                                  │
                                  ▼
                  [ Model 3: Spatial Database & Storage ]
                (PostgreSQL 15 + PostGIS 3.3 + MinIO)
                                  │
                                  ▼
                  [ Model 4: Watchlist & Alert Router ]
              (FastAPI + 5-Min Cooldown + WebSocket Server)
                                  │
                                  ▼
                  [ Model 5: Command Center & GIS Map ]
              (React.js + CartoDB Leaflet + Vector Trajectory)
```

---

## 2. End-to-End System Data Flow

```text
[ Government CCTV Grid ]
        │ (RTSP over TCP)
        ▼
[ POST /api/v1/cameras/sync ] ──► [ Stream Ingestion Manager ] ──► [ Decoded Frame Buffer ]
      (camera catalogue)
                                                                       │ (PTS Timestamp)
                                                                       ▼
[ Web Dashboard ] ◄── [ WebSocket Alert ] ◄── [ Watchlist Engine ] ◄── [ AI ANPR Pipeline ]
    │                      │                      │                     (YOLOv8 + EasyOCR)
    ▼                      ▼                      ▼                             │
[ GIS Trajectory ] ◄── [ Alert Store ] ◄── [ PostGIS DB ] ◄── [ Snapshot Storage ] (MinIO)
```

---

## 3. Core Architectural Modules

1. **Ingestion Layer (`ingestion/`)**: Multi-threaded Python workers, forcing RTSP over TCP transport and extracting Presentation Time Stamps (PTS).
2. **AI Analytics Layer (`ai/`)**: PyTorch inference pipeline combining YOLOv8 vehicle detection, CLAHE contrast enhancement, EasyOCR text extraction (PaddleOCR optional via `OCR_ENGINE=paddleocr`), and multi-frame consensus voting.
3. **Tracking & Correlation Layer (`ai/tracking/`)**: ByteTrack tracker binding local track IDs to plate strings and assembling cross-camera chronological trajectories.
4. **Backend Services (`backend/`)**: FastAPI microservice serving REST APIs, executing PostGIS spatial queries, and managing WebSocket client connection pools.
5. **Database & Storage (`database/`)**: PostgreSQL 15 with PostGIS extension for spatial querying, paired with MinIO S3 object storage for evidence snapshot images.
6. **Frontend Command Center (`frontend/`)**: React 18 single-page application featuring live video grids, real-time toast popups, and Leaflet vector mapping.
