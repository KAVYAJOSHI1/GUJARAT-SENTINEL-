# DEVELOPER EXECUTION GUIDE — RISHIT

## 1. Developer Details
- **Developer Name**: Rishit
- **Role**: CCTV Stream Ingestion & RTSP Processing Lead
- **Git Branch**: `feature/rishit-stream`

---

## 2. Mission
Rishit is responsible for building the stream ingestion manager. The engine consumes government camera metadata from `/api/ingest`, launches OpenCV/FFmpeg capture worker threads, forces RTSP over TCP transport, extracts frame Presentation Time Stamps (PTS), executes an exponential backoff reconnection loop (`2s -> 4s -> 8s -> 16s -> 30s max`) on stream drops, and exposes stream telemetry health APIs.

---

## 3. Exact Features Owned
- **`/api/ingest` Catalogue Ingest Handler**: Parse camera inventory JSON payloads containing RTSP, WebRTC, and HLS stream URLs.
- **Multi-Threaded RTSP Stream Worker Pool**: Capture worker threads opening feeds using OpenCV `cv2.VideoCapture`.
- **RTSP over TCP Enforcer**: Force TCP transport via OpenCV FFmpeg options (`rtsp_transport;tcp`).
- **PTS Timestamping Engine**: Extract frame Presentation Time Stamps for frame sequencing (ignoring `CAP_PROP_FPS` or wall-clock arrival time).
- **Exponential Backoff Reconnection Engine**: Automatic retry loop (`2s -> 4s -> 8s -> 16s -> 30s max`) managing socket drops without process crashes.
- **Stream Telemetry & Health API (`GET /api/v1/streams/health`)**: Measure current FPS, PTS jitter, frame loss rate, and connection status (`ONLINE`, `RECONNECTING`, `OFFLINE`).

---

## 4. Files You Should Work On
```text
ingestion/
├── catalogue_ingest.py # /api/ingest route handler & JSON validator
├── stream_manager.py   # Multi-stream RTSP worker pool
├── reconnect.py        # Exponential backoff retry engine
├── stream_health.py    # Health telemetry collector
├── ffmpeg_utils.py     # OpenCV/FFmpeg capture options & environment setup
└── README.md
```

---

## 5. Technologies
- **Python**: 3.10+
- **Video Capture**: OpenCV (`cv2` with FFmpeg backend), PyAV / `ffmpeg-python`
- **Streaming Protocols**: RTSP over TCP, WebRTC, HLS, H.264, H.265

---

## 6. Input
- Government camera catalogue JSON payload from `/api/ingest`.
- Live network RTSP / WebRTC video stream URLs.

---

## 7. Processing Pipeline
```text
/api/ingest Catalogue Payload
       │
       ▼
Catalogue Parser ──► Validate RTSP URLs & Camera Identifiers
       │
       ▼
Stream Worker Pool ──► Force OpenCV OPENCV_FFMPEG_CAPTURE_OPTIONS = "rtsp_transport;tcp"
       │
       ▼
Read Video Frame ──► Retrieve PTS Timestamp (CAP_PROP_POS_MSEC)
       │
       ├── Frame Read Success ──► Push Frame Array + PTS to Kavya's AI Queue
       └── Frame Read Fail    ──► Trigger Exponential Backoff Reconnection Loop
                                   (2s ➔ 4s ➔ 8s ➔ 16s ➔ 30s Max)
```

---

## 8. Output
- Decoded OpenCV video frames (`numpy.ndarray`) with `camera_id` and `pts` timestamp pushed to AI processing queue.
- Stream telemetry health status JSON responses.

---

## 9. API Contract Reference
Stream health telemetry must strictly comply with **`docs/API_CONTRACTS.md`**:
- **Camera Telemetry & Health Schema**: `docs/API_CONTRACTS.md#5-camera-telemetry--health-schema`

---

## 10. Integration Dependencies
- **Upstream Providers**:
  - Government Camera Catalogue (`/api/ingest`).
- **Downstream Consumers**:
  - **Kavya (`feature/kavya-ai-anpr`)**: Receives decoded video frames and PTS timestamps.
  - **Vanshal (`feature/vanshal-backend`)**: Receives stream health status updates (`ONLINE`, `RECONNECTING`, `OFFLINE`).
  - **Isha (`feature/isha-frontend`)**: Uses WebRTC / HLS preview links for live camera grid views.

---

## 11. Testing Requirements
- Test RTSP capture against local test video server (e.g. MediaMTX / `rtsp-simple-server`).
- Simulate network disconnect (kill RTSP server) and verify exponential backoff sequence (`2s -> 4s -> 8s -> 16s -> 30s`).
- Test H.264 vs H.265 video stream codec switching.

---

## 12. Definition of Done (DoD)
- [ ] `/api/ingest` parses camera catalogue payload and initializes stream worker threads.
- [ ] Ingestion forces RTSP over TCP, eliminating UDP packet loss and visual artifacts.
- [ ] Stream disconnect automatically triggers exponential backoff sequence (`2s -> 4s -> 8s -> 16s -> 30s`).
- [ ] Telemetry API (`/api/v1/streams/health`) accurately reflects real-time stream status.
- [ ] Code committed to `feature/rishit-stream` and Pull Request opened to `testing`.

---

## 13. Git Branching Instructions
```bash
# 1. Work exclusively on your feature branch
git checkout feature/rishit-stream

# 2. Commit changes
git add .
git commit -m "feat(ingestion): build RTSP/TCP worker pool and exponential backoff engine"

# 3. Push to GitHub
git push origin feature/rishit-stream

# 4. Open Pull Request on GitHub:
# feature/rishit-stream  ──►  testing (Central Integration Branch)
# NEVER push directly to main!
```
