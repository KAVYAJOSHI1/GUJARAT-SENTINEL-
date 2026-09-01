# Team Specification — KAVYA

## 1. Developer Profile & Module Ownership
- **Member Name**: Kavya
- **Module Ownership**: AI Processing + Vehicle Detection + ANPR / OCR
- **Git Branch**: `feature/kavya-ai-anpr`

---

## 2. Core Responsibilities
- Implement the core AI computer vision pipeline: Vehicle Detection -> License Plate Locator -> Image Preprocessing -> OCR Engine -> Normalized Registration String.
- Utilize pretrained YOLO-family models (YOLOv8) for vehicle detection and plate crop extraction.
- Implement PaddleOCR (or Tesseract fallback) for license plate character recognition.
- Build **Multi-Frame OCR Consensus Logic** to aggregate characters across sequential frames to eliminate transient OCR misreads.
- Generate evidence snapshots and transmit detection payloads to Vanshal's backend API.

---

## 3. Recommended AI Pipeline Architecture
```text
Video Frame
   │
   ▼
YOLOv8 Vehicle Detector  ──> Bounding Box (car, truck, motorcycle, bus)
   │
   ▼
Plate Region Proposal    ──> Bounding Box (License Plate Region)
   │
   ▼
Plate Crop & Preprocessing ──> Grayscale, Contrast Stretching, Deskewing
   │
   ▼
PaddleOCR Engine         ──> Raw OCR Text Stream
   │
   ▼
Character Normalization  ──> Regex Cleaning (e.g. "G J 01 A B 1 2 3 4" ➔ "GJ01AB1234")
   │
   ▼
Multi-Frame Consensus    ──> Select Most Frequent High-Confidence Registration String
   │
   ▼
JSON AI Event Creation
```

---

## 4. Technology Stack & Pretrained Models
- **Language**: Python 3.10+
- **Detection**: Ultralytics YOLOv8 (`yolov8n.pt` / `yolov8s.pt`)
- **Plate Detection**: Pretrained License Plate YOLO weights / OpenCV Contour Fallback
- **OCR**: PaddleOCR (`paddleocr`) / EasyOCR
- **Image Processing**: OpenCV (`opencv-python`), Pillow, NumPy

---

## 5. Interface & Data Contracts

### 5.1 Inputs
- Ingested raw video frames and PTS timestamp references from Rishit's stream queue.

### 5.2 Outputs (APIs Produced)
- **POST `/api/v1/events/ai-detection`**:
```json
{
  "camera_id": "CAM-AHM-001",
  "track_id": 42,
  "vehicle_type": "car",
  "plate_number": "GJ01AB1234",
  "confidence": 0.94,
  "timestamp": "2026-09-01T10:32:14Z",
  "evidence_path": "evidence/CAM-001_103214.jpg"
}
```

---

## 6. Expected Directory Layout (`ai/`)
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

## 7. Development Priorities
1. **Day 1**: Set up YOLOv8 vehicle detection pipeline on test images/video clips.
2. **Day 2**: Implement plate region proposal locator and crop extraction.
3. **Day 3**: Integrate PaddleOCR and build character normalization regex functions.
4. **Day 4**: Implement multi-frame consensus filtering and API event dispatcher.

---

## 8. Definition of Done (DoD) & Testing Requirements
- [ ] Vehicle detection successfully identifies cars, trucks, motorcycles, and buses.
- [ ] License plate detection crops valid plate regions from vehicle bounding boxes.
- [ ] OCR correctly extracts registration numbers (e.g. `GJ01AB1234`) with >90% accuracy on clear test frames.
- [ ] Multi-frame consensus successfully rejects single-frame character glitches.
- [ ] Code committed to `feature/kavya-ai-anpr` and verified on `testing`.

---

## 9. Inter-Member Dependencies
- **Rishit**: Depends on stream frames from Rishit's RTSP ingestion service.
- **Prajin**: Works closely with Prajin to associate detected plates with ByteTrack local track IDs.
- **Vanshal**: Sends final AI event JSON payloads to Vanshal's backend ingestion endpoint.
