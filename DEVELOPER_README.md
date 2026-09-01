# DEVELOPER EXECUTION GUIDE — PRAJIN

---

### 1. Developer Details
- **Developer Name**: Prajin
- **Role**: Vehicle Tracking & Cross-Camera Correlation Engineer
- **Git Branch**: `feature/prajin-tracking`

---

### 2. Project Objective
Build the multi-object tracking and cross-camera correlation engine for the **SENTINEL** platform. Track moving vehicles within individual camera views using ByteTrack, associate license plate detection bounding boxes to active vehicle tracks using Intersection-over-Union (IoU), eliminate duplicate event emissions across continuous video frames, and correlate vehicle sightings across different cameras chronologically by registration plate strings.

---

### 3. Exact Responsibility
You own the tracking module (`ai/tracking/`). You are responsible for ByteTrack lifecycle management (track creation, update, termination), matching license plate sub-bounding boxes to parent vehicle track IDs, track event deduplication, and assembling cross-camera chronological movement trajectories.

---

### 4. Exact Features to Build
1. **ByteTrack Multi-Object Tracker**: Wrap ByteTrack library to maintain persistent local track IDs (`Track #1`, `Track #2`) per camera feed.
2. **Track Lifecycle Manager**: Handle track creation, track updates across frames, and track termination when vehicle leaves FOV.
3. **Track ↔ Plate Association**: Match extracted license plate region bounding boxes to overlapping vehicle bounding box track IDs using Intersection-over-Union (IoU).
4. **Local Event Deduplication**: Suppress duplicate event emissions so 1 consolidated AI event is sent per completed vehicle track.
5. **Cross-Camera Trajectory Builder**: Backend engine correlating vehicle detections across different camera locations chronologically by plate string `GJ01AB1234`.
6. **Primary Cross-Camera Identity**: Correlate using `plate_number + timestamp + camera_id + location`.
7. **Optional Vehicle Re-ID Module**: Feature vector comparison for unplated vehicle matching (bonus/optional module).

---

### 5. What NOT to Build
- Do NOT make vehicle Re-ID a hard dependency for the primary vehicle tracking flow.
- Do NOT build RTSP video ingestion workers or network decoders (owned by Rishit).
- Do NOT build YOLO vehicle detectors or PaddleOCR engines (owned by Kavya).
- Do NOT build PostgreSQL database migrations or REST servers (owned by Vanshal).
- Do NOT build web UI components or GIS maps (owned by Isha & Vishakha).

---

### 6. Technologies
- **Python**: 3.10+
- **Multi-Object Tracker**: ByteTrack (`bytetrack` / `lap`)
- **Spatial / Assignment Algorithms**: NumPy, SciPy (Hungarian Algorithm / Linear Sum Assignment)

---

### 7. Recommended Models / Libraries
- `bytetrack`
- `lap` (Linear Assignment Problem solver)
- `scipy`
- `numpy`

---

### 8. Input
- Vehicle bounding boxes `(x1, y1, x2, y2, score, class)` from Kavya's YOLO detector.
- License plate region crops and candidate OCR strings from Kavya's ANPR module.

---

### 9. Processing Pipeline
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

### 10. Output
- Enriched vehicle tracking bounding box objects tagged with persistent local `track_id`.
- Chronologically ordered trajectory arrays for vehicle plate queries.

---

### 11. Required API Contract
Must strictly comply with `testing` integration contracts documented in `docs/API_CONTRACTS.md`:
- **Vehicle History Response Schema**: `docs/API_CONTRACTS.md#4-vehicle-history-response-schema`

---

### 12. Database Interaction
No direct database tables created. Supplies trajectory array sorting logic to Vanshal's PostgreSQL backend queries (`/api/v1/vehicles/search`).

---

### 13. Integration Dependencies
- **Upstream Providers**:
  - **Kavya (`feature/kavya-ai-anpr`)**: Consumes YOLO vehicle bounding boxes and plate OCR candidate text.
- **Downstream Consumers**:
  - **Vanshal (`feature/vanshal-backend`)**: Supplies cross-camera trajectory data to Vanshal's backend `/api/v1/vehicles/search` endpoint.
  - **Vishakha (`feature/vishakha-investigation`)**: Trajectory array feeds Vishakha's Leaflet polyline route map.

---

### 14. Exact Implementation Steps
1. Create `ai/tracking/` folder structure (`tracker.py`, `track_association.py`, `correlation.py`).
2. Implement `tracker.py` wrapping ByteTrack initialization and frame-by-frame bounding box update loop.
3. Implement `track_association.py` computing IoU overlaps between vehicle bounding boxes and plate crops.
4. Implement deduplication logic ensuring only 1 event payload is dispatched when a vehicle leaves camera view.
5. Implement `correlation.py` receiving multi-camera event lists and sorting by timestamp `ASC`.

---

### 15. Error Handling
- **Track Discontinuity**: If a vehicle is briefly occluded for $< 15$ frames, maintain track ID using ByteTrack Kalman filter predictions.
- **No Plate Match**: If no plate is detected for a track, assign temporary ID `UNPLATED_TRACK_{id}` and do not crash pipeline.

---

### 16. Testing Requirements
- Unit test IoU association between vehicle bounding box and plate crop bounding box.
- Test cross-camera trajectory sorting with out-of-order event timestamps to verify correct chronological order.
- Test tracking persistence under simulated frame drops.

---

### 17. Performance Requirements
- ByteTrack update latency $< 5$ ms per frame.
- Track ↔ Plate IoU association latency $< 2$ ms.
- Cross-camera trajectory sorting $< 10$ ms for 100+ events.

---

### 18. Day 1 Tasks
Setup Python environment, install ByteTrack dependencies, build `tracker.py` wrapper, test tracking on sample vehicle bounding boxes.

---

### 19. Day 2 Tasks
Build `track_association.py` IoU bounding box matcher, test linking plate crops to parent vehicle tracks.

---

### 20. Day 3 Tasks
Build track event deduplicator to prevent redundant event bursts, build `correlation.py` cross-camera trajectory builder.

---

### 21. Day 4 Tasks
Run integration tests combining Kavya's AI pipeline outputs with your tracking engine, verify trajectory chronological ordering.

---

### 22. Definition of Done (DoD)
- [ ] ByteTrack maintains persistent camera-local track IDs for vehicles in continuous stream views.
- [ ] Track event deduplication ensures only 1 consolidated event is emitted per completed vehicle track.
- [ ] Cross-camera correlation engine correctly sorts sightings by timestamp `ASC` for a target plate string `GJ01AB1234`.
- [ ] Code committed to `feature/prajin-tracking` and Pull Request opened to `testing`.

---

### 23. Git Workflow
```bash
# 1. Work exclusively on your feature branch
git checkout feature/prajin-tracking

# 2. Add implementation files as you build
git add ai/tracking/

# 3. Commit changes
git commit -m "feat(tracking): integrate ByteTrack and build cross-camera trajectory engine"

# 4. Push to GitHub
git push origin feature/prajin-tracking

# 5. Open Pull Request on GitHub:
# feature/prajin-tracking  ──►  testing (Central Integration Branch)
# NEVER push directly to main!
```

---

### 24. What Must Be Demonstrated Before PR
1. ByteTrack maintaining persistent track IDs across 100 continuous frames.
2. Deduplication engine suppressing duplicate detections, emitting 1 clean event payload.
3. Trajectory builder sorting 4 simulated sightings from 4 different cameras into chronological order.

---

### 25. Shared Technical Reference
For central system specifications, hybrid architecture decisions, and database schemas, refer to the integration blueprints on `testing`:
- `docs/ARCHITECTURE.md`
- `docs/API_CONTRACTS.md`
- `docs/TESTING.md`

---

### 26. Final Workspace Rule
This branch starts with **ONLY** `DEVELOPER_README.md`. As developer Prajin, you will create the `ai/tracking/` directory and implementation files as you code. Do NOT commit unnecessary root scaffold files.
