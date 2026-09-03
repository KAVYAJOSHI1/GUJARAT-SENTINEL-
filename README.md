# SENTINEL — CCTV Stream Ingestion & RTSP Processing Engine

> High-throughput, fault-tolerant RTSP/WebRTC stream ingestion and frame sequencing engine for the **GUJARAT SENTINEL** traffic monitoring and surveillance platform.

---

## 📌 Overview

The **SENTINEL Stream Ingestion Module** (`ingestion/`) is responsible for ingesting live government CCTV camera feeds, managing multi-threaded video decoding pipelines via OpenCV/FFmpeg, enforcing reliable RTSP-over-TCP transport, sequencing frames using hardware/stream Presentation Time Stamps (PTS), handling network disconnects with exponential backoff recovery, and exposing real-time stream health telemetry.

```text
               ┌────────────────────────────────────────────────────────┐
               │         Government Camera Catalogue (/api/ingest)      │
               └───────────────────────────┬────────────────────────────┘
                                           │
                                           ▼
                                 ┌───────────────────┐
                                 │  Catalogue Parser │
                                 │ & Schema Validator│
                                 └─────────┬─────────┘
                                           │
                                           ▼
                          ┌─────────────────────────────────┐
                          │   Multi-Threaded Stream Pool    │
                          │        (StreamManager)          │
                          └────────┬───────────────┬────────┘
                                   │               │
                    ┌──────────────▼────┐    ┌─────▼─────────────┐
                    │ Worker: CAM_001   │    │ Worker: CAM_002   │
                    │ (OpenCV / FFmpeg) │    │ (OpenCV / FFmpeg) │
                    └──────┬────────────┘    └─────┬─────────────┘
                           │                       │
                           ├── Frame Read OK       └── Frame Read Fail
                           │   (Extract PTS)           (Exponential Backoff:
                           │                            2s➔4s➔8s➔16s➔30s)
                           ▼                               │
              ┌──────────────────────────┐                 ▼
              │   Downstream AI Queue    │      ┌──────────────────────┐
              │ (Kavya: ANPR/OCR Engine) │      │ StreamHealthRegistry │
              └──────────────────────────┘      │ & Telemetry API      │
                                                │ (Vanshal / Isha UI)  │
                                                └──────────────────────┘
```

---

## 🚀 Core Features

1. **Multi-Schema Catalogue Ingestion (`catalogue_ingest.py`)**:
   - Parses both full GIS camera metadata envelopes (`{"status": "success", "data": [...]}`) and bare camera lists (`[{"id": "...", "name": "..."}]`).
   - Automatically validates RTSP protocol schemes, handles duplicate camera IDs, and skips malformed payloads defensively without crashing the pipeline.

2. **Multi-Threaded Stream Worker Pool (`stream_manager.py`)**:
   - Spawns isolated, lightweight daemon worker threads (`StreamWorker`) per camera stream.
   - Dynamically syncs active workers with catalogue updates (`sync_cameras`) without interrupting healthy connections.

3. **RTSP over TCP Enforcement**:
   - Globally forces `OPENCV_FFMPEG_CAPTURE_OPTIONS = "rtsp_transport;tcp"` to eliminate UDP packet drops, macroblocking, and visual tearing over public/mesh networks.

4. **Hardware PTS Timestamp Sequencing**:
   - Uses native stream Presentation Time Stamps via `CAP_PROP_POS_MSEC` for precise frame ordering and gap detection.
   - Packages decoded frames into `FrameEnvelope` objects with monotonic sequence IDs before dispatching to downstream AI queues.

5. **Exponential Backoff Reconnection Engine (`reconnect.py`)**:
   - Resilient retry supervisor with an automatic backoff ladder: `2.0s ➔ 4.0s ➔ 8.0s ➔ 16.0s ➔ 30.0s (cap)`.
   - Thread-safe, responsive cancellation with zero shutdown latency.

6. **Real-Time Health & Telemetry Registry (`stream_health.py`)**:
   - Calculates rolling-window measured FPS, PTS jitter standard deviation (`pstdev`), total frame drops, and reconnect attempts.
   - Exposes stream health over a local FastAPI endpoint (`GET /api/v1/streams/health`) and supports background HTTP push to central backend services.

---

## 📂 Project Structure

```text
GUJARAT-SENTINEL-/
├── DEVELOPER_README.md          # Developer role blueprint & execution requirements
├── README.md                    # Project documentation (this file)
└── ingestion/                   # Core Stream Ingestion Package
    ├── __init__.py              # Package initialization
    ├── config.py                # Centralized environment-driven configuration
    ├── models.py                # Dataclasses & Enums (CameraRecord, FrameEnvelope, StreamMetrics)
    ├── catalogue_ingest.py      # Inventory parser, validator & de-duplicator
    ├── stream_manager.py        # Worker pool manager & OpenCV frame reader
    ├── reconnect.py             # Exponential backoff reconnection supervisor
    └── stream_health.py         # Rolling telemetry registry & FastAPI health server
```

---

## ⚙️ Configuration

All pipeline settings can be configured via environment variables or initialized with sensible defaults:

| Variable | Default | Description |
| :--- | :---: | :--- |
| `SENTINEL_CATALOGUE_URL` | `http://localhost:9000/api/ingest` | URL for the central camera inventory endpoint. |
| `SENTINEL_CATALOGUE_POLL_INTERVAL` | `60.0` | Polling frequency (seconds) to check for added/removed cameras. |
| `SENTINEL_TELEMETRY_WINDOW` | `60` | Rolling frame window size for FPS and PTS jitter calculations. |
| `SENTINEL_OPEN_TIMEOUT` | `10.0` | Maximum timeout (seconds) when establishing initial stream sockets. |
| `SENTINEL_HEALTH_PUSH_URL` | `None` | (Optional) Remote webhook/backend URL to push health snapshots. |
| `SENTINEL_HEALTH_PUSH_INTERVAL` | `5.0` | Push interval (seconds) for health telemetry reporting. |

---

## 🛠️ Installation & Setup

### Prerequisites
- **Python 3.10+** (Tested on Python 3.11)
- **OpenCV with FFmpeg support** (`opencv-python` or `opencv-python-headless`)

### Install Dependencies
```bash
pip install opencv-python numpy requests fastapi uvicorn
```

---

## 💻 Usage Example

### 1. Ingest Catalogue & Start Stream Pool

```python
import queue
from ingestion.catalogue_ingest import parse_catalogue
from ingestion.models import FrameEnvelope
from ingestion.stream_manager import StreamManager
from ingestion.stream_health import HealthRegistry

# Initialize downstream AI queue and health telemetry registry
ai_frame_queue: queue.Queue[FrameEnvelope] = queue.Queue(maxsize=500)
health_registry = HealthRegistry(window_size=60)

# Create stream manager
manager = StreamManager(frame_queue=ai_frame_queue, health=health_registry)

# Sample camera inventory payload
raw_catalogue = [
    {
        "camera_id": "CAM_AHM_001",
        "name": "Ashram Road Junction",
        "stream_url": "rtsp://10.0.1.100:554/live/ch1",
        "stream_protocol": "RTSP/TCP",
        "location": {"latitude": 23.0225, "longitude": 72.5714}
    }
]

# Parse, validate, and synchronize streams
cameras = parse_catalogue(raw_catalogue)
manager.sync_cameras(cameras)
```

### 2. Consume Frames in AI Pipeline (Kavya's ANPR)

```python
while True:
    envelope: FrameEnvelope = ai_frame_queue.get()
    print(f"Processing frame from {envelope.camera_id} at PTS {envelope.pts_ms}ms (Seq: {envelope.seq_num})")
    # Feed envelope.frame (numpy.ndarray) to AI detection models
```

### 3. Mount Stream Health API

```python
from ingestion.stream_health import build_health_app

# Standalone FastAPI telemetry server
app = build_health_app(health_registry)
# Run via: uvicorn app:app --port 8000
```

---

## 📊 Stream Telemetry Schema (`GET /api/v1/streams/health`)

```json
{
  "streams": [
    {
      "camera_id": "CAM_AHM_001",
      "status": "ONLINE",
      "fps": 25.0,
      "pts_jitter_ms": 1.42,
      "frame_drop_count": 0,
      "reconnect_count": 0,
      "last_error": null,
      "updated_at": 1788371075.43
    }
  ]
}
```

---

## 🧪 Testing & Verification

Run the test suite to verify catalogue parsing, backoff ladder progression, PTS jitter calculation, frame queues, and dynamic worker synchronization:

```bash
python -m unittest discover -s tests
```

---

## 🔗 Integration Dependencies

- **Upstream**: Government Camera Inventory Registry (`/api/ingest`).
- **Downstream AI Consumer**: ANPR & Vehicle Detection Pipeline (Kavya — `feature/kavya-ai-anpr`).
- **Downstream Backend**: Central API Backend (Vanshal — `feature/vanshal-backend`).
- **Downstream Frontend**: Live Camera Grid & Telemetry UI (Isha — `feature/isha-frontend`).

---

## 📄 License & Ownership
- **Module Owner**: Rishit (CCTV Stream Ingestion & RTSP Processing Lead)
- **Branch**: `feature/rishit-stream`
