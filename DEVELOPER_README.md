# CENTRAL INTEGRATION DEVELOPER EXECUTION GUIDE — SENTINEL

---

### 1. Developer Details & Subsystem Ownership
- **Stream Ingestion Lead**: Rishit (`feature/rishit-stream`) — Stream worker pool, RTSP/TCP capture, backoff reconnects, health telemetry.
- **AI / ANPR Lead**: Kavya (`feature/kavya-ai-anpr`) — YOLOv8 vehicle detection, PaddleOCR text extraction, multi-frame consensus, snapshot evidence saving.
- **Central Integration Branch**: `testing`

---

### 2. Project Objective
Build and integrate the core stream ingestion engine and AI Computer Vision analytics pipeline for the **SENTINEL** platform. Parse government camera inventory payloads, launch multi-threaded OpenCV video capture worker pools, force RTSP over TCP transport, sequence video frames using frame Presentation Time Stamps (PTS), run YOLOv8 vehicle detection, locate license plate regions, preprocess crops, run PaddleOCR, apply multi-frame consensus voting across track frames to eliminate misreads, generate high-res evidence snapshots, and dispatch AI Event JSON payloads to backend ingestion APIs.

---

### 3. Subsystem Boundaries & Responsibilities

#### A. Stream Ingestion Module (`ingestion/`)
- Camera catalogue ingestion & validation (`catalogue_ingest.py`).
- OpenCV/FFmpeg stream capture worker pools (`stream_manager.py`).
- RTSP over TCP enforcement (`OPENCV_FFMPEG_CAPTURE_OPTIONS = "rtsp_transport;tcp"`).
- Monotonic PTS timestamp calculation (`CAP_PROP_POS_MSEC`).
- Exponential backoff reconnection loop (`reconnect.py`).
- Stream telemetry & health tracking (`stream_health.py`).

#### B. AI / ANPR Analytics Module (`ai/`)
- Model inference execution (`ai/detection/vehicle_detector.py`).
- License plate region localization & preprocessing (`ai/anpr/`).
- PaddleOCR text extraction & character normalization (`ai/ocr/`).
- Multi-frame frequency voting logic (`ai/anpr/consensus.py`).
- Evidence snapshot saving & AI detection event formatting (`ai/pipeline.py`).
- Adapter interface for `FrameEnvelope` -> `FrameInput` conversion (`ai/adapter/`).

---

### 4. Input & Integration Boundary Interface

The ingestion engine passes decoded video frame containers (`FrameEnvelope`) to the AI queue consumer, which converts them to `FrameInput` objects:

```python
from ai.adapter.frame_interface import FrameInput
from ai.pipeline import AIPipeline

pipeline = AIPipeline()

# Convert ingestion FrameEnvelope to AI FrameInput
frame_input = FrameInput(
    frame=envelope.frame,
    camera_id=envelope.camera_id,
    pts=envelope.pts_ms,
    metadata={"seq_num": envelope.seq_num, "received_at_s": envelope.received_at_s}
)

events = pipeline.process_frame(frame_input)
```

---

### 5. Integrated Processing Pipeline

```text
[ Live RTSP Grid / Catalogue ]
             │
             ▼
[ StreamWorker Pool (RTSP over TCP) ] ──► Extracts PTS_MS (CAP_PROP_POS_MSEC)
             │
             ├── Read Success ──► FrameEnvelope Queue ──► FrameInput Adapter
             └── Read Failure ──► ReconnectSupervisor (2s -> 4s -> 8s -> 16s -> 30s)
                                       │
                                       ▼
                     [ Kavya AIPipeline Execution ]
                                       │
            ┌──────────────────────────┼──────────────────────────┐
            ▼                          ▼                          ▼
     YOLOv8 Detection           Plate Localization          PaddleOCR Engine
    (car, truck, etc.)          (Cropper + CLAHE)         (Normalizer Regex)
            │                          │                          │
            └──────────────────────────┼──────────────────────────┘
                                       ▼
                            Multi-Frame Consensus
                                       │
                                       ▼
                       Save Evidence & Emit Event JSON
```

---

### 6. Technologies & Dependencies
- **Python**: 3.10+
- **Stream Ingestion**: OpenCV (`cv2`), `requests`, FFmpeg backend (`rtsp_transport;tcp`)
- **Object Detection**: Ultralytics YOLOv8 (`ultralytics`), PyTorch (`torch`)
- **OCR Engine**: PaddleOCR (`paddleocr`)
- **Image Processing**: OpenCV (`cv2`), Pillow (`PIL`), NumPy

---

### 7. Sentinel Gujarat Camera Grid Integration Procedure

#### A. Camera Catalogue & Registry
- Sentinel Live Catalogue: `https://cctv.corp8.cloud/cameras.json`
- GIS Enriched Registry: `data/camera_registry.json`

#### B. Direct RTSP Ingestion Stream Pattern
- RTSP Endpoint: `rtsp://103.250.160.189:8554/stream/<camera_id>`
- Example: `rtsp://103.250.160.189:8554/stream/cam04` (H.264), `cam06` (H.265 / HEVC)
- Transport Protocol: RTSP over TCP (`rtsp_transport;tcp`)

#### C. Running Live Smoke Test against Sentinel Feeds
```bash
.venv/bin/python scripts/rtsp_ai_demo.py \
  --source "rtsp://103.250.160.189:8554/stream/cam04" \
  --camera-id "cam04" \
  --max-frames 60 \
  --benchmark
```

---

### 8. Testing & Execution Commands

#### A. Run Automated Unit Test Suite
```bash
.venv/bin/python -m unittest discover tests
```

#### B. Stream Ingestion Telemetry Test
```bash
.venv/bin/python -c "
from ingestion.models import CameraRecord
from ingestion.stream_manager import StreamWorker
from ingestion.stream_health import HealthRegistry
import queue, time

cam = CameraRecord(camera_id='cam04', stream_url='rtsp://103.250.160.189:8554/stream/cam04')
q, h = queue.Queue(), HealthRegistry()
w = StreamWorker(cam, q, h)
w.start()
time.sleep(25.0)
print(f'Queue count: {q.qsize()}, Telemetry: {h.get_snapshot()[0]}')
w.stop(); w.join()
"
```

---

### 9. Definition of Done (DoD)
- [x] Stream Ingestion worker pool forces RTSP over TCP (`rtsp_transport;tcp`).
- [x] Stream disconnect automatically triggers exponential backoff sequence (`2s -> 4s -> 8s -> 16s -> 30s`).
- [x] Telemetry (`HealthRegistry`) accurately reflects real-time FPS, PTS jitter, and drop counts.
- [x] YOLOv8 accurately detects vehicles with confidence score $\ge 0.50$.
- [x] PaddleOCR & Normalizer extract license numbers and fall back to `UNKNOWN` on unreadable plates.
- [x] Multi-frame consensus algorithm filters out single-frame misreads.
- [x] CCTV frame PTS timestamp propagation and fallback ISO formatting implemented.
- [x] Enriched GIS camera registry dataset populated for all 30 cameras (`data/camera_registry.json`).
- [x] All 19 unit tests passing on central `testing` integration branch.
