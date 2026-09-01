# Team Specification — RISHIT

## 1. Developer Profile & Module Ownership
- **Member Name**: Rishit
- **Module Ownership**: CCTV Stream Ingestion + RTSP / Stream Processing Manager
- **Git Branch**: `feature/rishit-stream`

---

## 2. Core Responsibilities
- Implement the stream ingestion service and the `/api/ingest` camera catalogue endpoint.
- Consume live government CCTV streams using **RTSP over TCP**.
- Manage multi-camera stream processing using FFmpeg, OpenCV, or GStreamer.
- Implement robust frame extraction with **PTS timestamps** (ignoring raw stream FPS declarations).
- Implement an **Automatic Exponential Backoff Reconnection Engine** to maintain resilient connections to network streams.
- Monitor stream health telemetry (Online/Offline, FPS, Bitrate, Frame Loss Rate).

---

## 3. Mandatory Government-Feed Ingestion Rules

1. **RTSP over TCP**: Force TCP transport (`-rtsp_transport tcp` in FFmpeg / OpenCV) to prevent UDP frame corruption.
2. **PTS Synchronization**: Drive frame rate by PTS timestamps, handling inter-frame gaps gracefully.
3. **Stream Discontinuities**: Catch and ignore non-fatal H.264/H.265 decoder warnings during initial stream joins.
4. **Catalogue Ingest**: Dynamically fetch stream URLs from `/api/ingest` rather than hardcoding static RTSP strings.
5. **No Direct Gateway Publishing**: Do NOT attempt to push processed streams back into the government gateway.
6. **Exponential Backoff Reconnection Strategy**:
```text
Stream Failure Detected
       │
       ├─► Wait 2 seconds  ──► Reconnect Attempt 1
       ├─► Wait 4 seconds  ──► Reconnect Attempt 2
       ├─► Wait 8 seconds  ──► Reconnect Attempt 3
       ├─► Wait 16 seconds ──► Reconnect Attempt 4
       └─► Wait 30 seconds max ──► Continuous Retry Loop
```

---

## 4. Technology Stack
- **Languages/Tools**: Python 3.10+, FFmpeg, OpenCV (`cv2.VideoCapture`), GStreamer
- **Protocols**: RTSP, TCP, WebRTC/WHEP, HLS

---

## 5. Interface & Data Contracts

### 5.1 APIs Produced
- **POST `/api/ingest`**: Dynamic camera catalogue onboarding endpoint.
- **GET `/api/v1/streams/health`**: Real-time stream telemetry and uptime statistics.

### 5.2 Internal Stream Output
- Decoded video frames with associated `camera_id` and `pts` timestamp pushed to Kavya's AI detection queue.

---

## 6. Expected Directory Layout (`ingestion/`)
```text
ingestion/
├── catalogue_ingest.py # /api/ingest route handler
├── stream_manager.py   # Multi-stream RTSP worker pool
├── reconnect.py        # Exponential backoff loop
├── stream_health.py    # Health telemetry collector
├── ffmpeg_utils.py     # FFmpeg/OpenCV capture wrappers
└── README.md
```

---

## 7. Development Priorities
1. **Day 1**: Build `/api/ingest` catalogue parsing service.
2. **Day 2**: Implement RTSP over TCP stream capture with OpenCV/FFmpeg.
3. **Day 3**: Add exponential backoff reconnection engine and stream health checks.
4. **Day 4**: Perform stress testing with simultaneous multi-camera video streams.

---

## 8. Definition of Done (DoD) & Testing Requirements
- [ ] `/api/ingest` endpoint accepts government camera catalogue payload and registers active streams.
- [ ] OpenCV/FFmpeg capture forces RTSP over TCP without frame tearing.
- [ ] Simulated stream disconnect automatically triggers exponential backoff reconnection (`2s -> 4s -> 8s -> 16s -> 30s`).
- [ ] Code committed to `feature/rishit-stream` and verified on `testing`.

---

## 9. Inter-Member Dependencies
- **Kavya**: Passes raw video frames to Kavya's AI detection pipeline.
- **Vanshal**: Pushes camera health telemetry status to Vanshal's database.
- **Isha**: Supplies HLS/WebRTC preview links to Isha's frontend grid.
