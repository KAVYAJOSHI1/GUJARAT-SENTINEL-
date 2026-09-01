# Team Specification — VISHAKHA

## 1. Developer Profile & Module Ownership
- **Member Name**: Vishakha
- **Module Ownership**: GIS Map + Vehicle Investigation + Movement Reports
- **Git Branch**: `feature/vishakha-investigation`

---

## 2. Core Responsibilities
- Implement the interactive GIS mapping module using Leaflet or OpenLayers.
- Build the **Hero Feature Vehicle Search & Investigation Console**: plate query, chronological timeline, spatial movement vector route, and snapshot evidence modal.
- Build exportable Vehicle Movement PDF/CSV reports for law enforcement officers.
- Integrate PostGIS geospatial camera coordinates and vehicle detection trajectories from Vanshal's backend.

---

## 3. UI Screens & Features to Implement
1. **Interactive GIS Map (`/map`)**: Full-screen interactive map displaying camera pin markers, online/offline color coding, and department filtering.
2. **Vehicle Search & Timeline (`/investigation`)**: Target plate input (e.g. `GJ01AB1234`), chronological card list of sightings, first-seen/last-seen metrics.
3. **Route Visualizer**: Animated or polyline vector path drawn between sequential camera sightings on the map.
4. **Evidence Viewer Modal**: High-resolution popup displaying full vehicle snapshot, license plate crop, and AI confidence telemetry.
5. **Report Exporter**: Downloadable summary report of vehicle journey and detection history.

---

## 4. Technology Stack
- **Map Library**: Leaflet.js / React-Leaflet or OpenLayers
- **Tile Provider**: OpenStreetMap / CartoDB Dark Matter tiles
- **Report Generation**: jsPDF / HTML2Canvas
- **Frontend Framework**: React.js

---

## 5. Interface & Data Contracts

### 5.1 APIs Consumed
- `GET /api/v1/cameras/geojson`: PostGIS GeoJSON feature collection of all cameras.
- `GET /api/v1/vehicles/search?plate={plate_number}`: Vehicle movement route array, camera timestamps, lat/long, and snapshot URLs.
- `GET /api/v1/vehicles/evidence/{event_id}`: High-res snapshot and metadata.

### 5.2 Inputs & Outputs
- **Input**: Plate search string, date range filters.
- **Output**: Rendered polyline route on map, chronological list cards, exported PDF reports.

---

## 6. Development Priorities
1. **Day 1**: Leaflet map integration with dark tiles and mock camera markers.
2. **Day 2**: Vehicle Investigation Search view & chronological timeline component.
3. **Day 3**: Draw connected trajectory lines (polylines) on map for search results.
4. **Day 4**: Evidence image modal, report generation, and full integration with `testing`.

---

## 7. Definition of Done (DoD) & Testing Requirements
- [ ] GIS map correctly renders camera locations from backend GeoJSON.
- [ ] Searching a vehicle registration number (e.g. `GJ01AB1234`) displays sequential camera pins with numbered markers.
- [ ] Clicking a camera pin opens a popup showing timestamp, plate crop, and confidence.
- [ ] Route polylines accurately connect chronological camera coordinates.
- [ ] Code committed to `feature/vishakha-investigation` and tested against `testing` branch.

---

## 8. Inter-Member Dependencies
- **Vanshal**: Requires backend search API (`/api/v1/vehicles/search`) and PostGIS GeoJSON endpoint.
- **Prajin**: Relies on Prajin's cross-camera correlation engine for accurate timestamp sequences.
