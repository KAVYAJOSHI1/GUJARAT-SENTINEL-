# SENTINEL — GIS Mapping & Vehicle Investigation Engine

---

## 1. GIS Mapping Subsystem

The GIS Subsystem renders interactive spatial layers using **Leaflet.js** over CartoDB Dark Matter tiles:
- **Camera Pins**: PostGIS point features (`cameras.location`) rendered as interactive status markers.
- **Trajectory Polylines**: Leaflet vector layer connecting camera coordinates in chronological order of appearance with direction arrow overlays.

---

## 2. Vehicle Investigation Console (`/investigation`)

- **Plate Search Input**: Officers query registration strings (e.g. `GJ01AB1234`).
- **Vehicle Profile Card**: Displays First Seen, Last Seen, Total Sightings, Camera Count, and Watchlist Status.
- **Sighting Timeline**: Chronological vertical timeline card sequence.
- **Evidence Modal**: Displays full frame snapshot and cropped plate image.
- **PDF Report Exporter**: Generates downloadable PDF vehicle history report (`GJ01AB1234_Report.pdf`).
