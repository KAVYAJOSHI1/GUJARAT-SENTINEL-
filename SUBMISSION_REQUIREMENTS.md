# SENTINEL — Hackathon Submission Requirements Compliance

---

## 1. Compliance Matrix

| Requirement | Implementation Detail | Status |
| :--- | :--- | :--- |
| **50 CCTV Feeds Onboarding** | Standardized `/api/ingest` catalogue parser for department cameras | Fully Compliant |
| **Live RTSP/WebRTC Streams** | OpenCV multi-threaded workers forcing RTSP over TCP | Fully Compliant |
| **Vehicle Detection & ANPR** | YOLOv8 + PaddleOCR with multi-frame consensus voting | Fully Compliant |
| **Cross-Camera Tracking** | ByteTrack spatial-temporal indexing & plate string correlation | Fully Compliant |
| **Real-Time Watchlist Alerts** | Sub-second alert router with 5-minute cooldown deduplication | Fully Compliant |
| **GIS Visualization & Trajectory** | Leaflet CartoDB dark maps with polyline route vectors | Fully Compliant |
