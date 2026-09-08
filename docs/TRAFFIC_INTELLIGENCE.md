# Traffic Intelligence (Phase 14 §4, §5)

Volume, flow, trend, congestion and GIS density — **entirely from SQL
aggregates over the existing `vehicle_events` / `alerts` / `anomaly_events`
/ `incidents`.** Video is never re-processed. An empty database returns
zeros / empty lists; nothing is estimated or mocked.

---

## 1. `TrafficAnalyticsService`

| Method | Returns |
| :--- | :--- |
| `overview(filters, default_hours)` | total vehicles, readable/unknown split, distinct plates, active cameras, `vehicles_per_hour`, `peak_hour`, `trend` (vs the immediately-preceding equal window) + `trend_pct`, `congestion`, vehicle-type distribution, top cameras |
| `by_camera(...)` | per-camera: total, readable, `vehicles_per_hour`, `busiest_hour`, `congestion` |
| `trends(..., bucket="hour"\|"day")` | time series `[{bucket, total, readable}]` + `mean_per_bucket`, `max_bucket` |
| `heatmap(filters, kind)` | per-camera density points — **geolocated cameras only** |

### Filters (all optional)

`date_from` / `date_to` (override the window), `camera_codes[]`,
`vehicle_type`, `zone` — `zone` is matched case-insensitively against the
camera `name` / `location_desc` (no zone table, no migration).

### Congestion

Derived from the **busiest camera's hourly rate**:

| rate (veh/h) | congestion |
| :--- | :--- |
| ≥ `TRAFFIC_CONGESTION_HIGH_PER_HOUR` (120) | `HIGH` |
| ≥ `TRAFFIC_CONGESTION_MODERATE_PER_HOUR` (40) | `MODERATE` |
| > 0 | `LOW` |
| 0 | `NONE` |

### Trend

`total` this window vs `total` in the immediately-preceding window of the
same length: `> +10%` → `up`, `< −10%` → `down`, else `flat`.
`trend_pct` is `None` when the previous window was empty.

## 2. Heatmap (§5)

`kind ∈ { vehicle_density, alert_density, anomaly_density,
incident_density }`. Each point is a **real camera** with `latitude` /
`longitude` from PostGIS, a `count` for the window, and a `weight`
(`count / max_count`, 0–1) for rendering intensity.

> **Only geolocated cameras contribute — no coordinates are ever
> fabricated.** Cameras with a NULL `location` are omitted; the response
> reports `geolocated_cameras` and `contributing_cameras`.

## 3. API (`/api/v1/analytics/traffic/*`, JWT-authenticated, read-only)

| Endpoint | Query params |
| :--- | :--- |
| `GET /overview` | `window_hours` (≤ 90 d), `date_from`, `date_to`, `camera_code` (repeatable), `vehicle_type`, `zone` |
| `GET /cameras` | same |
| `GET /trends` | same + `bucket=hour\|day` |
| `GET /heatmap` | same + `kind=...` |

## 4. Frontend — `/traffic`

`TrafficIntelligencePage.jsx`: KPI row (vehicles, per-hour, peak hour,
trend, congestion, active cameras) · vehicle-type + top-camera bar lists ·
hourly/daily trend bars · a Leaflet **density heatmap** (weighted
`CircleMarker`s over the existing dark GIS basemap, kind switch) ·
per-camera breakdown table. Window (6h/24h/7d/30d) + vehicle-type + zone
filters. Reachable from the `Traffic` nav tab.

## 5. Config

`TRAFFIC_TOPN` (10), `TRAFFIC_CONGESTION_MODERATE_PER_HOUR` (40),
`TRAFFIC_CONGESTION_HIGH_PER_HOUR` (120).

## 6. Tests

`backend/tests/test_traffic.py` (10): window bounding, camera/type/zone
filters, trend-vs-previous-window, per-camera breakdown + busiest hour,
trend buckets, heatmap geolocated-only + weights, all four heatmap kinds,
endpoints, auth 401.

## 7. Limitations

- Congestion thresholds are global constants, not per-camera calibrated
  capacities.
- `direction` of travel is not derived (the current pipeline emits no
  lane/heading); it would come from ByteTrack trajectory sign — see
  `BEHAVIOR_ANALYTICS.md` (wrong-way detector uses the same trajectory
  data).
- Heatmap intensity is per-camera point weight, not an interpolated
  raster surface.
