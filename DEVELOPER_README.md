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
