# SENTINEL — CCTV Feed Integration & RTSP Stream Manager

---

## 1. Overview
The Stream Ingestion Subsystem standardizes onboarding across 50+ government CCTV feeds operating over heterogeneous protocols (RTSP, WebRTC, HLS) and video codecs (H.264, H.265).

---

## 2. Technical Ingestion Standards

1. **RTSP Over TCP**: All RTSP stream connections force TCP transport (`rtsp_transport;tcp`) to prevent packet loss, UDP corruption, and visual artifact smearing.
2. **PTS Timestamping**: Frame timing relies exclusively on Presentation Time Stamps (`CAP_PROP_POS_MSEC`) to guarantee accurate sequencing regardless of variable network delivery rates.
3. **Catalogue Ingestion (`/api/ingest`)**: Standardized HTTP endpoint parsing camera catalogue JSON payloads provided by government authorities.
4. **Exponential Backoff Reconnection Engine**: Automatic retry loop (`2s -> 4s -> 8s -> 16s -> 30s max`) managing stream disconnects gracefully without process termination.
5. **Stream Health Telemetry (`GET /api/v1/streams/health`)**: Telemetry service tracking FPS, frame drop rates, and operational status (`ONLINE`, `RECONNECTING`, `OFFLINE`).
