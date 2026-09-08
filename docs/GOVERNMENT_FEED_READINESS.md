# Government-Feed Readiness

Government CCTV is currently unavailable. **Nothing in Sentinel needs to
change for it to return** — only feed availability. This document is the
verification that the wiring is complete.

---

## 1. The path (unchanged)

```
Government CCTV (RTSP)
   │  scripts/run_pipeline_service.py --cameras cam04,cam06 --registry data/camera_registry.json
   ▼
ingestion.stream_manager  ── per-camera worker, TCP-forced, reconnect/backoff
   ▼
ai/pipeline.py            ── YOLOv8n → ByteTrack → ANPR/OCR → Gujarat-plate normalise
   ▼
POST /api/v1/events/ai-detection   (X-Ingest-Key)    ── events.py
   ▼
vehicle_events  (+ camera auto-onboard, snapshot → MinIO)
   ▼
watchlist engine → alerts → WebSocket /ws/alerts
   ▼
AI layer (Copilot / NL search / summaries / anomaly)   ── reads vehicle_events, never re-processes video
   ▼
journey / GIS / investigation → incidents → evidence → cases → audit
```

## 2. What activation requires

1. RTSP reachable from the pipeline host + `SENTINEL_RTSP_USERNAME` /
   `SENTINEL_RTSP_PASSWORD` in `.env` (already the case; the creds are
   never stored in the DB or exposed by any API).
2. Start the pipeline:
   ```bash
   docker compose --profile ai up -d pipeline      # cam04,cam06 by default
   # or bare-metal:
   .venv/bin/python scripts/run_pipeline_service.py --cameras cam04,cam06 \
       --registry data/camera_registry.json --backend-url http://localhost:8000/api/v1/events/ai-detection
   ```
3. Nothing else. No migration, no config flag, no code change.

## 3. Field-by-field: what a live event carries and where it lands

| Live event field (`ai/pipeline.py`) | Backend column | Used by |
| :--- | :--- | :--- |
| `camera_id` (external code, e.g. `cam04`) | resolved → `cameras.id`, kept as `vehicle_events.camera_code` | camera resolver auto-onboards unknown codes (`INGEST_AUTO_ONBOARD_CAMERAS`) |
| `plate` / `plate_number` | `plate_number` + `plate_number_normalized` | watchlist match, journey, search, Copilot |
| `timestamp` | `vehicle_events.timestamp` | journey ordering, time-range search, anomaly dwell, retention |
| `track_id` (per-camera ByteTrack id) | `vehicle_events.track_id` | **stopped-vehicle anomaly** grouping, journey |
| `vehicle_type` | `vehicle_events.vehicle_type` (canonicalised) | search / Copilot `vehicle_type` filter |
| `vehicle_color` | `vehicle_events.vehicle_color` | search / Copilot `vehicle_color` filter *(column + filters ready; the current detector does not emit colour yet — see limitations)* |
| `latitude` / `longitude` | `vehicle_events.{latitude,longitude,location}` | GIS map, journey **distance / speed** transitions, anomaly displacement |
| `confidence` | `vehicle_events.confidence_score` | search `min_confidence`, Copilot confidence, sighting display |
| `snapshot_base64` / path | MinIO object → `vehicle_events.snapshot_url` | evidence proxy + media ticket |

## 3a. Feed-source abstraction (Phase 15H §12)

One derived field, `feed_source`, decides how anything is presented:

```
DEMO  -- is_demo is set (seed_ai_demo / DEMO scenarios). Badged "DEMO DATA".
MOCK  -- code matches ^mock[_-]?cam (a local simulated clip). Badged "MOCK STREAM".
REAL  -- everything else (a government RTSP feed). Badged "REAL FEED".
```

`cameras.is_demo` + `vehicle_events.is_demo` (migration `0014`, default
false). `app/services/feed_source.py` is the single decision point;
`CameraRead` and `CameraStreamProfile` both carry `feed_source`; the
frontend `CameraPlayer` badges it explicitly. **Seeded demo data is never
presented as government CCTV.**

### Browser playback when feeds return (Phase 15A)

Set `cameras.hls_url` / `cameras.webrtc_url` (operator PATCH or registry
sync) and run a media gateway (MediaMTX) in front of the RTSP feed:

```
rtsp://<gov-camera>  ──►  MediaMTX  ──┬──►  /whep/<cam>     (webrtc_url)
                                      └──►  /hls/<cam>.m3u8 (hls_url)
```

`CameraStreamService.profile()` then returns `mode: LIVE` and the frontend
`CameraPlayer` plays the real stream. No code change, no migration.

## 4. REAL vs MOCK

A camera / sighting is **MOCK** iff its code matches `^mock[_-]?cam` — a
naming convention, never a schema flag, so a real government feed can never
be mislabelled.

* `GET /api/v1/cameras` returns `is_mock` per camera.
* `GET /api/v1/vehicles/search` returns `is_mock` per sighting.
* `POST /api/v1/search/vehicles` supports `source: "REAL" | "MOCK"`.
* The Camera Management console, the GIS markers and the journey UI badge
  MOCK explicitly.

Government cameras are registered from `data/camera_registry.json` (30
entries) with real codes (`cam04`, `cam06`, …) → they render as **REAL**.

## 5. Health status when feeds return

`ingestion.stream_health` pushes `POST /api/v1/cameras/health` every ~5 s
per camera. The backend:

* stores `stream_fps` / `frame_drop_count` / `reconnect_count` / `health_updated_at`;
* serves a freshness-checked **effective status** (`_effective_status`) —
  a camera silent for > 20 s is `OFFLINE` regardless of its last push;
* on a real ONLINE↔OFFLINE transition writes a `camera_health_history` row
  + a `CAMERA_OFFLINE` / `CAMERA_RECOVERED` notification (deduped);
* a 30 s in-process watcher catches cameras that go completely silent.

All of this is already live and exercised by the demo (mock cameras) — it
just starts receiving real telemetry.

## 6. WebSocket

`/ws/alerts` (scoped-ticket auth) broadcasts every alert the instant it is
created — watchlist matches from the live pipeline **and** anomaly alerts.
The frontend command centre and alert feed update in real time. No change.

## 7. AI processing on live data

* **Copilot / NL search / summaries** — on-demand reads of `vehicle_events`
  / `alerts` / `incidents` / `cases`. Live rows appear immediately.
* **Stopped-vehicle anomaly** — `_anomaly_scan_loop` runs every
  `AI_ANOMALY_SCAN_INTERVAL_S` (300 s) over recent events; live tracks are
  included on the next tick. `POST /ai/anomalies/scan` forces it.
* **Journey intelligence** — transitions (distance / estimated speed /
  confidence) are computed from the live `latitude`/`longitude` the
  pipeline already sends.

## 8. Verification performed (with feeds down)

* `tests/test_ai_to_backend.py`, `test_ingestion_bridge.py`,
  `test_camera_registry.py` — exercise the exact ingest → `vehicle_events`
  → watchlist → alert path with a synthetic pipeline payload. **Passing.**
* `tests/test_ws_auth.py` — a real alert frame delivered over `/ws/alerts`.
  **Passing.**
* The AI demo seed (`scripts/seed_ai_demo.py`) writes `vehicle_events` with
  `track_id` / GPS exactly as the live pipeline would, then the **real**
  `BehaviorAnalyticsService` and Copilot run against them.
* Earlier real cam04/cam06 smoke (Phase 11): RTSP auth OK, YOLO+ByteTrack
  run, events delivered, plates `UNKNOWN` (documented).

## 9. Limitations at activation

* **Plate reads on wide-area government feeds are `UNKNOWN`.** The ANPR
  emits `UNKNOWN`, never a guess. Cross-camera correlation is plate-string
  only (no visual Re-ID — future phase).
* **Vehicle colour** is not emitted by the current detector; the column and
  every filter are ready for when it is.
* **CPU throughput** ~1 FPS aggregate across many feeds on the test host
  (see `SCALE_TO_80000.md`). Real-time 30+ live feeds needs GPU + the
  horizontal design in that doc.
