# Implementation Specification — VISHAKHA (GIS + Investigation + Reports)

---

### 1. Ownership
- **Developer Name**: Vishakha
- **Module Ownership**: Interactive GIS Mapping, Vehicle Investigation Console & Movement Reports
- **Git Branch**: `feature/vishakha-investigation`

---

### 2. Objective
Develop the interactive GIS mapping interface and Hero Feature Vehicle Investigation console to allow law enforcement officers to query registration numbers, reconstruct chronological movement journeys, visualize trajectory routes on maps, view snapshot evidence, and generate exportable reports.

---

### 3. Responsibilities
- Integrate Leaflet.js map component with dark tile layers.
- Implement camera pin markers with online/offline status indicators.
- Build the **Vehicle Search Console (`/investigation`)**: plate query input, chronological timeline cards, and evidence viewer modal.
- Render animated or polyline route vectors connecting camera sightings in sequence.
- Build client-side PDF/CSV movement report generation.

---

### 4. Features to Implement
1. **Interactive GIS Map (`/map`)**: Full-screen interactive map displaying PostGIS camera pins, department layer filters, and alert markers.
2. **Vehicle Search Console (`/investigation`)**: Search plate `GJ01AB1234` to fetch chronological sightings, first-seen/last-seen metrics, and total detections.
3. **Route Visualizer**: Polyline vector trajectory drawn on Leaflet map connecting sequential camera pins.
4. **Evidence Snapshot Modal**: Modal view displaying high-res vehicle snapshot, cropped plate image, confidence score, and timestamp.
5. **PDF/CSV Report Exporter**: Button to generate downloadable investigative reports.

---

### 5. Module Architecture
```text
React App (App.jsx)
 └── Investigation & GIS Module
      ├── Interactive Map View (GisMap.jsx)
      │    ├── Camera Markers Layer (CameraMarker.jsx)
      │    └── Trajectory Polyline Layer (RoutePolyline.jsx)
      ├── Vehicle Search Console (VehicleSearch.jsx)
      │    ├── Search Input & Filters
      │    ├── Chronological Timeline List (SightingTimeline.jsx)
      │    └── Vehicle Summary Card
      ├── Evidence Viewer Modal (EvidenceModal.jsx)
      └── PDF/CSV Report Generator (ReportExporter.js)
```

---

### 6. Technologies
- **Map Library**: Leaflet.js / React-Leaflet
- **Tile Provider**: OpenStreetMap / CartoDB Dark Matter tiles
- **Report Generation**: jsPDF / HTML2Canvas
- **Frontend Framework**: React.js

---

### 7. Folder Structure
```text
frontend/src/
├── components/gis/
│   ├── GisMap.jsx
│   ├── CameraMarker.jsx
│   ├── RoutePolyline.jsx
│   ├── EvidenceModal.jsx
│   └── SightingTimeline.jsx
├── pages/
│   ├── MapPage.jsx
│   └── InvestigationPage.jsx
├── services/
│   ├── gisService.js
│   └── ReportExporter.js
```

---

### 8. Detailed Implementation Tasks
1. Install `leaflet` and `react-leaflet` npm packages.
2. Build `GisMap.jsx` initialized at Gujarat center coordinates (`23.0225, 72.5714`) with zoom level 11.
3. Fetch camera GeoJSON features from `/api/v1/cameras/geojson` and plot custom SVG pin markers.
4. Build `VehicleSearch.jsx` console containing plate text input and date range pickers.
5. Fetch vehicle history from `/api/v1/vehicles/search?plate={plate_number}`.
6. Parse chronological sightings array and draw Leaflet `Polyline` with direction arrows connecting camera coordinates.
7. Build `EvidenceModal.jsx` displaying snapshot image, plate crop image, camera name, and confidence score.
8. Implement `ReportExporter.js` using `jsPDF` to format vehicle history into a formal investigation document.

---

### 9. Input
- Vehicle plate query string (e.g. `GJ01AB1234`).
- PostGIS GeoJSON camera feature collection from backend.
- Vehicle search response JSON containing sightings array.

---

### 10. Output
- Rendered GIS map with camera pins and trajectory vectors.
- Chronological sighting timeline cards.
- Downloadable PDF/CSV investigation reports.

---

### 11. APIs Consumed
- `GET /api/v1/cameras/geojson`: Returns PostGIS GeoJSON feature collection.
- `GET /api/v1/vehicles/search?plate={plate}`: Returns vehicle route, sightings array, first-seen/last-seen metadata.
- `GET /api/v1/vehicles/evidence/{event_id}`: Returns evidence image references.

---

### 12. Database Interaction
Interacts with PostGIS geometry tables indirectly via Vanshal's backend REST APIs.

---

### 13. Dependencies on Other Members
- **Vanshal**: Requires backend search API (`/api/v1/vehicles/search`) and PostGIS GeoJSON endpoint.
- **Prajin**: Relies on Prajin's cross-camera correlation engine for accurate timestamp ordering.

---

### 14. Integration Contract
Must adhere to `docs/API_CONTRACTS.md` Vehicle History Response Schema.

---

### 15. Error Handling & UI States
- **No Sightings Found**: Displays "No vehicle detections found for plate [XYZ]" card.
- **Invalid Plate Format**: Shows input validation error message.
- **Map Tile Load Error**: Fallback to secondary tile provider if CartoDB tiles fail.

---

### 16. Testing Requirements
- Test Leaflet marker rendering with 50+ simultaneous camera coordinates.
- Test route polyline rendering with sequential out-of-order timestamps.

---

### 17. Performance Requirements
- GIS map initial tile render $< 1.0$ second.
- Vehicle route polyline render $< 200$ ms after API response.

---

### 18. Day 1 Plan
Setup Leaflet map component with dark tiles and static test camera markers.

---

### 19. Day 2 Plan
Build Vehicle Search Console UI and chronological timeline list component.

---

### 20. Day 3 Plan
Implement Leaflet polyline route renderer and evidence snapshot modal view.

---

### 21. Day 4 Plan
Implement PDF report exporter, UI polish, and end-to-end testing against `testing` branch.

---

### 22. Definition of Done (DoD)
- [ ] GIS map correctly displays camera pins from backend GeoJSON.
- [ ] Searching `GJ01AB1234` renders sequential camera pins and connects them with polyline arrows.
- [ ] Clicking a camera pin opens popup displaying timestamp, plate crop, and evidence image.
- [ ] PDF report exports clean vehicle history summary.
- [ ] Code committed to `feature/vishakha-investigation` and verified on `testing`.

---

### 23. Deliverables
- GIS mapping and vehicle investigation component source code.
- Client-side report generation service.

---

### 24. What NOT to do
- Do NOT perform raw spatial GIS calculations in JavaScript; rely on PostGIS backend APIs.
- Do NOT load high-resolution map tiles synchronously blocking UI thread.
- Do NOT push directly to `main`.

---

### 25. Merge Checklist
- [ ] GIS map renders smoothly
- [ ] Vehicle search API integration verified
- [ ] PR opened from `feature/vishakha-investigation` to `testing`
