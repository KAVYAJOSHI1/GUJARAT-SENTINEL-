# DEVELOPER EXECUTION GUIDE — PRAJIN

## 1. Developer Details
- **Developer Name**: Prajin
- **Role**: Vehicle Tracking & Cross-Camera Correlation Engineer
- **Git Branch**: `feature/prajin-tracking`

---

## 2. Mission
Prajin is responsible for multi-object tracking within individual camera views using ByteTrack, associating local track IDs with license plate detection boxes, suppressing duplicate AI event emissions for active tracks, and building the cross-camera vehicle trajectory correlation engine that reconstructs chronological journeys based on registration plate strings.

---

## 3. Exact Features Owned
- **ByteTrack Multi-Object Tracker**: Wrap ByteTrack library to maintain persistent local track IDs (`Track #1`, `Track #2`) per camera feed.
- **Track Lifecycle Manager**: Handle track creation, track updates across frames, and track termination when vehicle leaves FOV.
- **Track ↔ Plate Association**: Match extracted license plate region bounding boxes to overlapping vehicle bounding box track IDs using Intersection-over-Union (IoU).
- **Local Event Deduplication**: Suppress duplicate event emissions so 1 consolidated AI event is sent per completed vehicle track.
- **Cross-Camera Trajectory Builder**: Backend engine correlating vehicle detections across different camera locations chronologically by plate string `GJ01AB1234`.

---

## 4. Files You Should Work On
```text
ai/tracking/
├── tracker.py           # ByteTrack initialization & frame update wrapper
├── track_association.py # Track ID ↔ Plate matching logic
├── correlation.py       # Cross-camera timestamp trajectory builder
└── README.md
```

---

## 5. Technologies
- **Python**: 3.10+
- **Multi-Object Tracker**: ByteTrack (`bytetrack` / `lap`)
- **Spatial / Assignment Algorithms**: NumPy, SciPy (Hungarian Algorithm / Linear Sum Assignment)

---

## 6. Input
- Vehicle bounding boxes `(x1, y1, x2, y2, score, class)` from Kavya's YOLO detector.
- License plate region crops and candidate OCR strings from Kavya's ANPR module.

---

## 7. Processing Pipeline
```text
YOLO Vehicle Bounding Boxes & Video Frames
 │
 ▼
ByteTrack Update ──► Assign Camera-Local Track ID (e.g. Track #42)
 │
 ▼
Track ↔ Plate IoU Matcher ──► Bind Plate String "GJ01AB1234" to Track #42
 │
 ▼
Track Termination / Age Out ──► Finalize Consensus Plate ──► Emit 1 Event
 │
 ▼
Cross-Camera Trajectory ──► Sort Events by Plate String + Timestamp ASC Across Cameras
```

---

## 8. Output
- Enriched vehicle tracking bounding box objects tagged with persistent local `track_id`.
- Chronologically ordered trajectory arrays for vehicle plate queries.

---

## 9. API Contract Reference
Cross-camera vehicle trajectory responses must comply with **`docs/API_CONTRACTS.md`**:
- **Vehicle History Schema**: `docs/API_CONTRACTS.md#4-vehicle-history-response-schema`

---

## 10. Integration Dependencies
- **Upstream Providers**:
  - **Kavya (`feature/kavya-ai-anpr`)**: Consumes YOLO vehicle bounding boxes and plate OCR candidate text.
- **Downstream Consumers**:
  - **Vanshal (`feature/vanshal-backend`)**: Supplies cross-camera trajectory data to Vanshal's backend `/api/v1/vehicles/search` endpoint.
  - **Vishakha (`feature/vishakha-investigation`)**: Trajectory array feeds Vishakha's Leaflet polyline route map.

---

## 11. Testing Requirements
- Unit test IoU association between vehicle bounding box and plate crop bounding box.
- Test cross-camera trajectory sorting with out-of-order event timestamps to verify correct chronological order.
- Test tracking persistence under simulated frame drops.

---

## 12. Definition of Done (DoD)
- [ ] ByteTrack maintains persistent camera-local track IDs for vehicles in continuous stream views.
- [ ] Track event deduplication ensures only 1 consolidated event is emitted per completed vehicle track.
- [ ] Cross-camera correlation engine correctly sorts sightings by timestamp `ASC` for a target plate string `GJ01AB1234`.
- [ ] Code committed to `feature/prajin-tracking` and Pull Request opened to `testing`.

---

## 13. Git Branching Instructions
```bash
# 1. Work exclusively on your feature branch
git checkout feature/prajin-tracking

# 2. Commit changes
git add .
git commit -m "feat(tracking): integrate ByteTrack and build cross-camera trajectory engine"

# 3. Push to GitHub
git push origin feature/prajin-tracking

# 4. Open Pull Request on GitHub:
# feature/prajin-tracking  ──►  testing (Central Integration Branch)
# NEVER push directly to main!
```
