# SENTINEL CCTV Stream Ingestion Manager

Owner: **Rishit**
Branch: `feature/rishit-stream`

## Responsibilities
- `/api/ingest` Catalogue ingestion endpoint
- RTSP over TCP video capture
- FFmpeg / OpenCV / GStreamer multi-stream ingestion
- PTS timestamping & inter-frame stability
- Automatic exponential backoff reconnection engine (2s -> 4s -> 8s -> 16s -> 30s)
- Stream health telemetry & monitoring
