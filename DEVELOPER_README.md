# DEVELOPER EXECUTION GUIDE — RISHIT

---

### 1. Developer Details
- **Developer Name**: Rishit
- **Role**: CCTV Stream Ingestion & RTSP Processing Lead
- **Git Branch**: `feature/rishit-stream`

---

### 2. Project Objective
Build the resilient stream ingestion manager for the **SENTINEL** platform. Consume government camera inventory payloads from `/api/ingest`, launch multi-threaded OpenCV video capture worker pools, force RTSP over TCP transport, sequence video frames using frame Presentation Time Stamps (PTS), handle stream drops using an exponential backoff reconnection loop (`2s -> 4s -> 8s -> 16s -> 30s max`), and expose stream health telemetry APIs.

---

### 3. Exact Responsibility
You own the stream ingestion module (`ingestion/`). You are responsible for camera catalogue ingestion, OpenCV/FFmpeg stream capture worker pools, RTSP over TCP enforcement, PTS timestamp calculation, network disconnection backoff management, resource cleanup, and stream health telemetry generation.

---

### 4. Exact Features to Build
1. **`/api/ingest` Catalogue Parser**: Parse and validate government camera inventory JSON payloads (containing camera IDs, RTSP, WebRTC, and HLS stream URLs).
2. **Multi-Threaded RTSP Stream Worker Pool**: Worker thread manager opening and decoding video feeds via OpenCV `cv2.VideoCapture`.
3. **RTSP over TCP Enforcer**: Force TCP transport via FFmpeg capture environment options (`rtsp_transport;tcp`) to prevent UDP packet loss and visual artifacts.
4. **PTS Timestamping Engine**: Extract frame Presentation Time Stamps (`CAP_PROP_POS_MSEC`) for accurate frame sequencing (never rely on declared FPS or wall-clock time).
5. **Exponential Backoff Reconnection Engine**: Automatic retry loop (`2s -> 4s -> 8s -> 16s -> 30s max`) managing stream disconnects without thread/process crashes.
6. **Codec Support**: Support decoding both H.264 and H.265 (HEVC) video codec streams.
7. **Stream Telemetry & Health API (`GET /api/v1/streams/health`)**: Expose real-time FPS, PTS jitter, frame drop count, and stream status (`ONLINE`, `RECONNECTING`, `OFFLINE`).

---

### 5. What NOT to Build
- Do NOT download or store raw government video footage files to local disk.
- Do NOT publish modified video streams back to government gateways.
- Do NOT calculate frame timing using fixed FPS assumptions or wall-clock system time (`time.time()`). Use PTS timestamps.
- Do NOT build AI vehicle detection or OCR models (owned by Kavya).
- Do NOT build PostgreSQL database schemas or REST servers (owned by Vanshal).

---

### 6. Technologies
- **Python**: 3.10+
- **Video Capture Engine**: OpenCV (`cv2` with FFmpeg backend), PyAV / `ffmpeg-python`
- **Protocols & Codecs**: RTSP over TCP, WebRTC, HLS, H.264, H.265 (HEVC)

---

### 7. Recommended Models / Libraries
- `opencv-python`
- `ffmpeg-python` / `av`
- `requests`

---

### 8. Input
- Government camera catalogue JSON payload posted to `/api/ingest`.
- Live network RTSP / WebRTC video stream URLs.

---

### 9. Processing Pipeline
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

### 10. Output
- Decoded OpenCV video frame arrays (`numpy.ndarray`) paired with `camera_id` and `pts` timestamps pushed to Kavya's AI queue.
- Stream telemetry health JSON payloads (`GET /api/v1/streams/health`).

---

### 11. Required API Contract
Must strictly comply with `testing` integration contracts documented in `docs/API_CONTRACTS.md`:
- **Camera Telemetry & Health Schema**: `docs/API_CONTRACTS.md#5-camera-telemetry--health-schema`

---

### 12. Database Interaction
No direct database interaction. Streams status telemetry to Vanshal's FastAPI backend endpoints.

---

### 13. Integration Dependencies
- **Upstream Providers**:
  - Government Camera Catalogue (`/api/ingest`).
- **Downstream Consumers**:
  - **Kavya (`feature/kavya-ai-anpr`)**: Receives decoded video frame arrays and PTS timestamps.
  - **Vanshal (`feature/vanshal-backend`)**: Receives stream health status updates (`ONLINE`, `RECONNECTING`, `OFFLINE`).
  - **Isha (`feature/isha-frontend`)**: Uses WebRTC / HLS preview links for live camera grid views.

---

### 14. Exact Implementation Steps
1. Create `ingestion/` folder structure (`catalogue_ingest.py`, `stream_manager.py`, `reconnect.py`, `stream_health.py`).
2. Build `catalogue_ingest.py` parsing `/api/ingest` camera inventory JSON.
3. Build `stream_manager.py` setting `os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"` and launching `cv2.VideoCapture` worker threads.
4. Build `reconnect.py` implementing exponential backoff loop (`[2, 4, 8, 16, 30]` seconds max).
5. Build `stream_health.py` tracking active threads, frame drop counts, and FPS metrics.

---

### 15. Error Handling
- **Stream Disconnect**: Catch OpenCV frame read failures (`ret == False`), set status `RECONNECTING`, and initiate exponential backoff loop.
- **Corrupt Frame GOP**: Skip invalid video frames without crashing stream worker thread.
- **Memory Leak Prevention**: Explicitly invoke `cap.release()` on thread shutdown.

---

### 16. Testing Requirements
- Test RTSP capture against a local test video server (e.g. MediaMTX / `rtsp-simple-server`).
- Simulate network disconnect (kill RTSP server) and verify exponential backoff retry timestamps (`2s -> 4s -> 8s -> 16s -> 30s`).
- Test decoding H.264 vs H.265 video streams. 

---

### 17. Performance Requirements
- Frame decoding latency $< 10$ ms per frame.
- Reconnection detection latency $< 500$ ms following stream socket drop.
- Worker memory footprint $< 150$ MB per active camera stream thread.

---

### 18. Day 1 Tasks
Setup Python environment, build `catalogue_ingest.py` to parse test camera catalogue JSON, launch basic OpenCV video capture thread.

---

### 19. Day 2 Tasks
Configure RTSP over TCP transport options, build PTS timestamping extractor, implement multi-stream worker pool manager.

---

### 20. Day 3 Tasks
Build `reconnect.py` exponential backoff retry loop, test stream drop recovery using local RTSP server.

---

### 21. Day 4 Tasks
Build `stream_health.py` telemetry collector, connect frame queue output to Kavya's AI pipeline, run 50-stream load stress test.

---

### 22. Definition of Done (DoD)
- [ ] `/api/ingest` parses camera catalogue payload and initializes stream worker threads.
- [ ] Ingestion forces RTSP over TCP, eliminating UDP packet loss and visual artifacts.
- [ ] Stream disconnect automatically triggers exponential backoff sequence (`2s -> 4s -> 8s -> 16s -> 30s`).
- [ ] Telemetry API (`/api/v1/streams/health`) accurately reflects real-time stream status.
- [ ] Code committed to `feature/rishit-stream` and Pull Request opened to `testing`.

---

### 23. Git Workflow
```bash
# 1. Work exclusively on your feature branch
git checkout feature/rishit-stream

# 2. Add implementation files as you build
git add ingestion/

# 3. Commit changes
git commit -m "feat(ingestion): build RTSP/TCP worker pool and exponential backoff engine"

# 4. Push to GitHub
git push origin feature/rishit-stream

# 5. Open Pull Request on GitHub:
# feature/rishit-stream  ──►  testing (Central Integration Branch)
# NEVER push directly to main!
```

---

### 24. What Must Be Demonstrated Before PR
1. Ingestion worker reading RTSP over TCP feed with PTS timestamps.
2. Stream drop recovery demonstrating exponential backoff sequence (`2s -> 4s -> 8s -> 16s -> 30s`).
3. Stream health telemetry JSON returning status `ONLINE` for 4 active test feeds.

---

### 25. Shared Technical Reference
For central system specifications, hybrid architecture decisions, and database schemas, refer to the integration blueprints on `testing`:
- `docs/ARCHITECTURE.md`
- `docs/API_CONTRACTS.md`
- `docs/TESTING.md`

---

### 26. Final Workspace Rule
This branch starts with **ONLY** `DEVELOPER_README.md`. As developer Rishit, you will create the `ingestion/` directory and implementation files as you code. Do NOT commit unnecessary root scaffold files.


