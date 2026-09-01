# Team Specification — PRAJIN

## 1. Developer Profile & Module Ownership
- **Member Name**: Prajin
- **Module Ownership**: Vehicle Tracking + Cross-Camera Event Correlation
- **Git Branch**: `feature/prajin-tracking`

---

## 2. Core Responsibilities
- Implement multi-object tracking within individual camera feeds using **ByteTrack** (or OpenCV Kalman filter tracker).
- Maintain local bounding box track IDs (`Track #1`, `Track #2`) per camera stream to prevent redundant ANPR OCR execution on every frame.
- Implement **Cross-Camera Vehicle Identity Correlation**: map local track IDs to global normalized registration numbers (`GJ01AB1234`).
- Calculate vehicle trajectory statistics: `first_seen`, `last_seen`, `total_sightings`, camera-to-camera movement sequence, and estimated transit times.

---

## 3. Tracking & Correlation Paradigm

```text
Camera-Local Frame Stream
   │
   ▼
ByteTrack Multi-Object Tracker ──> Assign Local Track ID (e.g., Track #42)
   │
   ▼
Track ↔ Plate Association     ──> Bind Plate "GJ01AB1234" to Track #42
   │
   ▼
Single Event Per Vehicle Track ──> Emit 1 Consolidated Event per Track (Not 30 frames/sec)
   │
   ▼
Global Correlation Engine      ──> Aggregate "GJ01AB1234" Detections Across CAM-007 ➔ CAM-013 ➔ CAM-021
```

> [!IMPORTANT]
> **Global Identity Rule**: Camera-local track IDs (e.g. `Track #42`) must **NEVER** be treated as global vehicle identities. Global cross-camera identity relies exclusively on the normalized registration plate string.

---

## 4. Technology Stack
- **Tracker**: ByteTrack / BoT-SORT / OpenCV MultiTracker
- **Language**: Python 3.10+
- **Data Structures**: Spatial-Temporal Indexing, Priority Queues

---

## 5. Interface & Data Contracts

### 5.1 Inputs
- Vehicle detection bounding boxes from Kavya's YOLO model.
- Timestamped plate extraction events from Kavya's OCR engine.

### 5.2 Outputs
- Enriched Event Objects containing `track_id`, `trajectory_points`, `first_seen`, `last_seen`, and camera sequence arrays sent to Vanshal's backend.

---

## 6. Expected Directory Layout (`ai/tracking/`)
```text
ai/tracking/
├── tracker.py           # ByteTrack initialization & frame update
├── track_association.py # Track ID ↔ Plate matching logic
├── correlation.py       # Cross-camera timestamp trajectory builder
└── README.md
```

---

## 7. Development Priorities
1. **Day 1**: Integrate ByteTrack wrapper with YOLO vehicle detection bounding boxes.
2. **Day 2**: Implement Track ID ↔ ANPR plate association logic.
3. **Day 3**: Build local track deduplication to avoid event spamming.
4. **Day 4**: Build cross-camera chronological correlation and transit time calculators.

---

## 8. Definition of Done (DoD) & Testing Requirements
- [ ] Local ByteTrack maintains persistent track IDs for vehicles moving across a single camera view.
- [ ] System emits a single consolidated event when a vehicle passes a camera (rather than firing events every frame).
- [ ] Searching a plate string correctly correlates records across multiple distinct cameras in sequential order.
- [ ] Code committed to `feature/prajin-tracking` and verified against `testing`.

---

## 9. Inter-Member Dependencies
- **Kavya**: Relies on Kavya's YOLO bounding boxes and ANPR OCR plate strings.
- **Vanshal**: Supplies cross-camera trajectory data to Vanshal's database query services.
