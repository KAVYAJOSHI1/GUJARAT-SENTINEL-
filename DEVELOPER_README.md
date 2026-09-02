# DEVELOPER EXECUTION GUIDE — KAVYA

---

### 1. Developer Details
- **Developer Name**: Kavya
- **Role**: AI Lead & ANPR / OCR Computer Vision Engineer
- **Git Branch**: `feature/kavya-ai-anpr`

---

### 2. Project Objective
Construct the core AI Computer Vision analytics pipeline for the **SENTINEL** platform. Process incoming video stream frames, run YOLOv8 vehicle detection, locate license plate regions, preprocess crops for maximum contrast, run PaddleOCR to extract text registration numbers, apply multi-frame consensus voting across track frames to eliminate misreads, generate high-res evidence snapshots, and dispatch AI Event JSON payloads to the backend ingestion API.

---

### 3. Exact Responsibility
You own the AI pipeline codebase (`ai/detection/`, `ai/anpr/`, `ai/ocr/`, `ai/adapter/`). You are responsible for model inference execution, bounding box spatial cropping, image preprocessing, character normalization regex algorithms, multi-frame frequency voting logic, local disk evidence snapshot saving, and emitting standardized JSON payload events.

---

### 4. Exact Features to Build
1. **Vehicle Detector**: YOLOv8 inferencing detecting `car`, `truck`, `bus`, `motorcycle`, and `auto-rickshaw` ($\ge 0.50$ confidence).
2. **License Plate Region Locator**: Bounding box cropper extracting license plate region from detected vehicle region.
3. **Image Preprocessor**: Grayscale conversion, Contrast Limited Adaptive Histogram Equalization (CLAHE), and adaptive thresholding.
4. **PaddleOCR Text Extractor**: Character recognition engine returning raw plate registration string and confidence scores.
5. **Plate Normalization Engine**: Regex cleaner stripping spaces, hyphens, and invalid characters (e.g. `GJ-01 AB 1234` ➔ `GJ01AB1234`).
6. **Multi-Frame Consensus Voting Engine**: Frequency voting accumulator across sequential frames of a track to pick the most reliable plate string.
7. **Snapshot & Crop Evidence Saver**: File saving utility writing full frame snapshots and plate crop images to local evidence directory.
8. **AI Event Ingest Publisher**: HTTP POST client sending event JSON to backend API `/api/v1/events/ai-detection`.
9. **RTSP Stream Adapter & Frame Interface**: Standardized frame ingestion interface and local testing adapter.

---

### 5. What NOT to Build
- Do NOT train large object detection models from scratch. Use pretrained YOLOv8 (`yolov8n.pt`).
- Do NOT build multi-camera tracking or Re-ID algorithms (owned by Prajin).
- Do NOT build RTSP video stream worker pools or network decoders (owned by Rishit).
- Do NOT build PostgreSQL database schemas, Watchlist engines, or REST servers (owned by Vanshal).
- Do NOT build web UI components or GIS maps (owned by Isha & Vishakha).

---

### 6. Technologies
- **Python**: 3.10+
- **Object Detection**: Ultralytics YOLOv8 (`ultralytics`), PyTorch (`torch`)
- **OCR Engine**: PaddleOCR (`paddleocr`) / Tesseract fallback
- **Image Processing**: OpenCV (`cv2`), Pillow (`PIL`), NumPy
- **Stream I/O**: `RTSPStreamAdapter` (OpenCV / FFmpeg with TCP transport)

---

### 7. Recommended Models / Libraries
- `ultralytics` (YOLOv8 nano: `yolov8n.pt`)
- `paddleocr`
- `opencv-python`
- `requests`

---

### 8. Input & Integration Boundary
- **Integration Boundary with Rishit (CCTV Ingestion)**:
  - Rishit owns stream decoding and worker pools.
  - Rishit passes decoded OpenCV frame arrays (`np.ndarray`), `camera_id`, and presentation timestamps (`pts`) into Kavya's `AIPipeline.process_frame()` or `FrameInput` container.
  - Kavya's AI module accepts frames asynchronously without taking ownership of network connection retries or video stream worker pools.

```python
from ai.adapter.frame_interface import FrameInput
from ai.pipeline import AIPipeline

pipeline = AIPipeline()
frame_input = FrameInput(
    frame=bgr_frame_array,
    camera_id="CAM-GANDHINAGAR-01",
    pts=123456.78,
    timestamp="2026-09-02T12:00:00Z"
)
events = pipeline.process_frame(frame_input)
```

---

### 9. Processing Pipeline
```text
Video Frame / FrameInput ──► YOLOv8 Detection ──► Vehicle Bounding Box
                               │
                               ▼
                         Plate Locator ──► Crop License Plate Box
                               │
                               ▼
                      Image Preprocessor ──► CLAHE Grayscale Enhancement
                               │
                               ▼
                       PaddleOCR Engine ──► Extract Raw Text + Conf
                               │
                               ▼
                      Plate Normalizer ──► Regex Stripping & Cleansing
                               │
                               ▼
                    Multi-Frame Consensus ──► Accumulate Track Votes
                               │
                               ▼
                   Save Snapshot & Crop ──► Post JSON to /api/v1/events/ai-detection
```

---

### 10. Output & AI Event Object Schema
Generated event structure strictly complies with system API specifications:

```json
{
  "event_id": "evt_a1b2c3d4e5f6",
  "timestamp": "2026-09-02T12:00:00Z",
  "pts": 123456.78,
  "camera_id": "CAM-GANDHINAGAR-01",
  "vehicle": {
    "type": "car",
    "class": "car",
    "confidence": 0.94,
    "bbox": [200, 150, 800, 550],
    "track_id": 42
  },
  "license_plate": {
    "text": "GJ01AB1234",
    "plate_number": "GJ01AB1234",
    "confidence": 0.95,
    "bbox": [320, 420, 520, 480],
    "raw_text": "GJ01AB1234",
    "consensus_applied": true,
    "raw_reads": ["GJ01AB1234", "GJ01A81234", "GJ01AB1234"]
  },
  "evidence": {
    "frame_path": "evidence/CAM-GANDHINAGAR-01_1725273200_tr42_GJ01AB1234.jpg",
    "frame_snapshot_path": "evidence/CAM-GANDHINAGAR-01_1725273200_tr42_GJ01AB1234.jpg",
    "plate_crop_path": "evidence/CAM-GANDHINAGAR-01_1725273200_tr42_GJ01AB1234_crop.jpg"
  }
}
```

---

### 11. Testing & Running Options

#### A. Run Automated Unit Tests
```bash
.venv/bin/python -m unittest discover tests
```

#### B. Test Using a Local Video File
```bash
.venv/bin/python scripts/rtsp_ai_demo.py --source "sample_traffic.mp4" --camera-id "CAM-TEST-01" --frame-skip 2
```

#### C. Test Using a Live RTSP Stream URL
```bash
.venv/bin/python scripts/rtsp_ai_demo.py --source "rtsp://<host>:8554/stream/<id>" --camera-id "CAM-RTSP-01"
```

#### D. Configure via Environment Variables
```bash
export SENTINEL_RTSP_URL="rtsp://<host>:8554/stream/cam1"
export CAMERA_ID="CAM-GANDHINAGAR-01"
export FRAME_SKIP=2
export CONFIDENCE_THRESHOLD=0.50
export SENTINEL_BACKEND_URL="http://localhost:8000/api/v1/events/ai-detection"

.venv/bin/python scripts/rtsp_ai_demo.py
```

#### E. Run Performance Benchmark
```bash
.venv/bin/python scripts/demo_pipeline.py
# OR
.venv/bin/python scripts/rtsp_ai_demo.py --source "test.mp4" --benchmark
```

---

### 12. Definition of Done (DoD)
- [x] YOLOv8 accurately detects vehicles with confidence score $\ge 0.50$.
- [x] License plate cropper extracts clean crops from vehicle regions.
- [x] PaddleOCR extracts registration numbers accurately on clear frames.
- [x] Multi-frame consensus algorithm successfully filters out single-frame misreads.
- [x] RTSP Stream Adapter & `FrameInput` interface integrated for local testing and upstream frame delivery.
- [x] CCTV frame PTS timestamp propagation and fallback ISO formatting implemented.
- [x] AI Detection Event JSON payload formatted for backend compatibility.
- [x] Code committed to `feature/kavya-ai-anpr` and pushed to `origin/feature/kavya-ai-anpr`.
