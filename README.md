# SENTINEL — CCTV Integration & Video Analytics Platform

### Gujarat Police Innovation Hackathon 2026

![Sentinel Banner](https://img.shields.io/badge/Gujarat_Police-Hackathon_2026-blue?style=for-the-badge)
![Architecture](https://img.shields.io/badge/Architecture-Hybrid_Models_1--5-emerald?style=for-the-badge)
![Status](https://img.shields.io/badge/Status-Initial_Workspace_Setup-orange?style=for-the-badge)

---

## 1. Project Overview

**SENTINEL** is a next-generation, vendor-neutral CCTV video analytics and intelligence platform built to integrate government-provided camera streams, perform automated vehicle detection, ANPR, and OCR, track vehicles across heterogeneous camera networks, correlate detections against law enforcement watchlists, and visualize vehicle routes on interactive GIS maps.

The architecture is built on a **Hybrid Model combining Reference Models 1–5**, establishing a foundation capable of scaling from an initial **~50 camera PoC** to a statewide grid of **~80,000 cameras**.

---

## 2. Core Problem & Solution

### The Challenge
- Ingesting heterogeneous CCTV feeds across departments (Police, Traffic, Municipalities) with varying codecs (H.264/H.265) and protocols (RTSP, WebRTC, HLS).
- Processing multi-camera streams in real-time to detect vehicles and extract license plate registration numbers under varying lighting and motion conditions.
- Reconstructing a vehicle's chronological journey across different cameras without relying on local camera track IDs.
- Instantly alerting law enforcement when blacklisted or stolen vehicles appear on public feeds.

### The SENTINEL Solution
- **Catalogue Ingest (`/api/ingest`)**: Standardized onboarding of government camera catalogues.
- **Resilient Stream Ingestion**: RTSP over TCP with automatic exponential backoff reconnection.
- **AI Analytics Pipeline**: Pretrained YOLOv8 vehicle detection + ANPR plate crop + PaddleOCR with multi-frame consensus.
- **Cross-Camera Vehicle Intelligence**: Global correlation of vehicle identity based on normalized registration numbers.
- **Watchlist & Real-Time Alerts**: Sub-second alert dispatch over WebSockets to command dashboard operators.
- **Interactive GIS Map & Vehicle Route Reconstruction**: Visual trajectory mapping over PostGIS spatial layers.

---

## 3. Team & Module Ownership

| Developer | Role & Module Ownership | Core Technologies | Dedicated Git Branch |
| :--- | :--- | :--- | :--- |
| **Isha** | Frontend + Main Command Dashboard | React.js, Tailwind/Vanilla CSS, WebSockets | `feature/isha-frontend` |
| **Vishakha** | GIS + Vehicle Investigation + Reports | Leaflet, OpenLayers, PostGIS, jsPDF | `feature/vishakha-investigation` |
| **Kavya** | AI + ANPR / OCR Engine | PyTorch, YOLOv8, OpenCV, PaddleOCR | `feature/kavya-ai-anpr` |
| **Prajin** | Vehicle Tracking + Cross-Camera Correlation | ByteTrack, Spatial-Temporal Indexing | `feature/prajin-tracking` |
| **Rishit** | CCTV Stream Ingestion & Stream Manager | OpenCV, FFmpeg, RTSP/TCP, Reconnect Engine | `feature/rishit-stream` |
| **Vanshal** | Backend APIs + Database + Watchlist + Alerts | FastAPI, PostgreSQL, PostGIS, MinIO, WebSockets | `feature/vanshal-backend` |

---

## 4. Repository Branching Strategy

We enforce a **Single Central Repository** strategy with 8 dedicated branches:

```text
                                main
                                  │
                              PROTECTED (Final Integration)
                                  │
                               testing
                                  │ (Central Integration Branch)
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
                                  │ Automated & Manual Integration Tests
                                  ▼
                                main
```

> [!IMPORTANT]
> **Branch Rules**:
> 1. **Nobody pushes directly to `main`**. `main` is reserved exclusively for production-ready releases.
> 2. All active feature development occurs inside `feature/<name>-<module>`.
> 3. Features merge into `testing` via Pull Request for central system validation before merging into `main`.

---

## 5. Master System Architecture

```text
                     GOVERNMENT CCTV GRID
                              │
                              ▼
                      CAMERA CATALOGUE
                              │
                              ▼
                         /api/ingest
                              │
                              ▼
                      CAMERA REGISTRY
                              │
                              ▼
                      STREAM MANAGER (RTSP/TCP)
                              │
                              ▼
                      VIDEO PROCESSING LAYER
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
           VEHICLE         PERSON          OTHER
          DETECTION       DETECTION       ANALYTICS
              │
              ▼
           TRACKING (ByteTrack)
              │
              ▼
        PLATE DETECTION (ANPR)
              │
              ▼
             OCR (PaddleOCR)
              │
              ▼
       VEHICLE REGISTRATION (Multi-Frame Consensus)
              │
              ▼
         EVENT ENGINE
              │
        ┌─────┴─────┬────────────────┐
        ▼           ▼                ▼
    PostgreSQL  Watchlist        Evidence
    + PostGIS     Engine          Storage (MinIO)
        │           │
        │           ▼
        │         ALERT (WebSocket)
        │           │
        └─────┬─────┘
              │
              ▼
    CROSS-CAMERA CORRELATION
              │
        ┌─────┴──────┐
        ▼            ▼
       GIS      INVESTIGATION
        │            │
        └─────┬──────┘
              │
              ▼
        WEB DASHBOARD
```

---

## 6. Quick Start & Local Setup

### Prerequisites
- Docker & Docker Compose
- Git
- Python 3.10+
- Node.js 18+

### 1. Clone & Set Environment
```bash
git clone git@github.com:KAVYAJOSHI1/GUJARAT-SENTINEL-.git
cd GUJARAT-SENTINEL-
cp .env.example .env
```

### 2. Start Full Stack Infrastructure with Docker Compose
```bash
docker-compose up --build -d
```
This launches:
- **PostgreSQL + PostGIS**: `localhost:5432`
- **MinIO Object Storage**: `localhost:9000` (Console: `localhost:9001`)
- **FastAPI Backend**: `localhost:8000`
- **Stream Ingestion Service**: `localhost:8001`
- **React Command Dashboard**: `localhost:3000`

---

## 7. Inter-Module Data Contracts Summary

- **Ingestion ➔ AI**: RTSP frame references with PTS timestamps.
- **AI ➔ Backend**: `GET /api/v1/events/ai-detection` containing `camera_id`, `track_id`, `plate_number`, `confidence`, `vehicle_type`, and `evidence_snapshot_path`.
- **Backend ➔ Frontend**: REST endpoints for vehicle search history and WebSocket push notifications for watchlist matches (`ws://localhost:8000/ws/alerts`).

Detailed contract schemas are documented in [`docs/API_CONTRACTS.md`](docs/API_CONTRACTS.md).

---

## 8. Development & Integration Workflow

1. Checkout your feature branch:
   ```bash
   git checkout feature/<your-branch-name>
   ```
2. Develop module features according to your execution guide in `DEVELOPER_README.md`.
3. Test locally using unit tests and mock video samples.
4. Push your branch and open a Pull Request into `testing`:
   ```bash
   git push origin feature/<your-branch-name>
   ```
5. Perform integration testing on the `testing` branch before final merge to `main`.
