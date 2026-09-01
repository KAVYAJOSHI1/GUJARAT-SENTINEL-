# Implementation Specification — RISHIT (CCTV Ingestion & Stream Processing)

---

### 1. Ownership
- **Developer Name**: Rishit
- **Module Ownership**: CCTV Stream Ingestion Manager, `/api/ingest` Catalogue Parser, RTSP/TCP & Reconnection Engine
- **Git Branch**: `feature/rishit-stream`

---

### 2. Objective
Architect and build the stream ingestion service that consumes government CCTV feeds, parses stream catalogues from `/api/ingest`, forces RTSP over TCP transport, extracts frames using Presentation Time Stamps (PTS), executes automatic exponential backoff reconnection loops on network drops, and monitors stream health telemetry.

---

### 3. Responsibilities
- Implement the `/api/ingest` camera catalogue onboarding endpoint parser.
- Manage multi-stream RTSP video capture using OpenCV / FFmpeg worker threads.
- Enforce mandatory government feed rules: **RTSP over TCP**, **PTS timestamping**, non-fatal decoder join error handling.
- Build the **Automatic Exponential Backoff Reconnection Engine** (`2s -> 4s -> 8s -> 16s -> 30s max`).
- Expose real-time stream health telemetry API (`GET /api/v1/streams/health`).

---

### 4. Features to Implement
1. **Catalogue Ingest Handler (`/api/ingest`)**: Accept camera inventory JSON payloads containing RTSP, WebRTC, and HLS stream links.
2. **RTSP Stream Worker Pool**: Multi-threaded capture workers opening feeds using OpenCV `cv2.VideoCapture`.
3. **PTS Frame Extractor**: Retrieve frame presentation timestamps to drive frame sequencing (ignoring `CAP_PROP_FPS`).
4. **Exponential Backoff Reconnector**: Retry loop managing broken sockets without thread death.
5. **Stream Health Monitor**: Measure current FPS, PTS jitter, frame loss rate, and connection status per stream.

---

### 5. Module Architecture
```text
/api/ingest Catalogue Payload
 │
 ▼
Catalogue Parser (catalogue_ingest.py)
 │
 ▼
Stream Manager Worker Pool (stream_manager.py)
 │
 ├── Worker Thread 1 (CAM-001) ──(RTSP over TCP)──► Frame Queue + PTS Timestamp ──► Kavya's AI Engine
 ├── Worker Thread 2 (CAM-002) ──(RTSP over TCP)──► Frame Queue + PTS Timestamp ──► Kavya's AI Engine
 └── Worker Thread 3 (CAM-003) ──► Connection Drop Detected
                                            │
                                            ▼
                                Exponential Backoff Engine (reconnect.py)
                                (2s ➔ 4s ➔ 8s ➔ 16s ➔ 30s Max)
```

---

### 6. Technologies
- **Python**: 3.10+
- **Video Tools**: OpenCV (`cv2`), FFmpeg (`ffmpeg-python` / PyAV)
- **Protocols**: RTSP over TCP, WebRTC, HLS, H.264, H.265

---

### 7. Folder Structure
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

### 8. Detailed Implementation Tasks
1. Set OpenCV environment variable for TCP transport: `os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"`.
2. Implement `catalogue_ingest.py` parsing `/api/ingest` payload into stream worker configs.
3. Implement `stream_manager.py` launching background worker threads for each active camera.
4. In worker thread, open capture: `cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)`.
5. Retrieve PTS timestamp: `pts = cap.get(cv2.CAP_PROP_POS_MSEC)`.
6. Implement `reconnect.py` exponential backoff loop:
```python
import time

def reconnect_stream(camera_id, rtsp_url):
    backoff_intervals = [2, 4, 8, 16, 30]
    for attempt, delay in enumerate(backoff_intervals):
        time.sleep(delay)
        cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        if cap.isOpened():
            return cap
    # Keep retrying at max 30 seconds
    while True:
        time.sleep(30)
        cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        if cap.isOpened():
            return cap
```
7. Ignore decoder warnings during stream join; wait for initial keyframe without crashing worker.
8. Expose stream telemetry via `/api/v1/streams/health`.

---

### 9. Input
- Government camera catalogue JSON payload from `/api/ingest`.
- Live network RTSP video streams.

---

### 10. Output
- Decoded image frames (`numpy.ndarray`) with `camera_id` and `pts` timestamp pushed to AI processing queue.
- Stream health telemetry status objects.

---

### 11. APIs Produced / Exposed
- `POST /api/ingest`: Onboard government camera catalogue.
- `GET /api/v1/streams/health`: Stream telemetry statistics (Online, Reconnecting, FPS, Dropped Frames).

---

### 12. Database Interaction
Pushes stream health status updates (`ONLINE`, `RECONNECTING`, `OFFLINE`) to Vanshal's `cameras` table in PostgreSQL.

---

### 13. Dependencies on Other Members
- **Kavya**: Passes decoded video frames and PTS timestamps to Kavya's AI detection pipeline.
- **Vanshal**: Pushes camera health telemetry status to Vanshal's database.
- **Isha**: Provides WebRTC/HLS preview URLs for Isha's dashboard frontend grid.

---

### 14. Integration Contract
Must adhere to government feed rules specified in `docs/ARCHITECTURE.md` Section 5.

---

### 15. Error Handling & Edge Cases
- **Stream Network Disconnect**: Caught gracefully by `cap.read()` returning `False`; triggers exponential backoff without crashing process.
- **Scene Discontinuities / Hard Cuts**: Reset local frame counters and notify downstream tracking modules.
- **H.265 Codec Support**: Ensure FFmpeg build includes H.265/HEVC hardware decoding capabilities.

---

### 16. Testing Requirements
- Test stream capture against test RTSP server (`rtsp-simple-server` / MediaMTX).
- Simulate network disconnect (kill RTSP server) and verify exponential backoff sequence (`2s -> 4s -> 8s -> 16s -> 30s`).

---

### 17. Performance Requirements
- Frame decoding latency $< 10$ ms per frame.
- Reconnection detection latency $< 2.0$ seconds after stream drop.

---

### 18. Day 1 Plan
Build `/api/ingest` catalogue parser and RTSP over TCP stream capture script.

---

### 19. Day 2 Plan
Implement multi-stream worker pool and PTS timestamp extraction logic.

---

### 20. Day 3 Plan
Build exponential backoff reconnection engine and stream health monitoring collector.

---

### 21. Day 4 Plan
Perform multi-stream stress testing (simultaneous 10+ RTSP feeds) and verify integration against `testing`.

---

### 22. Definition of Done (DoD)
- [ ] `/api/ingest` endpoint parses government camera catalogue payload and launches stream workers.
- [ ] Ingestion forces RTSP over TCP without visual artifacts or UDP packet drops.
- [ ] Stream disconnect automatically triggers exponential backoff sequence (`2s -> 4s -> 8s -> 16s -> 30s`).
- [ ] Stream telemetry API (`/api/v1/streams/health`) accurately reflects real-time stream status.
- [ ] Code committed to `feature/rishit-stream` and verified on `testing`.

---

### 23. Deliverables
- Complete `ingestion/` stream manager source codebase.
- Reconnection engine and stream health telemetry services.

---

### 24. What NOT to do
- Do NOT use wall-clock arrival time or `CAP_PROP_FPS` for frame sequencing; use PTS timestamps.
- Do NOT assume video streams can be downloaded via `curl`/`wget`; consume streams live only.
- Do NOT push streams back to government gateways.
- Do NOT push directly to `main`.

---

### 25. Merge Checklist
- [ ] RTSP over TCP transport verified
- [ ] Exponential backoff reconnection tested under simulated stream drop
- [ ] PR opened from `feature/rishit-stream` to `testing`
