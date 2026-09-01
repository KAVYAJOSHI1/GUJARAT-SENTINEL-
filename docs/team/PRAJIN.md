# Implementation Specification — PRAJIN (Tracking & Correlation)

---

### 1. Ownership
- **Developer Name**: Prajin
- **Module Ownership**: Multi-Object Vehicle Tracking & Cross-Camera Event Correlation
- **Git Branch**: `feature/prajin-tracking`

---

### 2. Objective
Implement local object tracking using ByteTrack within individual camera video feeds to maintain persistent track IDs, associate tracked vehicles with detected license plates, deduplicate redundant frame events, and construct cross-camera vehicle movement trajectories sorted chronologically by registration plate string.

---

### 3. Responsibilities
- Integrate ByteTrack multi-object tracker with Kavya's YOLO vehicle bounding box outputs.
- Maintain persistent camera-local track IDs (`Track #1`, `Track #2`) per stream.
- Bind extracted license plate numbers (`GJ01AB1234`) to local ByteTrack IDs.
- Deduplicate detection events to ensure a single vehicle track emits only 1 consolidated event (instead of 30 events per second).
- Implement the **Cross-Camera Correlation Engine**: sort detections across different cameras chronologically by normalized registration plate string.

---

### 4. Features to Implement
1. **ByteTrack Integration**: Wrap ByteTrack Python library to accept YOLO bounding boxes `(x1, y1, x2, y2, score, class)`.
2. **Track Life-Cycle Manager**: Handle track creation, track update across frames, and track termination when vehicle leaves camera FOV.
3. **Track ↔ Plate Assocation**: Associate plate OCR candidate strings with the overlapping vehicle bounding box track ID.
4. **Local Event Deduplicator**: Suppress duplicate AI event emissions for an active track until consensus plate is finalized.
5. **Cross-Camera Trajectory Builder**: Correlate events sharing plate string `GJ01AB1234` into a chronological camera trajectory (`CAM-007 ➔ CAM-013 ➔ CAM-021 ➔ CAM-034`).

---

### 5. Module Architecture
```text
YOLO Bounding Boxes & Video Frames
 │
 ▼
ByteTrack Tracker ──► Assign Camera-Local Track ID (e.g. Track #42)
 │
 ▼
Track ↔ Plate Matcher ──► Bind Plate String "GJ01AB1234" to Track #42
 │
 ▼
Local Event Deduplicator ──► Emit 1 Consolidated Event per Completed Track
 │
 ▼
Cross-Camera Correlation ──► Sort Detections by Plate String + Timestamp Across Cameras
```

---

### 6. Technologies
- **Python**: 3.10+
- **Tracker**: ByteTrack (`bytetrack` / `lap`)
- **Spatial Indexing**: NumPy, SciPy (Linear Sum Assignment / Hungarian Algorithm)

---

### 7. Folder Structure
```text
ai/tracking/
├── tracker.py           # ByteTrack initialization & frame update wrapper
├── track_association.py # Track ID ↔ Plate matching logic
├── correlation.py       # Cross-camera timestamp trajectory builder
└── README.md
```

---

### 8. Detailed Implementation Tasks
1. Install ByteTrack dependencies (`lap`, `cython_bbox`).
2. Implement `tracker.py` exposing `update_tracker(detections, frame)` returning tracked bounding boxes with persistent IDs.
3. Implement `track_association.py` using Intersection-over-Union (IoU) to match plate crop bounding boxes to vehicle track bounding boxes.
4. Implement track termination hook: when a track is lost for $> 30$ consecutive frames, trigger final multi-frame OCR consensus and emit single consolidated AI event.
5. Implement `correlation.py` backend utility function `build_vehicle_trajectory(plate_number)` querying PostgreSQL `vehicle_events` sorted by `timestamp ASC`.
6. Calculate trajectory statistics: `first_seen`, `last_seen`, `total_sightings`, and camera transit time intervals.

---

### 9. Input
- Vehicle bounding boxes from Kavya's YOLO model.
- License plate OCR candidate strings and bounding boxes.

---

### 10. Output
- Enriched tracking event objects containing persistent `track_id`.
- Chronologically ordered trajectory arrays for cross-camera plate queries.

---

### 11. APIs Produced / Supported
- Internal tracking helper methods used by AI pipeline before posting to `/api/v1/events/ai-detection`.
- Backend trajectory builder function supporting `GET /api/v1/vehicles/search?plate={plate}`.

---

### 12. Database Interaction
Queries `vehicle_events` table indexed on `plate_number` and `timestamp`.

---

### 13. Dependencies on Other Members
- **Kavya**: Depends on YOLO vehicle bounding boxes and ANPR OCR candidate text from Kavya.
- **Vanshal**: Supplies cross-camera trajectory data structures to Vanshal's FastAPI vehicle search endpoints.

---

### 14. Integration Contract
Must maintain global identity strictly via normalized registration plate strings as specified in `docs/ARCHITECTURE.md` Section 10.

---

### 15. Error Handling & Edge Cases
- **Occlusion / Lost Track**: If a vehicle is temporarily occluded and assigned a new local Track ID (`Track #45`), global identity remains unified by matching the same plate string `GJ01AB1234`.
- **Out-of-Order Frame Telemetry**: Sort events explicitly by PTS `timestamp ASC` during cross-camera trajectory reconstruction.
- **Multiple Vehicles with Unreadable Plates**: Track IDs maintain visual separation even if plates are obscured.

---

### 16. Testing Requirements
- Unit test IoU association between vehicle bounding box and plate crop bounding box.
- Test cross-camera correlation logic with out-of-order event timestamps to verify correct sorting.

---

### 17. Performance Requirements
- ByteTrack processing latency $< 5$ ms per frame.
- Cross-camera trajectory query execution $< 50$ ms for 1,000+ historical events.

---

### 18. Day 1 Plan
Setup ByteTrack Python wrapper and test local tracking on test video clip.

---

### 19. Day 2 Plan
Implement Track ID ↔ Plate crop IoU association logic.

---

### 20. Day 3 Plan
Implement local track deduplication hook (emit 1 event per track completion).

---

### 21. Day 4 Plan
Build cross-camera trajectory builder function and verify integration against `testing`.

---

### 22. Definition of Done (DoD)
- [ ] ByteTrack maintains persistent local track IDs for vehicles across continuous camera views.
- [ ] Single consolidated event is emitted per vehicle track (preventing event spam).
- [ ] Searching a plate string returns chronologically sorted sightings across different cameras.
- [ ] Code committed to `feature/prajin-tracking` and verified on `testing`.

---

### 23. Deliverables
- ByteTrack integration wrapper source code (`ai/tracking/`).
- Cross-camera correlation trajectory builder utility.

---

### 24. What NOT to do
- Do NOT treat camera-local Track IDs (e.g. `Track #42`) as global vehicle identities across different cameras.
- Do NOT run heavy AI re-identification models on every frame during the initial PoC.
- Do NOT push directly to `main`.

---

### 25. Merge Checklist
- [ ] Local ByteTrack tracking verified on test stream
- [ ] Cross-camera trajectory sorting verified
- [ ] PR opened from `feature/prajin-tracking` to `testing`
