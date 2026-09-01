# Implementation Specification — KAVYA (AI + ANPR / OCR)

---

### 1. Ownership
- **Developer Name**: Kavya
- **Module Ownership**: AI Computer Vision Pipeline, Vehicle Detection, License Plate Location & OCR Engine
- **Git Branch**: `feature/kavya-ai-anpr`

---

### 2. Objective
Construct a robust, real-time computer vision processing pipeline that accepts incoming video frames, detects vehicle bounding boxes, crops license plate regions, executes Optical Character Recognition (OCR), cleans character strings, applies multi-frame consensus voting, and emits standardized AI event JSON payloads to the backend.

---

### 3. Responsibilities
- Implement YOLOv8 vehicle detection for `car`, `truck`, `bus`, `motorcycle`, and `auto-rickshaw`.
- Implement license plate region proposal locator and crop extractor.
- Integrate PaddleOCR for character extraction from preprocessed plate crops.
- Build character normalization regex to standardize plate numbers (e.g. `GJ 01 AB 1234` ➔ `GJ01AB1234`).
- Build **Multi-Frame Consensus Voting** logic across consecutive frames of a track to eliminate single-frame character glitches.
- Generate high-resolution evidence snapshots and plate crop files.

---

### 4. Features to Implement
1. **Vehicle Detector**: YOLOv8 inferencing with configurable confidence thresholds ($\ge 0.50$).
2. **Plate Region Locator**: Bounding box cropper extracting license plate region from vehicle bounding box.
3. **Image Preprocessor**: Grayscale conversion, contrast stretching (CLAHE), and adaptive thresholding.
4. **PaddleOCR Integration**: Character recognition returning text string and confidence.
5. **Multi-Frame Consensus**: Voting dictionary accumulating character frequency across 5+ frames per vehicle track.
6. **AI Event Dispatcher**: HTTP POST payload sender pushing event JSON to Vanshal's backend.

---

### 5. Module Architecture
```text
Video Frame (from Ingestion)
 │
 ▼
Vehicle Detector (YOLOv8) ──► Bounding Boxes (car, truck, motorcycle)
 │
 ▼
Plate Detector / Locator  ──► Bounding Box (Plate Region)
 │
 ▼
Image Preprocessor        ──► Grayscale, Contrast Stretching, Deskewing
 │
 ▼
PaddleOCR Engine          ──► Raw OCR Text & Confidence
 │
 ▼
Character Normalizer      ──► Clean Registration String (Regex)
 │
 ▼
Multi-Frame Consensus     ──► Frequency Accumulator across Track
 │
 ▼
AI Event Publisher        ──► POST /api/v1/events/ai-detection
```

---

### 6. Technologies
- **Python**: 3.10+
- **Detector**: Ultralytics YOLOv8 (`yolov8n.pt` / `yolov8s.pt`)
- **OCR Engine**: PaddleOCR (`paddleocr`) / EasyOCR
- **Image Processing**: OpenCV (`cv2`), Pillow, NumPy

---

### 7. Folder Structure
```text
ai/
├── detection/
│   ├── vehicle_detector.py
│   └── yolo_utils.py
├── anpr/
│   ├── plate_locator.py
│   └── crop_utils.py
├── ocr/
│   ├── ocr_engine.py
│   ├── preprocess.py
│   └── consensus.py
├── weights/
│   └── yolov8n.pt
├── pipeline.py
└── README.md
```

---

### 8. Detailed Implementation Tasks
1. Load `yolov8n.pt` pretrained model in `vehicle_detector.py`.
2. Implement `detect_vehicles(frame)` filtering COCO classes: 2 (car), 3 (motorcycle), 5 (bus), 7 (truck).
3. Implement `plate_locator.py` cropping plate region from top 40% lower bound of vehicle bounding box.
4. Build `preprocess.py` executing `cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)` and `cv2.createCLAHE(clipLimit=2.0)`.
5. Implement `ocr_engine.py` invoking PaddleOCR `ocr.ocr(crop, cls=True)`.
6. Implement plate string cleaning regex: `re.sub(r'[^A-Z0-9]', '', raw_text.upper())`.
7. Build `consensus.py` maintaining dictionary `{track_id: Counter([plate_candidates])}` selecting candidate with highest vote count when track completes.
8. Save snapshot image to `evidence/{date}/CAM_{id}_{timestamp}_{plate}.jpg` and plate crop to `evidence/{date}/crops/`.
9. Send POST payload to `http://localhost:8000/api/v1/events/ai-detection`.

---

### 9. Input
- Decoded OpenCV video frames (`numpy.ndarray`), camera ID, and PTS timestamp from Rishit's stream queue.

---

### 10. Output
- Saved image snapshot and crop files on disk.
- Standardized AI Event JSON payload.

---

### 11. APIs Produced
- **`POST /api/v1/events/ai-detection`**:
```json
{
  "camera_id": "CAM-AHM-021",
  "track_id": 42,
  "vehicle_type": "car",
  "plate_number": "GJ01AB1234",
  "raw_ocr_text": "GJ 01 AB 1234",
  "confidence": 0.96,
  "timestamp": "2026-09-01T10:32:14.000Z",
  "evidence_snapshot_path": "evidence/20260901/CAM-AHM-021_103214_GJ01AB1234.jpg",
  "plate_crop_path": "evidence/20260901/crops/CAM-AHM-021_103214_crop.jpg"
}
```

---

### 12. Database Interaction
No direct database operations. Relies on backend REST API endpoint for event insertion.

---

### 13. Dependencies on Other Members
- **Rishit**: Requires decoded RTSP video frames and PTS timestamps from Rishit's ingestion stream.
- **Prajin**: Shares local ByteTrack track IDs to group multi-frame OCR predictions per vehicle.
- **Vanshal**: Sends final event JSON payloads to Vanshal's backend API.

---

### 14. Integration Contract
Must strictly adhere to `docs/API_CONTRACTS.md` Section 2 (AI Event Schema).

---

### 15. Error Handling & Edge Cases
- **Low OCR Confidence ($< 0.50$)**: Candidate string is discarded from consensus pool.
- **Blurry / No Plate Detected**: Vehicle detection event is logged without plate string; no false plate event emitted.
- **Ambiguous Characters**: Handle common OCR misread mappings carefully (e.g. `O` ↔ `0`, `I` ↔ `1`) using state code context (`GJ` prefix validation).

---

### 16. Testing Requirements
- Unit test plate cleaning regex on 20+ dirty test strings (`GJ-01 AB 1234`, `G.J.01.AB.1234`).
- Test multi-frame consensus algorithm across 10 simulated frame predictions containing 2 noisy outlier reads.

---

### 17. Performance Requirements
- YOLO vehicle detection inference latency $< 25$ ms on GPU ($< 80$ ms on CPU).
- PaddleOCR inference latency $< 45$ ms per plate crop.

---

### 18. Day 1 Plan
Setup YOLOv8 vehicle detection pipeline on sample test video files.

---

### 19. Day 2 Plan
Implement plate locator cropper, image preprocessing pipeline, and PaddleOCR integration.

---

### 20. Day 3 Plan
Implement multi-frame consensus voting logic and image snapshot saving utility.

---

### 21. Day 4 Plan
Integrate backend HTTP event publisher, benchmark latency, and execute integration tests on `testing`.

---

### 22. Definition of Done (DoD)
- [ ] YOLOv8 accurately detects cars, trucks, motorcycles, and buses.
- [ ] License plate cropper extracts clean crops from vehicle bounding boxes.
- [ ] PaddleOCR extracts registration numbers with $>90\%$ accuracy on clear test frames.
- [ ] Multi-frame consensus successfully filters out transient character misreads.
- [ ] AI Event JSON payload is successfully posted to backend `/events/ai-detection` endpoint.
- [ ] Code committed to `feature/kavya-ai-anpr` and verified on `testing`.

---

### 23. Deliverables
- Complete `ai/` computer vision source codebase.
- Pretrained model loading configuration scripts.

---

### 24. What NOT to do
- Do NOT train large models from scratch during the hackathon; use pretrained YOLOv8 and PaddleOCR weights.
- Do NOT emit AI events on every single frame; emit 1 consensus event per completed vehicle track.
- Do NOT push directly to `main`.

---

### 25. Merge Checklist
- [ ] Multi-frame consensus algorithm verified
- [ ] Sample test video runs through pipeline without crashes
- [ ] PR opened from `feature/kavya-ai-anpr` to `testing`
