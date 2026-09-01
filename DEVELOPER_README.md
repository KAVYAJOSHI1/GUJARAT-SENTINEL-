# DEVELOPER EXECUTION GUIDE — KAVYA

## 1. Developer Details
- **Developer Name**: Kavya
- **Role**: AI Lead & ANPR / OCR Computer Vision Engineer
- **Git Branch**: `feature/kavya-ai-anpr`

---

## 2. Mission
Kavya is responsible for constructing the AI Computer Vision pipeline. The pipeline ingests decoded video frames from the stream manager, executes YOLOv8 vehicle detection, crops license plate region proposals, preprocesses crops for character enhancement, runs PaddleOCR, applies multi-frame consensus voting across track frames to eliminate character misreads, saves snapshot evidence, and emits standardized AI event JSON payloads to the backend API.

---

## 3. Exact Features Owned
- **Vehicle Detector**: YOLOv8 inferencing detecting `car`, `truck`, `bus`, `motorcycle`, and `auto-rickshaw` ($\ge 0.50$ confidence).
- **License Plate Region Locator**: Bounding box proposal cropper extracting license plate region from detected vehicle region.
- **Image Preprocessor**: Grayscale conversion, Contrast Limited Adaptive Histogram Equalization (CLAHE), and adaptive thresholding.
- **PaddleOCR Engine**: Character extraction returning plate registration text and confidence scores.
- **Plate Normalization Regex**: String cleaning (e.g. `GJ 01 AB 1234` ➔ `GJ01AB1234`).
- **Multi-Frame Consensus Voting**: Frequency voting accumulator across sequential frames of a track to pick the most reliable plate string.
- **Snapshot & Crop Evidence Saver**: Save high-res snapshot and plate crop files to disk storage.
- **AI Event Ingest Publisher**: HTTP POST payload dispatcher pushing event JSON to backend.

---

## 4. Files You Should Work On
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

## 5. Technologies
- **Python**: 3.10+
- **Computer Vision Frameworks**: Ultralytics YOLOv8 (`yolov8n.pt`), PyTorch (`torch`)
- **OCR Engine**: PaddleOCR (`paddleocr`)
- **Image Processing**: OpenCV (`cv2`), Pillow (`PIL`), NumPy

---

## 6. Input
- Decoded OpenCV video frames (`numpy.ndarray`), `camera_id`, and PTS timestamps from Rishit's ingestion frame queue.

---

## 7. Processing Pipeline
```text
Video Frame ──► YOLOv8 Detection ──► Vehicle Bounding Box (car, truck, etc.)
                   │
                   ▼
             Plate Locator ──► Crop License Plate Region Box
                   │
                   ▼
          Image Preprocessor ──► CLAHE Grayscale & Contrast Stretching
                   │
                   ▼
           PaddleOCR Engine ──► Extract Raw Text + Confidence Score
                   │
                   ▼
          Plate Normalizer ──► Strip Spaces/Hyphens with Regex
                   │
                   ▼
        Multi-Frame Consensus ──► Accumulate Votes across Track Frames
                   │
                   ▼
       Save Snapshot & Crop ──► Post JSON to POST /api/v1/events/ai-detection
```

---

## 8. Output
- Saved evidence snapshot files on disk (`evidence/{date}/CAM_{id}_{timestamp}_{plate}.jpg`).
- Standardized AI Event JSON payloads sent to backend.

---

## 9. API Contract Reference
All emitted event payloads must strictly comply with **`docs/API_CONTRACTS.md`**:
- **AI Event Schema**: `docs/API_CONTRACTS.md#2-ai-event-object-schema`

---

## 10. Integration Dependencies
- **Upstream Providers**:
  - **Rishit (`feature/rishit-stream`)**: Provides decoded video frames and PTS timestamps.
  - **Prajin (`feature/prajin-tracking`)**: Supplies local ByteTrack IDs to group multi-frame OCR predictions.
- **Downstream Consumers**:
  - **Vanshal (`feature/vanshal-backend`)**: Ingests AI event JSON payloads into PostgreSQL/PostGIS database.

---

## 11. Testing Requirements
- Unit test plate cleaning regex on 20+ dirty test strings (`GJ-01 AB 1234`, `G.J.01.AB.1234`).
- Test multi-frame consensus algorithm across 10 simulated frame predictions containing noisy outlier reads.
- Test pipeline processing speed on sample MP4 test video clips.

---

## 12. Definition of Done (DoD)
- [ ] YOLOv8 accurately detects vehicles with confidence score $\ge 0.50$.
- [ ] License plate cropper extracts clean crops from vehicle regions.
- [ ] PaddleOCR extracts registration numbers with $>90\%$ accuracy on clear test frames.
- [ ] Multi-frame consensus algorithm successfully filters out single-frame character misreads.
- [ ] AI Event JSON payload is posted to backend `/api/v1/events/ai-detection` endpoint.
- [ ] Code committed to `feature/kavya-ai-anpr` and Pull Request opened to `testing`.

---

## 13. Git Branching Instructions
```bash
# 1. Work exclusively on your feature branch
git checkout feature/kavya-ai-anpr

# 2. Commit changes
git add .
git commit -m "feat(ai): implement YOLO vehicle detection, PaddleOCR, and multi-frame consensus"

# 3. Push to GitHub
git push origin feature/kavya-ai-anpr

# 4. Open Pull Request on GitHub:
# feature/kavya-ai-anpr  ──►  testing (Central Integration Branch)
# NEVER push directly to main!
```
