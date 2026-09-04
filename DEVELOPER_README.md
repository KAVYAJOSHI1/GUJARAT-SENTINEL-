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

---

### 10. Mock Cameras (Local Dev / Demo Source)

**What this is.** `trafficdataset/` (git-ignored, ~1.7GB, not committed) holds
a downloaded set of real Anand, Gujarat traffic clips (`Videos/Videos/video1.MOV`
… `video104.MOV`, 1920x1080 H.264 @ 30fps, 5-11s each) donated by the user for
demoing this system at scale without depending on the real Sentinel RTSP feed
or venue internet. **These are LOCAL MOCK CAMERAS, not a live government
feed** — the dashboard always shows them behind a visible `MOCK` badge (never
alongside cam04/cam06 unlabelled). They are a *pure addition*: nothing about
the real cam01-cam30 registry, RTSP credentials, or ingestion behavior
changes because this exists.

**How it works, architecturally.** A mock camera is exactly a `CameraRecord`
whose `stream_url` is a local file path instead of an `rtsp://` URL. That's
the entire trick — `ingestion/stream_manager.py`'s `StreamWorker` already
opens any URL via `cv2.VideoCapture(url, cv2.CAP_FFMPEG)`, and a local path
opens the exact same way an RTSP URL does. The only new behavior, gated by
`_is_local_source()` (true only for non-`rtsp://`/`http(s)://` sources, so it
never touches a real camera):
  - **Real-time pacing** — frames are throttled to the source clip's own fps
    (or `--fps` override) so playback runs at wall-clock speed, not "as fast
    as the decoder can go".
  - **Clean EOF looping** — end-of-clip reopens the file and continues from
    frame 0, like a continuous live feed, without going through the
    RTSP reconnect/backoff ladder (no `RECONNECTING` flicker). The loop
    resets `seq_num`, which is what makes the *existing*
    `FrameConsumer._check_reconnect()` discontinuity check reset that
    camera's ByteTrack tracker automatically on every loop boundary — no new
    pipeline code was needed for that.

Every mock-camera frame goes through the identical
`StreamManager → FrameConsumer → AIPipeline (YOLO → ByteTrack → OCR) → POST
/api/v1/events/ai-detection → PostgreSQL → dashboard/GIS` chain real cameras
use. Detections, track IDs, and plates are real — a mock camera never
fabricates an event. The Anand clips are wide dashcam-angle footage, so
plates usually come back `UNKNOWN`, exactly like the real overhead junction
cameras — that is the correct, honest result, not a bug.

**Setup.**
```bash
# one-time (or again after adding new videos): scan trafficdataset/ and
# write data/trafficdataset_camera_registry.json (git-ignored — embeds local
# absolute paths, same reason data/mock_camera_registry.json is ignored)
.venv/bin/python scripts/generate_mock_camera_registry.py --count 3
```
Each selected clip becomes one `MOCK_CAM0N` entry at a distinct demo location
around Anand ("Anand Traffic Junction – Mock Camera 0N"), with the same
entry shape (`camera_id`, `name`, `rtsp_url`, `latitude`, `longitude`,
`status`, …) the real registry already uses — no new loader code. `--count`
defaults to 3; the dataset has 104 usable clips, but registering 104 fake
cameras would misrepresent the demo, so the number is always explicit and
small. `--videos video7.MOV,video12.MOV` picks specific clips instead.

**Running.**
```bash
# every configured mock camera
.venv/bin/python scripts/run_mock_cameras.py

# specific ones, adjust pacing/looping
.venv/bin/python scripts/run_mock_cameras.py --cameras MOCK_CAM01,MOCK_CAM02 --fps 15
.venv/bin/python scripts/run_mock_cameras.py --no-loop --duration 30

# REAL cam04/cam06 + MOCK cameras together, in ONE process (see below)
.venv/bin/python scripts/run_mock_cameras.py --with-real cam04,cam06
```
`scripts/run_mock_cameras.py` is a thin wrapper around the existing
`scripts/run_pipeline_service.py::PipelineService` — it does not run a second
AI pipeline. `--registry` also accepts a comma-separated list of registry
files directly if you'd rather drive it from `run_pipeline_service.py`:
```bash
.venv/bin/python scripts/run_pipeline_service.py \
  --registry data/camera_registry.json,data/trafficdataset_camera_registry.json \
  --cameras cam04,cam06,MOCK_CAM01,MOCK_CAM02
```

**Why one process for real+mock.** Two separate Python processes each
loading their own `AIPipeline` (YOLO/torch/OpenCV) have been observed to
crash into each other at interpreter shutdown on this machine (results still
deliver fine beforehand — only teardown is affected). Running real and mock
cameras as more `StreamWorker`s inside the *same* process/`AIPipeline`
sidesteps that entirely, and is the supported way to demo both together.

**Adding another video / mapping a video to a camera.** Drop additional
clips into `trafficdataset/Videos/Videos/` (or point `--videos-dir`
elsewhere) and re-run `generate_mock_camera_registry.py`, or hand-edit the
generated JSON — `source_video` / `rtsp_url` is the only field that actually
selects the clip a `MOCK_CAM0N` plays.

**REAL vs MOCK, everywhere.** No backend schema change was made for this —
`MOCK_CAM0N` is a naming convention (like `cam04` already is), not a new
field. The dashboard derives the `MOCK` badge and REAL/MOCK counts purely
from the camera `code` prefix (`frontend/src/services/api.js::isMockCamera`),
so a real Sentinel camera is never mislabeled and nothing changes for a
mock-camera-free run.

**In-dashboard playback.** Unlike real Sentinel RTSP feeds (Basic-auth,
no CORS HLS — genuinely can't be embedded), a mock camera *is* just a local
file, so `CameraCard.jsx` plays it directly via `GET
/api/v1/cameras/{id}/mock-video`. The source `.MOV` clips are a QuickTime
container most browsers won't decode in `<video>` even though the H.264
codec inside is standard, so `generate_mock_camera_registry.py` also
losslessly remuxes each selected clip into a real H.264-in-MP4 file
(`trafficdataset/_previews/<code>.mp4`, via the optional `av` dependency —
no re-encode, pixels untouched) that the backend prefers whenever present,
falling back to the raw `.MOV` otherwise.

Never commit `trafficdataset/` or `data/trafficdataset_camera_registry.json`
(both git-ignored) — no credentials live in either.

---

<!-- ===== Merged from feature/vishakha-investigation ===== -->

# DEVELOPER EXECUTION GUIDE — VISHAKHA

---

### 1. Developer Details
- **Developer Name**: Vishakha
- **Role**: GIS Mapping & Vehicle Investigation Console Engineer
- **Git Branch**: `feature/vishakha-investigation`

---

### 2. Project Objective
Build the GIS Mapping and Hero Feature Vehicle Investigation console (`/investigation`) for the **SENTINEL** platform. Enable law enforcement officers to enter a target registration plate (e.g. `GJ01AB1234`), render its chronological trajectory across Gujarat CCTV junctions on a map, view snapshot evidence, and generate downloadable PDF investigation reports.

---

### 3. Exact Responsibility
You own the GIS mapping components (`frontend/src/components/gis/`) and the vehicle investigation screen (`frontend/src/pages/InvestigationPage.jsx`). You are responsible for Leaflet map integration, dark-mode tile rendering, camera marker placement, chronological sighting timeline cards, polyline trajectory vector mapping with direction arrows, evidence snapshot viewer modals, search filters, and client-side PDF/CSV report generation.

---

### 4. Exact Features to Build
1. **Interactive GIS Map (`/map`)**: Leaflet map component rendering CartoDB dark tiles, PostGIS camera pins, alert overlays, and zoom controls.
2. **Vehicle Search Console (`/investigation`)**: Search input box supporting plate string lookups (`GJ01AB1234`), date range filters, and sighting metric summaries.
3. **Vehicle Profile Summary Card**: Display First Seen, Last Seen, Total Sightings, Camera Count, and Alert Trigger counters for queried plate string.
4. **Chronological Movement Timeline**: Vertical timeline component listing camera sightings sorted sequentially by timestamp (`ASC`).
5. **Route Trajectory Vector Overlay**: Leaflet polyline layer connecting camera coordinates in order of appearance with directional arrows.
6. **Evidence Viewer Modal**: Modal window displaying high-res snapshot image, cropped plate image, camera metadata, and OCR confidence.
7. **Client-Side PDF/CSV Exporter**: Export button invoking jsPDF to compile a structured vehicle movement report.

---

### 5. What NOT to Build
- Do NOT build main command dashboard stat widgets or navigation header (owned by Isha).
- Do NOT build AI inference models, YOLO detection, or OCR (owned by Kavya).
- Do NOT build multi-object tracking algorithms or Re-ID (owned by Prajin).
- Do NOT build RTSP video ingestion workers or stream decoders (owned by Rishit).
- Do NOT build database migrations or SQL tables (owned by Vanshal).

---

### 6. Technologies
- **Core Stack**: React 18+ (bootstrapped with Vite)
- **Map Engine**: Leaflet.js / React-Leaflet (`react-leaflet`, `leaflet`)
- **Map Tiles**: CartoDB Dark Matter tiles (`https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png`)
- **Report Generation**: jsPDF (`jspdf`) & HTML2Canvas

---

### 7. Recommended Models / Libraries
- `leaflet` & `react-leaflet`
- `leaflet-polylinedecorator` (for route direction arrows)
- `jspdf`
- `lucide-react`

---

### 8. Input
- **GeoJSON Camera Inventory Endpoint**: `GET /api/v1/cameras/geojson`
- **Vehicle History Search API**: `GET /api/v1/vehicles/search?plate={plate_number}`
- **Evidence Snapshot File API**: `GET /api/v1/vehicles/evidence/{event_id}`

---

### 9. Processing Pipeline
```text
1. User enters plate string "GJ01AB1234" in Investigation Console
2. Fetch GET /api/v1/vehicles/search?plate=GJ01AB1234
3. Parse JSON Response ──► Extract Sightings Array & PostGIS Lat/Long Coordinates
4. Render SightingTimeline.jsx Cards sorted by Timestamp ASC
5. Draw Leaflet Polyline connecting Camera Coordinates with Direction Arrow Overlays
6. Click Sighting Card ──► Open EvidenceModal.jsx displaying Snapshot & Crop
7. Click "Export PDF Report" ──► Invoke jsPDF ReportExporter.js ──► Download PDF File
```

---

### 10. Output
- Interactive Leaflet map with PostGIS camera markers and animated route vectors.
- Searchable vehicle timeline interface.
- Client-side downloadable PDF vehicle history report (`GJ01AB1234_Report.pdf`).

---

### 11. Required API Contract
Must strictly comply with `testing` integration contracts documented in `docs/API_CONTRACTS.md`:
- **Vehicle History Response Schema**: `docs/API_CONTRACTS.md#4-vehicle-history-response-schema`
- **Camera Schema**: `docs/API_CONTRACTS.md#1-camera-object-schema`

---

### 12. Database Interaction
No direct database interaction. Query Vanshal's PostGIS spatial REST APIs for GeoJSON feature collections and vehicle sighting trajectories.

---

### 13. Integration Dependencies
- **Upstream Providers**:
  - **Vanshal (`feature/vanshal-backend`)**: Supplies vehicle search trajectory endpoint (`/api/v1/vehicles/search`) and PostGIS GeoJSON feeds.
  - **Prajin (`feature/prajin-tracking`)**: Supplies cross-camera trajectory data structures.
- **Downstream Consumers**:
  - **Isha (`feature/isha-frontend`)**: Isha's main dashboard camera links route directly into your GIS Map view.

---

### 14. Exact Implementation Steps
1. Create GIS component folder structure (`frontend/src/components/gis/`).
2. Install `leaflet`, `react-leaflet`, `jspdf`.
3. Create `GisMap.jsx` initializing Leaflet map container with CartoDB dark tiles centered on Gujarat (Lat `23.0225`, Long `72.5714`).
4. Build `CameraMarker.jsx` displaying camera status markers.
5. Create `InvestigationPage.jsx` with search bar and vehicle profile summary card.
6. Create `SightingTimeline.jsx` rendering chronological sighting cards.
7. Create `RoutePolyline.jsx` connecting camera coordinates in timestamp order.
8. Create `EvidenceModal.jsx` displaying full snapshot and cropped plate image.
9. Implement `ReportExporter.js` generating PDF reports.

---

### 15. Error Handling
- **Plate Not Found**: Render empty state card "No recorded sightings found for plate GJ01AB1234".
- **Invalid Plate Format**: Show validation alert "Please enter a valid registration number (e.g. GJ01AB1234)".
- **Missing Snapshot Image**: Display placeholder image "Evidence snapshot unavailable".

---

### 16. Testing Requirements
- Test Leaflet map rendering with 50+ camera pins without UI lag.
- Test route polyline vector rendering with out-of-order timestamps to verify correct spatial connection.
- Test PDF generation service to ensure clean layout without text truncation.

---

### 17. Performance Requirements
- Map initial render time $< 1.0$ second.
- Trajectory polyline rendering $< 100$ ms for 20+ camera sightings.
- Client-side PDF generation $< 2.0$ seconds.

---

### 18. Day 1 Tasks
Setup Leaflet map component with CartoDB dark tiles, add Gujarat coordinates, render static camera pins from mock GeoJSON data.

---

### 19. Day 2 Tasks
Build `InvestigationPage` search interface, connect to backend `/api/v1/vehicles/search?plate=GJ01AB1234`, render vehicle profile summary card.

---

### 20. Day 3 Tasks
Build `SightingTimeline` and `RoutePolyline` components, render vector polyline connecting camera pins with direction arrows.

---

### 21. Day 4 Tasks
Build `EvidenceModal` snapshot viewer, build `ReportExporter.js` for PDF generation, run integration tests, and optimize map performance.

---

### 22. Definition of Done (DoD)
- [ ] GIS map accurately renders PostGIS camera markers on dark tiles.
- [ ] Searching `GJ01AB1234` renders sequential camera pins connected by polyline vector arrows.
- [ ] Timeline cards list sightings chronologically (`ASC`).
- [ ] Clicking a sighting card opens evidence modal displaying snapshot image and plate crop.
- [ ] PDF report exporter generates a clean vehicle history summary file.
- [ ] Code committed to `feature/vishakha-investigation` and Pull Request opened to `testing`.

---

### 23. Git Workflow
```bash
# 1. Work exclusively on your feature branch
git checkout feature/vishakha-investigation

# 2. Add implementation files as you build
git add frontend/src/components/gis/

# 3. Commit changes
git commit -m "feat(gis): implement Leaflet route polyline and investigation search console"

# 4. Push to GitHub
git push origin feature/vishakha-investigation

# 5. Open Pull Request on GitHub:
# feature/vishakha-investigation  ──►  testing (Central Integration Branch)
# NEVER push directly to main!
```

---

### 24. What Must Be Demonstrated Before PR
1. GIS map displaying 50 camera pins with dark tiles.
2. Vehicle search for `GJ01AB1234` displaying vehicle profile summary card.
3. Polyline route vector on map connecting 4 sequential camera sightings with arrows.
4. Downloadable PDF report generated upon clicking "Export PDF".

---

### 25. Shared Technical Reference
For central system specifications, hybrid architecture decisions, and database schemas, refer to the integration blueprints on `testing`:
- `docs/ARCHITECTURE.md`
- `docs/API_CONTRACTS.md`
- `docs/TESTING.md`

---

### 26. Final Workspace Rule
This branch starts with **ONLY** `DEVELOPER_README.md`. As developer Vishakha, you will create the GIS implementation files inside `frontend/src/` as you code. Do NOT commit unnecessary root scaffold files.


<!-- ===== Merged from feature/prajin-tracking ===== -->

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
