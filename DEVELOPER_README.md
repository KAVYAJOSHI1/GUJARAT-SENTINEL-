# DEVELOPER EXECUTION GUIDE — VISHAKHA

## 1. Developer Details
- **Developer Name**: Vishakha
- **Role**: GIS Mapping & Vehicle Investigation Console Engineer
- **Git Branch**: `feature/vishakha-investigation`

---

## 2. Mission
Vishakha is responsible for building the GIS mapping interface and the Hero Feature Vehicle Investigation console (`/investigation`). Officers use this console to query vehicle registration numbers (`GJ01AB1234`), visualize chronological movement trajectories across Gujarat camera junctions, view high-res evidence snapshots, and export PDF/CSV investigative reports.

---

## 3. Exact Features Owned
- **Interactive GIS Map (`/map`)**: Leaflet map component with dark-mode tiles, PostGIS camera markers, department filters, and alert overlays.
- **Vehicle Search Console (`/investigation`)**: Search plate input, date range filters, first-seen/last-seen metrics, and total sighting counters.
- **Chronological Movement Timeline**: Sighting cards sorted sequentially by timestamp.
- **Route Trajectory Renderer**: Leaflet polyline vector layer with direction arrows connecting camera coordinates in sequence.
- **Evidence Viewer Modal**: Modal window displaying snapshot image, cropped plate image, camera name, and confidence score.
- **PDF/CSV Report Exporter**: Button generating client-side downloadable PDF vehicle history reports.

---

## 4. Files You Should Work On
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

## 5. Technologies
- **Map Library**: Leaflet.js / React-Leaflet (`react-leaflet`)
- **Tile Provider**: CartoDB Dark Matter tiles
- **Report Generation**: jsPDF (`jspdf`) / HTML2Canvas
- **Framework**: React.js

---

## 6. Input
- **GeoJSON Camera Collection**: `GET /api/v1/cameras/geojson`
- **Vehicle History Search API**: `GET /api/v1/vehicles/search?plate={plate_number}`
- **Evidence Snapshot API**: `GET /api/v1/vehicles/evidence/{event_id}`

---

## 7. Processing Pipeline
```text
1. User enters plate "GJ01AB1234" in Investigation Console
2. Fetch GET /api/v1/vehicles/search?plate=GJ01AB1234
3. Parse JSON Response ──► Extract Sightings Array & PostGIS Lat/Long Coordinates
4. Render SightingTimeline.jsx Cards sorted by Timestamp ASC
5. Render Leaflet Polyline connecting Camera Coordinates with Direction Arrows
6. Click Sighting Card ──► Open EvidenceModal.jsx displaying Snapshot & Crop
7. Click Export Report ──► Invoke jsPDF ReportExporter.js ──► Download PDF File
```

---

## 8. Output
- Interactive GIS map with camera pins and animated polyline trajectory vectors.
- Searchable investigation timeline view.
- Downloadable PDF/CSV investigative reports.

---

## 9. API Contract Reference
All API calls must strictly adhere to **`docs/API_CONTRACTS.md`**:
- **Vehicle History Schema**: `docs/API_CONTRACTS.md#4-vehicle-history-response-schema`
- **Camera Schema**: `docs/API_CONTRACTS.md#1-camera-object-schema`

---

## 10. Integration Dependencies
- **Upstream Providers**:
  - **Vanshal (`feature/vanshal-backend`)**: Provides PostGIS GeoJSON endpoints and vehicle search trajectory API (`/api/v1/vehicles/search`).
  - **Prajin (`feature/prajin-tracking`)**: Supplies cross-camera trajectory data structures.
- **Downstream Consumers**:
  - **Isha (`feature/isha-frontend`)**: Embeds GIS map component and investigation link inside main command dashboard.

---

## 11. Testing Requirements
- Test Leaflet map rendering with 50+ camera pins.
- Test route polyline vector rendering with out-of-order timestamps to verify correct spatial connection.
- Test PDF generation service to ensure clean layout without text truncation.

---

## 12. Definition of Done (DoD)
- [ ] GIS map displays camera pins fetched from backend PostGIS GeoJSON.
- [ ] Searching `GJ01AB1234` renders sequential camera pins connected by polyline arrows.
- [ ] Clicking a sighting card opens evidence modal displaying snapshot image and plate crop.
- [ ] Client-side PDF exporter generates a clean vehicle history summary report.
- [ ] Code committed to `feature/vishakha-investigation` and Pull Request opened to `testing`.

---

## 13. Git Branching Instructions
```bash
# 1. Work exclusively on your feature branch
git checkout feature/vishakha-investigation

# 2. Commit changes
git add .
git commit -m "feat(gis): build vehicle investigation console and trajectory route map"

# 3. Push to GitHub
git push origin feature/vishakha-investigation

# 4. Open Pull Request on GitHub:
# feature/vishakha-investigation  ──►  testing (Central Integration Branch)
# NEVER push directly to main!
```
