# Camera Reliability Intelligence (Phase 14 §9)

A **statistical view of recent camera stability** from the existing
`camera_health_history` + `cameras` + `vehicle_events`.

> This is **not** failure prediction. The service never claims a camera
> *will* fail — only that its recent behaviour is (un)stable, with the
> evidence. No forecast, no ML.

---

## 1. Per-camera assessment (`CameraReliabilityService`)

| Signal | Source | Meaning |
| :--- | :--- | :--- |
| `disconnect_count` | `camera_health_history` ONLINE→OFFLINE/DEGRADED rows in window | how often it dropped |
| `mean_recovery_seconds` | matched OFFLINE→ONLINE gaps | how long it stays down |
| `heartbeat_stale` | `cameras.health_updated_at` vs 20 s | is it silent *right now* |
| `stream_fps` / `fps_degraded` | `cameras.stream_fps` vs `CAMERA_RELIABILITY_FPS_FLOOR` (5) | throughput collapse |
| `reconnect_count` | `cameras.reconnect_count` | cumulative RTSP reconnects |
| `detection_rate_change_pct` | `vehicle_events`/h this window vs the prior window (own baseline) | is it still *seeing* traffic |

### Score

```
health_score = 100
  − min(45, disconnects × 12)
  − 25   if heartbeat stale
  − 15   if FPS below floor
  − min(15, reconnects over threshold × 3)
  − 12   if detections down > 50 % vs own baseline
  −  8   if mean recovery > 300 s
```

| `health_score` | `reliability_score` |
| :--- | :--- |
| ≥ 80 | `HIGH` |
| ≥ 55 | `MEDIUM` |
| < 55 | `LOW` |
| never reported health | `UNKNOWN` (score `null`) |

`degradation_indicator` is `true` when reliability is `LOW`/`MEDIUM` **and**
there is at least one concrete observation (never for `UNKNOWN`).

Every camera also returns an `observations[]` list — the plain-language
evidence behind the score (e.g. *"4 disconnect(s) in 24h, avg recovery
140s"*, *"stream FPS 3.4 below floor 5"*).

## 2. API (`/api/v1/ai/camera-intelligence`, JWT, read-only)

| Endpoint | Notes |
| :--- | :--- |
| `GET /ai/camera-intelligence?window_hours=` | all cameras, **worst score first**, never-reported last; `camera_count`, `degraded_count`, `note` |
| `GET /ai/camera-intelligence/{code}?window_hours=` | one camera + its last 50 `camera_health_history` transitions |

## 3. Frontend — `/camera-intelligence`

`CameraIntelligencePage.jsx`: KPI row (cameras, avg health score, showing
degradation), a table ranked worst-first (health score, reliability label +
`DEGRADING` chip, disconnects + avg recovery, FPS, detections/h with a
drop arrow, top observations), and a detail modal (metrics + full
observation list + the health-transition log). Window switch 24h / 3d / 7d.
Reachable from the `Cam Intel` nav tab.

## 4. Config

`CAMERA_RELIABILITY_WINDOW_HOURS` (24), `_FPS_FLOOR` (5),
`_RECONNECT_WARN` (3), `_DISCONNECT_PENALTY` (12),
`_SLOW_RECOVERY_S` (300), `_MIN_BASELINE_DETECTIONS` (20),
`_HIGH_SCORE` (80), `_MEDIUM_SCORE` (55).

## 5. Offline demo

`seed_ai_demo.py` configures `CAM-07` with `stream_fps = 3.4`,
`reconnect_count = 6`, a slightly stale heartbeat and **3 disconnect /
recovery pairs** in `camera_health_history` — so it lands at
`reliability_score = LOW` with real observations, while the other demo
cameras (no telemetry in this offline environment) show `UNKNOWN`.

## 6. Tests

`backend/tests/test_camera_reliability.py` (9): healthy → HIGH,
disconnects lower the score + flag degradation + compute recovery time,
never-reported → UNKNOWN, stale heartbeat penalised, FPS degraded,
assess-all ranked worst-first with never-reported last, endpoints, unknown
camera 404, auth 401.

## 7. Limitations

- In an environment with no live ingestion (feeds down), most cameras have
  **no** health telemetry → `UNKNOWN`. The intelligence becomes meaningful
  as soon as `ingestion.stream_health` starts pushing.
- Thresholds are global constants, not per-camera calibrated.
- "Failure prediction" is explicitly **out of scope** — see the header.
