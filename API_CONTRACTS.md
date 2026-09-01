# SENTINEL — Master API Contracts & Schemas Specification

---

## 1. Camera Registry API

### `GET /api/v1/cameras`
Returns list of registered CCTV cameras.

```json
{
  "status": "success",
  "data": [
    {
      "camera_id": "CAM_AHM_001",
      "name": "Ashram Road Junction North",
      "department": "Traffic Police",
      "location": {
        "latitude": 23.0225,
        "longitude": 72.5714
      },
      "stream_url": "rtsp://10.0.1.100:554/live/ch1",
      "stream_protocol": "RTSP/TCP",
      "status": "ONLINE"
    }
  ]
}
```

---

## 2. AI Detection Event Ingestion API

### `POST /api/v1/events/ai-detection`
Ingests detection payload emitted by Kavya's AI pipeline.

```json
{
  "camera_id": "CAM_AHM_001",
  "track_id": 42,
  "timestamp": "2026-09-01T14:32:10.125Z",
  "pts_timestamp_ms": 1788273130125,
  "vehicle_type": "car",
  "plate_number": "GJ01AB1234",
  "ocr_confidence": 0.942,
  "consensus_votes": 8,
  "total_frames_analyzed": 10,
  "evidence_snapshot_path": "evidence/2026/09/01/CAM_AHM_001_1788273130125_GJ01AB1234.jpg"
}
```

---

## 3. Real-Time Watchlist Alert WebSocket Payload

### `WS /ws/alerts`
Broadcast payload emitted when an AI event matches a blacklisted watchlist record.

```json
{
  "alert_id": "ALT_982341",
  "camera_id": "CAM_AHM_001",
  "camera_name": "Ashram Road Junction North",
  "plate_number": "GJ01AB1234",
  "vehicle_type": "car",
  "offense_category": "Stolen Vehicle",
  "priority": "HIGH",
  "timestamp": "2026-09-01T14:32:10.500Z",
  "location": {
    "latitude": 23.0225,
    "longitude": 72.5714
  },
  "evidence_snapshot_url": "http://localhost:9000/sentinel-evidence/CAM_AHM_001_GJ01AB1234.jpg",
  "acknowledged": false
}
```

---

## 4. Vehicle Search & Trajectory Response Schema

### `GET /api/v1/vehicles/search?plate=GJ01AB1234`

```json
{
  "status": "success",
  "query_plate": "GJ01AB1234",
  "total_sightings": 3,
  "summary": {
    "first_seen": "2026-09-01T10:15:00Z",
    "last_seen": "2026-09-01T14:32:10Z",
    "total_cameras": 3,
    "has_active_watchlist_hit": true
  },
  "sightings": [
    {
      "event_id": "EVT_001",
      "camera_id": "CAM_AHM_001",
      "camera_name": "Ashram Road Junction",
      "timestamp": "2026-09-01T10:15:00Z",
      "location": { "latitude": 23.0225, "longitude": 72.5714 },
      "evidence_snapshot_url": "http://localhost:9000/sentinel-evidence/EVT_001.jpg"
    },
    {
      "event_id": "EVT_002",
      "camera_id": "CAM_AHM_004",
      "camera_name": "SG Highway Circle",
      "timestamp": "2026-09-01T12:40:22Z",
      "location": { "latitude": 23.0301, "longitude": 72.5802 },
      "evidence_snapshot_url": "http://localhost:9000/sentinel-evidence/EVT_002.jpg"
    }
  ]
}
```
