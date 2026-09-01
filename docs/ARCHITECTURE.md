# SENTINEL — Master System Architecture & Technical Blueprint

## Gujarat Police Innovation Hackathon 2026
**Platform**: Sentinel CCTV Integration & Video Analytics Platform  
**System Type**: Hybrid Multi-Departmental CCTV Intelligence Engine  
**Target Scale**: Proof-of-Concept (~50 Cameras) ➔ Statewide Deployment (~80,000 Cameras)

---

# 1. Problem Statement

Modern law enforcement and urban traffic management across Gujarat face severe operational hurdles due to fragmented video surveillance infrastructure:

- **Fragmented Departmental Silos**: Separate camera deployments operated by Traffic Police, City Police, Municipal Corporations, Smart City authorities, Highways, and Ports without unified visibility.
- **Heterogeneous Vendors & Hardware**: Mixed camera vendors (Hikvision, Dahua, Axis, Hanwha, CP Plus) with disparate native Video Management Systems (VMS) like Milestone and Genetec.
- **Codec & Protocol Disparities**: Ingestion across H.264, H.265, MJPEG, RTSP, WebRTC, WHEP, and HLS protocols.
- **Storage Isolation**: Local NVR/DVR storage without central indexing, forcing manual physical video retrieval during criminal investigations.
- **Lack of Real-Time Vehicle Intelligence**: Inability to track suspect vehicles chronologically across multiple camera views or cross-reference detections against law enforcement watchlists in real-time.
- **Scalability Barriers**: Legacy architectures fail when scaling from local city intersections to a statewide grid of ~80,000 cameras.

---

# 2. Reference Model Strategy (Hybrid Architecture)

To resolve these challenges, SENTINEL combines the core strengths of **Reference Models 1 through 5** into a single, cohesive **Hybrid Architecture**:

```text
                     REFERENCE MODELS INTEGRATION MATRIX
                     
┌──────────────────────────┐    ┌──────────────────────────┐    ┌──────────────────────────┐
│   Model 1: Registry      │    │  Model 2: Unified View   │    │ Model 3: VMS Federation  │
│  - PostGIS Spatial Reg.  │ ──>│  - Operator Command Hub  │ ──>│  - Protocol Abstraction  │
│  - Department Metadata   │    │  - Real-Time AI Overlay  │    │  - RTSP/WebRTC/HLS Norm. │
└──────────────────────────┘    └──────────────────────────┘    └──────────────────────────┘
             │                                                               │
             ▼                                                               v
┌──────────────────────────┐                                    ┌──────────────────────────┐
│ Model 4: Central AI Engine│ <───────────────────────────────── │   Model 5: Hybrid Scale  │
│  - Watchlist Matching    │                                    │  - Edge/Regional Nodes   │
│  - Vehicle Route Engine  │                                    │  - Kafka Event Pipeline  │
└──────────────────────────┘                                    └──────────────────────────┘
```

### Why the Hybrid Model is Superior
1. **Model 1 (Registry + GIS)** provides spatial metadata and physical camera inventory.
2. **Model 2 (Unified Viewing)** provides the real-time command dashboard interface.
3. **Model 3 (VMS Federation)** ensures vendor neutrality by wrapping heterogeneous cameras behind standardized ingestion interfaces (`/api/ingest`).
4. **Model 4 (Central AI)** executes centralized ANPR consensus, cross-camera correlation, and watchlist matching.
5. **Model 5 (Edge + Regional Architecture)** provides the roadmap to process streams near the edge, optimizing WAN bandwidth for statewide ~80,000 camera expansion.

---

# 3. Complete System Architecture

```text
                                GOVERNANCE & CCTV GRID
                                (Government Camera Feeds)
                                           │
                                           ▼
                                   CAMERA CATALOGUE
                                           │
                                           ▼
                                    /api/ingest
                                           │
                                           ▼
                                    CAMERA REGISTRY
                                    (PostGIS Metadata)
                                           │
                                           ▼
                                    STREAM MANAGER
                                    (RTSP over TCP)
                                           │
                                           ▼
                                  VIDEO DECODER LAYER
                                    (FFmpeg/OpenCV)
                                           │
                                           ▼
                                  AI ANALYTICS PIPELINE
                                           │
               ┌───────────────────────────┼───────────────────────────┐
               ▼                           ▼                           ▼
       VEHICLE DETECTION            PERSON DETECTION            OTHER ANALYTICS
       (YOLOv8 Classifiers)            (Pedestrian)              (Crowd/Motion)
               │
               ▼
        VEHICLE TRACKING
        (ByteTrack Multi-Object)
               │
               ▼
        PLATE DETECTION
        (ANPR Region Proposal)
               │
               ▼
             OCR
        (PaddleOCR Engine)
               │
               ▼
      VEHICLE REGISTRATION
        (Multi-Frame Consensus)
               │
               ▼
          EVENT ENGINE
               │
      ┌────────┴────────┬───────────────────────┐
      ▼                 ▼                       ▼
 PostgreSQL         Watchlist               Evidence
 + PostGIS           Engine                 Storage
  Storage       (Critical Matches)         (MinIO/S3)
      │                 │                       │
      │                 ▼                       ▼
      │               ALERT                  Metadata
      │                 │                       │
      └────────┬────────┘                       │
               │                                │
               ▼                                │
     CROSS-CAMERA CORRELATION  <────────────────┘
               │
      ┌────────┴────────┐
      ▼                 ▼
     GIS          INVESTIGATION
   MAPPING           CONSOLE
      │                 │
      └────────┬────────┘
               │
               ▼
         WEB DASHBOARD
      (React Command Center)
```

---

# 4. End-to-End Data Flow

```text
Camera ──> Stream ──> Frame ──> Detection ──> Tracking ──> ANPR ──> OCR ──> Event ──> Database ──> Watchlist ──> Alert ──> GIS ──> Investigation
```

1. **Camera**: Physical hardware mounted at a road junction or facility.
2. **Stream**: Live video transmission exposed via RTSP, WebRTC, or HLS.
3. **Frame**: Decoded image array tagged with a Presentation Time Stamp (PTS).
4. **Detection**: Bounding box proposals for vehicles (`car`, `truck`, `bus`, `motorcycle`).
5. **Tracking**: Local persistent track ID (`Track #42`) assigned by ByteTrack across sequential frames.
6. **ANPR**: License plate region proposal cropped from the vehicle bounding box.
7. **OCR**: Optical character recognition extracting raw text characters.
8. **Event**: Multi-frame consensus normalized plate payload emitted to the backend.
9. **Database**: Spatial-temporal indexing in PostgreSQL + PostGIS.
10. **Watchlist**: Real-time cross-referencing against blacklisted registration numbers.
11. **Alert**: Sub-second alert dispatch pushed over WebSockets to operator screens.
12. **GIS**: Plotting detection pins and animated route polylines on Leaflet maps.
13. **Investigation**: Chronological journey reconstruction, evidence snapshot review, and PDF report export.

---

# 5. Government Feed Integration & Sandbox Rules

## 5.1 Sandbox Endpoint `/api/ingest`
Stream ingestion reads camera URLs dynamically from `/api/ingest`:

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

## 5.2 Stream Protocol Utilization
```text
RTSP (over TCP)  ──> Internal AI Analytics & Video Processing
WebRTC / WHEP    ──> Low-Latency Browser Live View Preview
HLS              ──> Fallback & Mobile Playback
```

## 5.3 Technical Ingestion Requirements
- **RTSP over TCP**: Forced via `-rtsp_transport tcp` to eliminate UDP packet loss and visual artifacting.
- **PTS Timestamping**: Frame rates are calculated from PTS timestamps; systems must **NEVER** rely on `CAP_PROP_FPS` or wall-clock arrival times.
- **Decoder Resilience**: Non-fatal decoder join warnings (e.g. missing initial I-frames) are handled without crashing the capture thread.
- **Exponential Backoff Reconnect**:
  $$\text{Interval} = \min(2^n, 30) \text{ seconds} \quad (n \in [1, 5] \implies 2\text{s}, 4\text{s}, 8\text{s}, 16\text{s}, 30\text{s})$$
- **Live Consumption Policy**: Feeds are consumed live-only; no local archiving of full video streams or attempt to publish streams back to government gateways.

---

# 6. AI Analytics Pipeline Architecture

```text
Frame ──> Vehicle Detector (YOLOv8) ──> ByteTrack Tracker ──> Plate Locator ──> Plate Crop ──> Preprocessing ──> PaddleOCR ──> Multi-Frame Voting ──> Event JSON
```

### 6.1 Mandatory PoC Pipeline
- **Vehicle Detection**: Pretrained YOLOv8 detector identifying `car`, `motorcycle`, `truck`, `bus`, `auto-rickshaw`.
- **Vehicle Tracking**: ByteTrack maintaining local track IDs (`Track #42`) within individual camera views.
- **Plate Detection**: Dedicated license plate detection region proposal model.
- **OCR Engine**: PaddleOCR extracting characters from preprocessed plate crops (grayscale, contrast stretching, deskewing).
- **Multi-Frame Consensus**: Voting algorithm across sequential frames of a track to eliminate single-frame OCR misreads.

### 6.2 Optional / Bonus Pipeline Features
- **Vehicle Re-ID**: Feature vector embedding (ResNet/OSNet) for appearance-based tracking when license plates are obscured.
- **Pedestrian & Crowd Analytics**: Pedestrian counting and intrusion detection overlays.

---

# 7. Database Architecture (PostgreSQL + PostGIS)

```sql
-- 1. Cameras Registry Table
CREATE TABLE cameras (
    camera_id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    department VARCHAR(64) NOT NULL,
    location GEOMETRY(Point, 4326) NOT NULL,
    rtsp_url TEXT NOT NULL,
    webrtc_url TEXT,
    hls_url TEXT,
    codec VARCHAR(16) NOT NULL DEFAULT 'H.264',
    status VARCHAR(32) NOT NULL DEFAULT 'ONLINE',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. Vehicle Events Table
CREATE TABLE vehicle_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camera_id VARCHAR(64) REFERENCES cameras(camera_id) ON DELETE CASCADE,
    track_id INT NOT NULL,
    plate_number VARCHAR(32) NOT NULL,
    raw_ocr_text VARCHAR(32),
    confidence FLOAT NOT NULL,
    vehicle_type VARCHAR(32) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    evidence_path TEXT NOT NULL,
    plate_crop_path TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. Watchlist Table
CREATE TABLE watchlist (
    watchlist_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plate_number VARCHAR(32) UNIQUE NOT NULL,
    category VARCHAR(64) NOT NULL,
    priority VARCHAR(16) NOT NULL CHECK (priority IN ('CRITICAL', 'HIGH', 'MEDIUM')),
    reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. Alerts Table
CREATE TABLE alerts (
    alert_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID REFERENCES vehicle_events(event_id) ON DELETE CASCADE,
    watchlist_id UUID REFERENCES watchlist(watchlist_id) ON DELETE CASCADE,
    priority VARCHAR(16) NOT NULL,
    acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_by VARCHAR(64),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for High-Performance Queries
CREATE INDEX idx_vehicle_events_plate ON vehicle_events(plate_number);
CREATE INDEX idx_vehicle_events_timestamp ON vehicle_events(timestamp DESC);
CREATE INDEX idx_vehicle_events_camera ON vehicle_events(camera_id);
CREATE INDEX idx_cameras_location ON cameras USING GIST (location);
```

### Production Partitioning Strategy
For statewide scaling, `vehicle_events` is range-partitioned monthly by `timestamp`:
```sql
CREATE TABLE vehicle_events_2026_09 PARTITION OF vehicle_events
    FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');
```

---

# 8. Tiered Evidence Storage Strategy

> [!IMPORTANT]
> **Rule**: Raw video clips and snapshot image files must **NEVER** be stored as binary BLOBs inside PostgreSQL.

```text
AI Event ──► PostgreSQL (Relational Metadata & File References)
         └──► MinIO / S3 Object Storage (Image Snapshots & Plate Crops)
```

### Storage Tiers & Retention Policies
1. **Hot Tier (0–7 Days)**: NVMe SSD storage for instant image snapshot and plate crop rendering.
2. **Warm Tier (7–30 Days)**: Standard MinIO / S3 Object Storage bucket for ongoing investigations.
3. **Cold Tier (30+ Days)**: Compressed Glacier object storage / archival storage for long-term legal evidence retention.

---

# 9. Watchlist & Alert Cooldown Engine

```text
Detected Plate: "GJ01AB1234"
         │
         ▼
Plate String Normalization (Upper, Strip Spaces/Hyphens)
         │
         ▼
Query Watchlist Index
         │
    ┌────┴────┐
    ▼         ▼
No Match    Match Detected
    │         │
    ▼         ▼
Normal     Check Cooldown Engine (Same Plate + Same Camera within 5 Mins?)
Event         │
         ┌────┴────┐
         ▼         ▼
        Yes       No
         │         │
         ▼         ▼
      Suppress  Create Alert Record + Dispatch WebSocket Payload
```

---

# 10. Cross-Camera Vehicle Intelligence

- **Primary Identity**: Normalized license plate registration string (`GJ01AB1234`).
- **Supporting Identity**: Vehicle visual feature embedding (Color, Make, Model, Re-ID embedding).

> [!WARNING]
> Camera-local ByteTrack Track IDs (e.g. `Track #42`) are transient to a single camera stream and must **NEVER** be used as global vehicle identities across cameras.

---

# 11. GIS Architecture

- **Engine**: Leaflet.js / OpenLayers on frontend; PostGIS spatial geometry on backend.
- **Layers**:
  1. Camera Registry Layer (Online green pins, offline red pins).
  2. Vehicle Sightings Layer (Chronological sequence numbers 1, 2, 3...).
  3. Route Trajectory Polyline (Animated direction arrows connecting sightings).
  4. Alert Overlay (Flashing red markers for critical watchlist matches).

---

# 12. Security Architecture

```text
User ──(HTTPS/TLS 1.3)──> API Gateway ──(JWT Bearer)──> RBAC Enforcer ──> Microservices ──> PostgreSQL
```

- **Transport**: TLS 1.3 encryption across REST APIs and WebSockets.
- **Authentication**: JWT tokens (15-min expiry) with refresh token rotation.
- **RBAC Roles**: `Admin` (System config), `Investigator` (Vehicle search & reports), `Operator` (Live view & alert acknowledgment).
- **Audit Trail**: Every vehicle query, watchlist edit, and evidence download is recorded in `audit_logs`.

---

# 13. Statewide Scalability (50 ➔ 80,000 Cameras)

```text
+-----------------------+     +-----------------------+     +-----------------------+
|    PoC Phase (~50)    | ──> |  Regional Pilot (1k)  | ──> | Statewide Scale (80k) |
| - Monolithic Compose  |     | - Kubernetes Clusters |     | - Edge AI Gateways    |
| - Single PostgreSQL   |     | - Kafka Event Bus     |     | - Distributed Pools   |
| - Local MinIO Storage |     | - GPU Worker Pools    |     | - Hot/Warm Storage    |
+-----------------------+     +-----------------------+     +-----------------------+
```

### Statewide Production Architecture Diagram
```text
CCTV Cameras (80k) ──► Edge AI Gateways ──► Regional Kafka Bus ──► Central GPU Worker Pools ──► PostGIS Cluster
```

---

# 14. Infrastructure Capacity Planning

Hardware sizing depends strictly on benchmark metrics:
- Resolution (1080p vs 4K)
- Bitrate (2 Mbps vs 8 Mbps)
- Ingestion FPS (15 FPS vs 30 FPS)
- AI Processing Skip Rate (Process every 3rd frame)
- Model Type (YOLOv8n vs YOLOv8m)
- GPU Type (NVIDIA T4 vs A100 / Jetson Orin)

---

# 15. Failure Recovery Matrix

| Failure Mode | Detection Signal | Automated Recovery Strategy |
| :--- | :--- | :--- |
| **Camera Disconnect** | RTSP read timeout | Exponential backoff reconnect (`2s -> 4s -> 8s -> 16s -> 30s`) |
| **Decoder Crash** | FFmpeg exit code $\neq 0$ | Respawn worker thread, skip corrupted frame, resume PTS |
| **OCR Failure / Blur** | Confidence $< 0.50$ | Discard low-confidence OCR, rely on multi-frame consensus |
| **Database Disconnect** | DB connection pool error | Cache events in local Redis / memory buffer, flush on reconnect |
| **MinIO Storage Down** | HTTP 500 on snapshot save | Store snapshot to local scratch disk fallback |
