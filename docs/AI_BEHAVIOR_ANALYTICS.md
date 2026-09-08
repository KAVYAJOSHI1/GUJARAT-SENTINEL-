# AI Behaviour Analytics — Stopped / Loitering Vehicle

One detector this phase (per the brief). **AI-assisted anomaly detection**,
not "behavioural AI" — it is a deterministic rule over stored ByteTrack
tracks. `app/services/ai/behavior.py :: BehaviorAnalyticsService`.

## Logic

```
for each (camera_id, track_id) with detections in the last ANOMALY_LOOKBACK_HOURS:
    count      = number of vehicle_events on that track
    duration_s = max(timestamp) - min(timestamp)
    displacement_m = haversine(bounding box of the track's lat/lon)   # if GPS present

    STOPPED  ⟺  count ≥ ANOMALY_STOPPED_MIN_DETECTIONS (6)
           AND  duration_s ≥ ANOMALY_STOPPED_MIN_SECONDS (120)
           AND  (displacement_m ≤ ANOMALY_STOPPED_MAX_DISPLACEMENT_M (25)  OR  no GPS)
```

Never re-processes video — a single grouped aggregate over `vehicle_events`.

## Output

An `anomaly_events` row:

| field | source |
| :--- | :--- |
| `kind` | `STOPPED_VEHICLE` |
| `camera_id` / `camera_code` / `plate_number_normalized` / `track_id` | the track |
| `first_seen` / `last_seen` / `duration_seconds` / `detection_count` | aggregate |
| `displacement_meters` | haversine (or `null` if no per-event GPS) |
| `confidence_score` / `confidence_level` | `confidence.anomaly_confidence()` |
| `reasoning` | e.g. *"AI-assisted anomaly detection: track held at one camera for 210s across 14 detections; max displacement 12 m"* |
| `evidence_event_id` | first sighting of the track |
| `alert_id` | the alert it generated |
| `status` | `NEW` → `REVIEWED` / `DISMISSED` |

## Feeds the EXISTING alert architecture (not a parallel one)

Each anomaly creates an `Alert` with:

* `source = ANOMALY` (new enum value; the watchlist engine still only ever
  writes `WATCHLIST`)
* `watchlist_id = NULL` (made nullable in migration `0008`)
* `anomaly_event_id` → the anomaly row
* `priority_level = ANOMALY_PRIORITY` (default `MEDIUM`)

So an anomaly alert is acknowledged, assigned, **escalated** and **promoted
to an incident** with the exact Phase-10/11 workflow. It also raises an
`ANOMALY_STOPPED_VEHICLE` notification and a WS `type:"ALERT", source:"ANOMALY"`
frame.

## Idempotency

Unique index `(camera_id, track_id, first_seen)` + a pre-check ⇒ a re-scan
returns `already_flagged`, never a duplicate.

## Triggers

* **Periodic** — `_anomaly_scan_loop` in `app/main.py`, every
  `AI_ANOMALY_SCAN_INTERVAL_S` (300 s). Off in the test suite
  (`AI_ANOMALY_SCAN_ENABLED=false`). When government feeds resume, new
  events flow through the unchanged ingest and the next tick picks them up.
* **Manual** — `POST /api/v1/ai/anomalies/scan` (ADMIN/OFFICER),
  `{ "lookback_hours": 24, "camera_code": "CAM-04" }` (both optional).

## API

| endpoint | role | notes |
| :--- | :--- | :--- |
| `GET /api/v1/ai/anomalies` | any auth | list, filter by `status` / `camera_code`, paginated |
| `POST /api/v1/ai/anomalies/scan` | ADMIN/OFFICER | run the detector, audited `AI_ANOMALY_SCAN` |
| `POST /api/v1/ai/anomalies/{id}/review` | ADMIN/OFFICER | `{ "status": "REVIEWED" \| "DISMISSED" }`, audited `AI_ANOMALY_REVIEW` |

## Frontend

`/anomalies` — list with the confidence chip, duration / detection count /
displacement, the linked alert, "Trace vehicle", and (for ADMIN/OFFICER)
Run scan / Mark reviewed / Dismiss. Also on the command centre as the
"AI Anomaly Events" panel.

## Tests

`tests/test_ai_behavior.py`: stopped track flagged + ANOMALY alert +
notification; moving track **not** flagged; short dwell **not** flagged;
re-scan idempotent; scan RBAC; review + audit.
