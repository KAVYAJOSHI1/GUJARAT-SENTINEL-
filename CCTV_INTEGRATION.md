# SENTINEL — CCTV Feed Integration & RTSP Stream Manager

---

## 1. Overview
The Stream Ingestion Subsystem standardizes onboarding across 50+ government CCTV feeds operating over heterogeneous protocols (RTSP, WebRTC, HLS) and video codecs (H.264, H.265).

---

## 2. Technical Ingestion Standards

1. **RTSP Over TCP**: All RTSP stream connections force TCP transport (`rtsp_transport;tcp`) to prevent packet loss, UDP corruption, and visual artifact smearing.
2. **PTS Timestamping**: Frame timing relies exclusively on Presentation Time Stamps (`CAP_PROP_POS_MSEC`) to guarantee accurate sequencing regardless of variable network delivery rates.
3. **Catalogue Ingestion (`POST /api/v1/cameras/sync`)**: Standardized HTTP endpoint upserting a camera catalogue (keyed by external `code`) from JSON payloads. The parser in `ingestion/catalogue_ingest.py` accepts three catalogue payload shapes.
4. **Exponential Backoff Reconnection Engine**: Automatic retry loop (`2s -> 4s -> 8s -> 16s -> 30s max`) managing stream disconnects gracefully without process termination.
5. **Stream Health Telemetry**: The ingestion workers push per-camera FPS, frame-drop, and status (`ONLINE`, `RECONNECTING`, `OFFLINE`) via `POST /api/v1/cameras/health`; the aggregate is read back at `GET /api/v1/dashboard/health`.
