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
You own the AI pipeline codebase (`ai/detection/`, `ai/anpr/`, `ai/ocr/`). You are responsible for model inference execution, bounding box spatial cropping, image preprocessing, character normalization regex algorithms, multi-frame frequency voting logic, local disk evidence snapshot saving, and emitting standardized JSON payload events.

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

---

### 7. Recommended Models / Libraries
- `ultralytics` (YOLOv8 nano: `yolov8n.pt`)
- `paddleocr`
- `opencv-python`
- `requests`

---

### 8. Input
- Decoded OpenCV video frame arrays (`numpy.ndarray`), `camera_id`, and PTS timestamps provided by Rishit's stream ingestion queue.

---

### 9. Processing Pipeline
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

### 10. Output
- Saved snapshot image files on disk (`evidence/CAM_{id}_{timestamp}_{plate}.jpg`).
- AI Detection Event JSON payloads dispatched to backend ingestion API.

---

### 11. Required API Contract
Must strictly comply with `testing` integration contracts documented in `docs/API_CONTRACTS.md`:
- **AI Event Object Schema**: `docs/API_CONTRACTS.md#2-ai-event-object-schema`

---

### 12. Database Interaction
No direct database interaction. Emits HTTP POST requests containing detection metadata to Vanshal's FastAPI backend `/api/v1/events/ai-detection`.

---

### 13. Integration Dependencies
- **Upstream Providers**:
  - **Rishit (`feature/rishit-stream`)**: Provides decoded video frame arrays and PTS timestamps.
  - **Prajin (`feature/prajin-tracking`)**: Supplies camera-local ByteTrack IDs to group multi-frame predictions.
- **Downstream Consumers**:
  - **Vanshal (`feature/vanshal-backend`)**: Ingests AI event JSON payloads into PostgreSQL/PostGIS database and evaluates Watchlist rules.

---

### 14. Exact Implementation Steps
1. Create `ai/` folder structure (`ai/detection/`, `ai/anpr/`, `ai/ocr/`, `ai/weights/`).
2. Download `yolov8n.pt` pretrained weights into `ai/weights/`.
3. Build `vehicle_detector.py` wrapping YOLOv8 inferencing with confidence threshold $\ge 0.50$.
4. Build `plate_locator.py` extracting plate bounding box sub-images.
5. Build `preprocess.py` executing CLAHE grayscale enhancement.
6. Build `ocr_engine.py` wrapping PaddleOCR.
7. Build `consensus.py` storing frame OCR predictions per track and returning majority vote result.
8. Build `pipeline.py` orchestrating end-to-end processing and dispatching HTTP POST requests.

---

### 15. Error Handling
- **Low Confidence OCR**: If OCR confidence $< 0.60$, mark plate string `UNKNOWN` and log frame.
- **No Vehicle Bounding Box**: Skip frame processing immediately to save GPU/CPU cycles.
- **Backend API Unreachable**: Catch HTTP connection errors and queue event payloads locally in memory buffer.

---

### 16. Testing Requirements
- Test plate normalization regex on 20+ dirty test strings (`GJ-01 AB 1234`, `G.J.01.AB.1234`).
- Test multi-frame consensus algorithm across 10 simulated frame predictions containing noisy outlier reads.
- Test end-to-end pipeline processing speed on sample MP4 test video clips.

---

### 17. Performance Requirements
- YOLO vehicle detection inference $< 30$ ms per frame on GPU / $< 80$ ms on CPU.
- ANPR plate crop + PaddleOCR inference $< 50$ ms per vehicle.
- End-to-end frame processing throughput $\ge 15$ FPS per stream.

---

### 18. Day 1 Tasks
Setup Python environment, download YOLOv8 weights, build `vehicle_detector.py` and test detection on sample vehicle images.

---

### 19. Day 2 Tasks
Build `plate_locator.py` bounding box cropper, build `preprocess.py` image enhancer, connect PaddleOCR engine.

---

### 20. Day 3 Tasks
Build `consensus.py` multi-frame voting aggregator, build plate normalization regex module, save snapshot files to evidence folder.

---

### 21. Day 4 Tasks
Build `pipeline.py` orchestrator, connect HTTP POST client to backend `/api/v1/events/ai-detection`, perform pipeline benchmark tests.

---

### 22. Definition of Done (DoD)
- [ ] YOLOv8 accurately detects vehicles with confidence score $\ge 0.50$.
- [ ] License plate cropper extracts clean crops from vehicle regions.
- [ ] PaddleOCR extracts registration numbers with $>90\%$ accuracy on clear test frames.
- [ ] Multi-frame consensus algorithm successfully filters out single-frame character misreads.
- [ ] AI Event JSON payload is posted to backend `/api/v1/events/ai-detection` endpoint.
- [ ] Code committed to `feature/kavya-ai-anpr` and Pull Request opened to `testing`.

---

### 23. Git Workflow
```bash
# 1. Work exclusively on your feature branch
git checkout feature/kavya-ai-anpr

# 2. Add implementation files as you build
git add ai/

# 3. Commit changes
git commit -m "feat(ai): implement YOLO vehicle detection, PaddleOCR, and multi-frame consensus"

# 4. Push to GitHub
git push origin feature/kavya-ai-anpr

# 5. Open Pull Request on GitHub:
# feature/kavya-ai-anpr  ──►  testing (Central Integration Branch)
# NEVER push directly to main!
```

---

### 24. What Must Be Demonstrated Before PR
1. YOLOv8 detecting vehicles in a test video stream with bounding boxes.
2. PaddleOCR outputting normalized plate string `GJ01AB1234` from cropped plate region.
3. Multi-frame consensus voting correcting 1 noisy frame misread (`GJ01A81234` ➔ `GJ01AB1234`).
4. HTTP POST request successfully sending AI Event JSON payload.

---

### 25. Shared Technical Reference
For central system specifications, hybrid architecture decisions, and database schemas, refer to the integration blueprints on `testing`:
- `docs/ARCHITECTURE.md`
- `docs/API_CONTRACTS.md`
- `docs/TESTING.md`

---

### 26. Final Workspace Rule
This branch starts with **ONLY** `DEVELOPER_README.md`. As developer Kavya, you will create the `ai/` directory and implementation files as you code. Do NOT commit unnecessary root scaffold files.
