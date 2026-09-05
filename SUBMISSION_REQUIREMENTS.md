# SENTINEL — Submission Requirements: honest status

This is a capability-by-capability status of the platform against the problem
statement. It is deliberately conservative. For the full engineering audit
(what is built, what is PoC-grade, what is a documented limitation) see
[`SENTINEL_System_Audit_Report.md`](SENTINEL_System_Audit_Report.md); for the
live demo see [`DEMO_RUNBOOK.md`](DEMO_RUNBOOK.md).

Status legend:

- **Built** — implemented, wired end to end, exercised by tests and/or the demo.
- **Built · PoC-grade** — works, but with a scale or accuracy caveat called out.
- **Known limitation** — not done, or does not work on real input yet.

## 1. Capability status

| Requirement | What is actually implemented | Status |
| :--- | :--- | :--- |
| CCTV feed onboarding | `POST /api/v1/cameras/sync` upserts a camera catalogue keyed by external code; the ingestion side parses three catalogue payload shapes (`ingestion/catalogue_ingest.py`). 30 real Sentinel cameras are registered in `data/camera_registry.json`. | Built |
| Live RTSP streams | OpenCV `VideoCapture` workers, one thread per camera, RTSP forced over TCP, reconnect/backoff supervisor, per-camera health pushed to the backend. WebRTC/HLS is a browser-side fallback only, not a server pipeline. | Built · PoC-grade |
| Vehicle detection | YOLOv8 (`ultralytics`) detection + ByteTrack tracking per camera. Verified on real feeds — vehicles are detected and tracked. | Built |
| ANPR (plate reading) | Heuristic plate-region locator → **EasyOCR** (PaddleOCR optional via `OCR_ENGINE=paddleocr`) → multi-frame consensus voting → Gujarat plate-format normalisation. | Built · PoC-grade — see §2 |
| Cross-camera tracking | Plate-string correlation across cameras builds a vehicle "journey" (`GET /api/v1/vehicles/search?plate=…` returns ordered `sightings` + a `journey` summary block); rendered as an ordered route on the GIS map. Visual re-identification (matching the same vehicle with no readable plate) is **not** implemented. | Built · PoC-grade |
| Real-time watchlist alerts | Alert router matches every event against the watchlist, dedupes with a cooldown window, persists an `Alert` row, and pushes it over an authenticated WebSocket to the command center. | Built |
| GIS visualisation & trajectory | Leaflet map, PostGIS-backed camera GeoJSON, alert markers, and polyline journey vectors. | Built |
| Evidence | Per-event snapshot uploaded to MinIO (S3-compatible), with a local-disk fallback; served to the UI through a short-lived signed ticket. | Built |
| Observability | `GET /api/v1/dashboard/health` aggregates DB / AI-pipeline / camera / event-flow / alert health — every field a live measurement or `NULL`, never a placeholder. | Built |

## 2. ANPR: the honest caveat

- **On the curated demo clips** (`demo_assets/clips/*.mp4`), the pipeline reads
  `GJ18TC0450` reliably and the full alert → journey → GIS chain lights up.
  This is the path [`DEMO_RUNBOOK.md`](DEMO_RUNBOOK.md) walks through.
- **On the real Sentinel camera feeds available to us** (`cam04`, `cam06`), the
  pipeline detects and tracks vehicles but the plates are too small / motion-
  blurred / oblique to read — events are honestly emitted as `UNKNOWN`. There
  are **zero hallucinated plates**: an unreadable plate is never guessed.
- ANPR accuracy is **not benchmarked against a real labelled dataset** (none
  exists locally). `scripts/evaluate_anpr.py` has a synthetic-font mode
  (measured this pass: 87.5% exact / 98.3% character) but its own output
  refuses to let those rendered-font numbers be quoted as real-camera accuracy.
  **No ">95%" or any headline accuracy figure is claimed.**

## 3. Explicitly NOT built / out of scope

- Distributed / statewide infrastructure (Kafka, Triton, Kubernetes, the
  50k+ camera FPS table in `SCALABILITY.md`) — that document is a roadmap, not
  running code.
- AES-256 evidence encryption, an immutable/append-only audit trail, RS256
  JWTs — the code uses at-rest storage as-is, a normal audit table, and HS256.
- Auto-rickshaw / three-wheeler handling is limited: the detector class set and
  the plate-aspect prior are tuned for cars and two-wheelers.
- Visual vehicle re-identification (no-plate cross-camera matching).
