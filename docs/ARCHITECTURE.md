# SENTINEL — System Architecture Specification

## Gujarat Police Innovation Hackathon 2026
**Platform**: Sentinel CCTV Integration & Video Analytics Platform  
**Architecture Paradigm**: Hybrid Architecture (Models 1–5 Integration)

---

# 1. Executive Summary & Vision

SENTINEL is an enterprise-grade, modular, vendor-neutral CCTV intelligence and video analytics platform engineered to onboard multi-departmental government CCTV feeds, execute real-time AI computer vision (Vehicle Detection, ANPR, OCR, Tracking), correlate vehicle detections across heterogeneous camera grids, cross-reference detections against law enforcement watchlists, and provide interactive GIS visualization and investigative telemetry for state security operations.

The platform is designed to seamlessly scale from an initial **~50 camera proof-of-concept (PoC)** to a statewide infrastructure spanning **~80,000 cameras**.

---

# 2. Master System Architecture Flow

```text
                                GOVERNANCE & CCTV GRID
                                (Government Camera Feeds)
                                           |
                                           v
                                   CAMERA CATALOGUE
                                           |
                                           v
                                    /api/ingest
                                           |
                                           v
                                    CAMERA REGISTRY
                                    (PostGIS Metadata)
                                           |
                                           v
                                    STREAM MANAGER
                                    (RTSP over TCP)
                                           |
                                           v
                                  VIDEO PROCESSING LAYER
                                           |
               +---------------------------+---------------------------+
               |                           |                           |
               v                           v                           v
       VEHICLE DETECTION            PERSON DETECTION            OTHER ANALYTICS
       (YOLOv8 Classifiers)            (Pedestrian)              (Crowd/Motion)
               |
               v
        VEHICLE TRACKING
        (ByteTrack Multi-Object)
               |
               v
        PLATE DETECTION
        (ANPR Region Proposal)
               |
               v
             OCR
        (PaddleOCR Engine)
               |
               v
      VEHICLE REGISTRATION
        (Multi-Frame Consensus)
               |
               v
          EVENT ENGINE
               |
      +--------+--------+-----------------------+
      |                 |                       |
      v                 v                       v
 PostgreSQL         Watchlist               Evidence
 + PostGIS           Engine                 Storage
  Storage       (Critical Matches)         (MinIO/S3)
      |                 |                       |
      |                 v                       v
      |               ALERT                  Metadata
      |                 |                       |
      +--------+--------+                       |
               |                                |
               v                                |
     CROSS-CAMERA CORRELATION  <----------------+
               |
      +--------+--------+
      |                 |
      v                 v
     GIS          INVESTIGATION
   MAPPING           CONSOLE
      |                 |
      +--------+--------+
               |
               v
         WEB DASHBOARD
      (React Command Center)
```

---

# 3. Hybrid Architecture Framework (Models 1–5 Integration)

The SENTINEL platform integrates the core advantages of Reference Models 1 through 5:

## Model 1 — Registry & GIS Foundation
- **Central Camera Registry**: Maintains comprehensive inventory of all camera assets across departments (Police, Traffic, Municipal, Highways).
- **PostGIS Geospatial Metadata**: Stores precise latitude/longitude, mounting height, lens field of view, bearing angle, and coverage radii.
- **Health Telemetry**: Tracks real-time status (Online, Offline, Reconnecting, Frame-Drop Rate).

## Model 2 — Unified Viewing & Analytics
- **Single Pane of Glass**: Aggregates live feeds and operational telemetry into a unified operator dashboard.
- **Real-Time AI Overlay**: Overlays detection bounding boxes, tracking vectors, and recognized license plates onto video streams.
- **Instant Event Feed**: Streams automated vehicle detections and critical alerts in real-time.

## Model 3 — VMS Federation & Middleware
- **Vendor & Codec Neutrality**: Normalizes streams from heterogeneous hardware (Hikvision, Dahua, Axis, Hanwha) and VMS platforms (Milestone, Genetec).
- **Multi-Protocol Abstraction**: Ingests RTSP, WebRTC, WHEP, and HLS, abstracting physical stream quirks behind standard internal interfaces.

## Model 4 — Central VMS & AI Platform
- **Central Intelligence Hub**: Ingests visual telemetry from edge feeds to perform centralized ANPR matching and identity tracking.
- **Watchlist Engine**: Real-time cross-referencing of extracted plate numbers against law enforcement databases.
- **Vehicle Investigation Suite**: Chronological movement reconstruction, evidence snapshot generation, and audit trail retention.

## Model 5 — Hybrid / Innovative Architecture
- **Distributed Gateway Nodes**: Supports Regional Gateways and Edge AI devices (NVIDIA Jetson) to run lightweight detection at the edge.
- **Bandwidth Optimization**: Transmits metadata (JSON events + keyframe crops) over WAN, requesting high-resolution stream clips only upon investigative query.
- **Scalable Event Bus**: Uses Kafka/Redpanda message brokers for high-throughput event distribution across analytical workers.

---

# 4. Team Module Ownership & Boundaries

```text
+------------------------------------------------------------------------+
|                                RISHIT                                  |
|                 CCTV Ingestion & Stream Processing                     |
|            - Catalogue Ingest (/api/ingest) & RTSP/TCP                 |
|            - PTS Timing, Reconnection Backoff & Health                 |
+-----------------------------------+------------------------------------+
                                    |
                                    v
+------------------------------------------------------------------------+
|                                 KAVYA                                  |
|                          AI + ANPR / OCR                               |
|            - Pretrained YOLO Vehicle & Plate Detection                 |
|            - Image Preprocessing & Multi-Frame Consensus OCR           |
+-----------------------------------+------------------------------------+
                                    |
                                    v
+------------------------------------------------------------------------+
|                                PRAJIN                                  |
|               Vehicle Tracking & Cross-Camera Correlation              |
|            - ByteTrack Local Track IDs & Vehicle Trajectory            |
|            - Global Plate Identity Correlation across Cameras          |
+-----------------------------------+------------------------------------+
                                    |
                                    v
+------------------------------------------------------------------------+
|                                VANSHAL                                 |
|               Backend + DB + Watchlist + Alert Engine                  |
|            - FastAPI REST/WS Services, PostgreSQL + PostGIS            |
|            - Watchlist Lookup, Alert Dispatch, MinIO Evidence          |
+-----------------------------------+------------------------------------+
                                    |
                  +-----------------+-----------------+
                  |                                   |
                  v                                   v
+-----------------------------------+ +-----------------------------------+
|               ISHA                | |             VISHAKHA              |
|      Frontend + Main Dashboard    | |     GIS + Investigation + Reports |
| - React UI & Navigation           | | - Interactive Leaflet/OpenLayers  |
| - Live Grid & Alert Stream        | | - Vehicle Timeline & GIS Route    |
+-----------------------------------+ +-----------------------------------+
```

---

# 5. Government Feed Integration Specifications

## 5.1 Catalogue Ingestion Endpoint
The stream subsystem consumes government camera sources via the standardized endpoint `/api/ingest`:

```json
{
  "catalogue_version": "1.0",
  "cameras": [
    {
      "camera_id": "CAM-AHM-001",
      "department": "Traffic Police",
      "location": {"latitude": 23.0225, "longitude": 72.5714},
      "codec": "H.264",
      "rtsp_url": "rtsp://gateway.sentinel.gujarat.gov.in:554/stream1",
      "webrtc_url": "https://gateway.sentinel.gujarat.gov.in/webrtc/cam-001",
      "hls_url": "https://gateway.sentinel.gujarat.gov.in/hls/cam-001.m3u8"
    }
  ]
}
```

## 5.2 Stream Protocols & Rules
1. **RTSP over TCP**: Forced for all AI processing to eliminate packet loss and UDP frame tearing.
2. **PTS (Presentation Time Stamp) Synchronization**: Frame synchronization relies strictly on PTS timing instead of declared stream FPS.
3. **Resilience & Non-Fatal Errors**: Decoder join warnings and missing initial keyframes are caught gracefully without crashing the processing loop.
4. **Exponential Backoff Reconnection Engine**:
   $$\text{Backoff Interval} = \min(2^n, 30) \text{ seconds}$$
   Sequence: `2s -> 4s -> 8s -> 16s -> 30s (Max)`

---

# 6. Hero Demonstration Workflow

The primary hackathon demonstration follows an end-to-end vehicle tracking flow:

```text
Operator Enters Target Plate: "GJ01AB1234"
                    │
                    ▼
Search Event Index Across All Integrated Cameras
                    │
                    ▼
Generate Chronological Movement Profile:
  • 10:02:14 AM ➔ CAM-007 (SG Highway)
  • 10:09:31 AM ➔ CAM-013 (Iscon Cross Road)
  • 10:18:07 AM ➔ CAM-021 (Pakwan Flyover)
  • 10:31:22 AM ➔ CAM-034 (Gandhinagar Entry)
                    │
                    ▼
Render Interactive GIS Route & Vector Trajectory
                    │
                    ▼
Display High-Resolution Snapshot Evidence & Plate Crops
                    │
                    ▼
Watchlist Cross-Reference Match ➔ CRITICAL ALERT DISPATCH
```

---

# 7. Enterprise Scalability (50 to 80,000 Cameras)

```text
+-----------------------+     +-----------------------+     +-----------------------+
|    PoC Phase (~50)    | ──> |  Regional Pilot (1k)  | ──> | Statewide Scale (80k) |
| - Monolithic Compose  |     | - Kubernetes Clusters |     | - Edge AI Gateways    |
| - Single PostgreSQL   |     | - Kafka Event Bus     |     | - Distributed Pools   |
| - Local MinIO Storage |     | - GPU Worker Pools    |     | - Hot/Warm Storage    |
+-----------------------+     +-----------------------+     +-----------------------+
```

### Key Scaling Pillars:
1. **Edge Processing**: Regional gateways run lightweight YOLO detection; frame metadata and plate crops are sent to the central cloud.
2. **Event-Driven Architecture**: High-volume detections publish to a Kafka message broker, decoupling video ingestion from analytical database writing.
3. **Tiered Evidence Storage**:
   - **Hot Storage (0–7 Days)**: Fast SSD NVMe for instant snapshot retrieval.
   - **Warm Storage (7–30 Days)**: MinIO / Cloud Object Storage.
   - **Cold Storage (30+ Days)**: Compressed archive / Glacier storage.

---

# 8. Security Architecture

```text
User ──(HTTPS)──> API Gateway ──(JWT Auth)──> RBAC Authorization ──> Internal Microservices ──> PostgreSQL
```

- **Transport Security**: TLS 1.3 encryption across all public REST and WebRTC/RTSP channels.
- **Authentication**: OAuth2 JWT Bearer tokens with 15-minute expiration and secure refresh cycles.
- **Role-Based Access Control (RBAC)**:
  - `Admin`: System configuration, camera onboarding, user management.
  - `Investigator`: Vehicle search, history reconstruction, report export.
  - `Operator`: Live view monitoring, alert acknowledgment.
- **Audit Logging**: Immutable logging of all vehicle searches, watchlist additions, and evidence downloads.

---

# 9. Government Database Integration Readiness

To ensure compliance with Gujarat Police infrastructure, SENTINEL implements an **Adapter Architecture** for seamless integration with national/state databases:

```text
                             SENTINEL PLATFORM
                                     |
               +---------------------+---------------------+
               |                     |                     |
               v                     v                     v
         VAHAN ADAPTER       eGujCop ADAPTER        SARTHI ADAPTER
        (Vehicle Owner)      (Criminal Records)    (Driver Licenses)
```

In the PoC environment, adapter interfaces query internal representative database tables, seamlessly swappable for production REST/SOAP government endpoints.
