# Behaviour Analytics (Phase 12 §4 + Phase 14 §6)

`BehaviorAnalyticsService` — **three** AI-assisted anomaly detectors, all
running on stored ByteTrack `vehicle_events` only. **Video is never
re-processed.** Every detection is written to `anomaly_events` **and**
pushed through the existing `Alert(source=ANOMALY)` →
notification → incident workflow — no parallel mechanism.

| Detector | `AnomalyKind` | Trigger |
| :--- | :--- | :--- |
| Stopped / loitering vehicle | `STOPPED_VEHICLE` | a track dwells at one camera ≥ `ANOMALY_STOPPED_MIN_SECONDS`, ≥ `MIN_DETECTIONS` detections, ≤ `MAX_DISPLACEMENT_M` movement |
| Wrong-way movement | `WRONG_WAY` | a track's net heading is ≥ `ANOMALY_WRONGWAY_MIN_ANGLE_DEG` off the camera's `permitted_direction_deg`, over ≥ `MIN_DISTANCE_M` and ≥ `MIN_DETECTIONS` geolocated sightings |
| Restricted-zone entry | `RESTRICTED_ZONE` | ≥ `ANOMALY_ZONE_MIN_INSIDE` of a track's geolocated sightings fall inside a camera `restricted_zones` polygon |

> Every anomaly is an **AI inference**, not a confirmed offence. Each row
> carries a `confidence_score` / `confidence_level` and a plain-language
> `reasoning`; the UI labels them `AI-GENERATED`.

---

## 1. Camera configuration (Phase 14 §6)

Two nullable columns on `cameras` (migration `0011`), both **NULL by
default** → the new detectors are inert until a camera is configured:

| Column | Meaning |
| :--- | :--- |
| `permitted_direction_deg` | compass bearing (0 = N, 90 = E) traffic is allowed to flow |
| `restricted_zones` | `[{ "name": str, "points": [[lat, lon], …] }]` — polygon rings |

Set via `PATCH /api/v1/cameras/{id}/behavior-config` (ADMIN/OFFICER,
audited `CAMERA_BEHAVIOR_CONFIG`). **Does not touch RTSP / credentials /
status.**

## 2. Geometry (pure Python — `app/services/geo.py`)

- `bearing_deg(lat1, lon1, lat2, lon2)` — initial great-circle bearing.
- `angular_diff_deg(a, b)` — smallest bearing difference, 0–180.
- `point_in_polygon(lat, lon, ring)` — ray-casting, no shapely.

Wrong-way uses the track's **first → last** geolocated sighting bearing vs
`permitted_direction_deg`. Restricted-zone tests **each** sighting against
each polygon.

## 3. Confidence

- `wrong_way_confidence(angle_diff, net_distance_m, count, min_distance_m)`
  — rises with angular opposition (0 at 90°, 1 at 180°), net travel, and
  detection count.
- `restricted_zone_confidence(inside_count, total_count, dwell_seconds)` —
  rises with the fraction of sightings inside and the dwell.

## 4. Idempotency

The `anomaly_events` unique index is now
`(camera_id, track_id, first_seen, kind)` — so one track can be **both** a
`STOPPED_VEHICLE` **and** a `RESTRICTED_ZONE` (e.g. parked inside a
plaza) without collision. A re-scan of the same window never
double-flags.

## 5. Running the detectors

- **Background**: `_anomaly_scan_loop` (`AI_ANOMALY_SCAN_INTERVAL_S`,
  default 300 s) now calls `BehaviorAnalyticsService.scan()` — all three
  detectors. Off in the test suite.
- **On demand**: `POST /api/v1/ai/anomalies/scan` (ADMIN/OFFICER) accepts
  `kinds: ["WRONG_WAY", …]` (omit / `[]` = all), `lookback_hours`,
  `camera_code`. Audited `AI_ANOMALY_SCAN`.
- **List**: `GET /api/v1/ai/anomalies` — `AnomalyEventRead` now carries
  `zone_name`, `direction_deg`, `expected_direction_deg`.

## 6. Frontend

`/anomalies` (`AnomaliesPage.jsx`) shows a per-kind coloured label
(`STOPPED VEHICLE` / `WRONG-WAY MOVEMENT` / `RESTRICTED-ZONE ENTRY`), an
`AI-GENERATED` chip, a kind-specific detail line (heading vs permitted;
zone name + dwell; hold time), the confidence badge, and the existing
"View alert" / "Trace vehicle" / review actions.

## 7. Offline demo

`seed_ai_demo.py` configures `CAM-02` with `permitted_direction_deg = 45°`
and seeds a black car (`GJ05WW1201`) driving SW into it → `WRONG_WAY`;
configures `CAM-06` with a "pedestrian plaza" polygon and seeds an
auto-rickshaw (`GJ01RZ7788`) driving through it → `RESTRICTED_ZONE`; plus
the existing `CAM-04` stopped vehicle. All via the real detector +
alert workflow.

## 8. Tests

`backend/tests/test_behavior_expanded.py` (12) + `test_ai_behavior.py` (4):
wrong-way positive / correct-direction / short-distance / no-config /
idempotent; restricted-zone positive / outside / single-touch;
scan-runs-all-3; stopped+zone same track no collision; stopped still works;
scan endpoint `kinds` filter; behaviour-config endpoint + RBAC.

## 9. Limitations

- Heading is derived from GPS-per-event start/end; a real U-turn or a
  reversing manoeuvre can look like wrong-way (mitigated by the angle +
  distance + detection thresholds and the explicit confidence).
- Polygons are lat/lon rings, not projected — fine at city scale, not for
  sub-metre precision.
- Wrong-way needs a per-camera `permitted_direction_deg`; the current
  pipeline emits no lane geometry, so this is operator-configured.
