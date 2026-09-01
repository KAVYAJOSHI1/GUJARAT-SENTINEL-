# SENTINEL — Inter-Module API & Data Contracts Specification

This document provides the implementation-grade JSON schemas and data contracts governing all communication between **Ingestion Services**, **AI Pipeline Workers**, **FastAPI Backend Services**, and the **React Dashboard**.

---

# 1. Camera Object Schema

### `GET /api/v1/cameras/{camera_id}`
```json
{
  "camera_id": "CAM-AHM-021",
  "name": "Pakwan Flyover North",
  "department": "Traffic Police",
  "location": {
    "latitude": 23.0345,
    "longitude": 72.5812
  },
  "codec": "H.264",
  "rtsp_url": "rtsp://gateway.sentinel.gujarat.gov.in:554/stream21",
  "webrtc_url": "https://gateway.sentinel.gujarat.gov.in/webrtc/cam-021",
  "hls_url": "https://gateway.sentinel.gujarat.gov.in/hls/cam-021.m3u8",
  "status": "ONLINE",
  "created_at": "2026-09-01T08:00:00.000Z"
}
```

---

# 2. AI Event Object Schema

### `POST /api/v1/events/ai-detection`
```json
{
  "event_id": "evt_8f92a11b-4c3d-4912",
  "camera_id": "CAM-AHM-021",
  "track_id": 42,
  "vehicle_type": "car",
  "vehicle_color": "white",
  "plate_number": "GJ01AB1234",
  "raw_ocr_text": "GJ 01 AB 1234",
  "confidence": 0.96,
  "plate_bounding_box": {
    "x_min": 450,
    "y_min": 600,
    "x_max": 620,
    "y_max": 650
  },
  "timestamp": "2026-09-01T10:32:14.000Z",
  "evidence_snapshot_path": "evidence/20260901/CAM-AHM-021_103214_GJ01AB1234.jpg",
  "plate_crop_path": "evidence/20260901/crops/CAM-AHM-021_103214_crop.jpg"
}
```

---

# 3. Alert Object Schema

### `WS /ws/alerts` & `GET /api/v1/alerts`
```json
{
  "alert_id": "alt_9921-bc10",
  "event_id": "evt_8f92a11b-4c3d-4912",
  "plate_number": "GJ01AB1234",
  "alert_type": "WATCHLIST_MATCH",
  "severity": "CRITICAL",
  "watchlist_category": "Stolen Vehicle",
  "camera_id": "CAM-AHM-021",
  "camera_name": "Pakwan Flyover North",
  "latitude": 23.0345,
  "longitude": 72.5812,
  "timestamp": "2026-09-01T10:32:14.000Z",
  "acknowledged": false,
  "acknowledged_by": null,
  "evidence_snapshot_url": "http://localhost:9000/sentinel-evidence/CAM-AHM-021_103214_GJ01AB1234.jpg"
}
```

---

# 4. Vehicle History Response Schema

### `GET /api/v1/vehicles/search?plate=GJ01AB1234`
```json
{
  "query_plate": "GJ01AB1234",
  "total_sightings": 4,
  "first_seen": "2026-09-01T10:02:14.000Z",
  "last_seen": "2026-09-01T10:31:22.000Z",
  "watchlist_status": {
    "is_listed": true,
    "category": "Stolen Vehicle",
    "priority": "CRITICAL"
  },
  "sightings": [
    {
      "sequence": 1,
      "event_id": "evt_001",
      "camera_id": "CAM-AHM-007",
      "camera_name": "SG Highway South",
      "department": "Traffic Police",
      "timestamp": "2026-09-01T10:02:14.000Z",
      "latitude": 23.0112,
      "longitude": 72.5510,
      "confidence": 0.94,
      "evidence_url": "http://localhost:9000/sentinel-evidence/CAM-007.jpg"
    },
    {
      "sequence": 2,
      "event_id": "evt_002",
      "camera_id": "CAM-AHM-013",
      "camera_name": "Iscon Cross Road",
      "department": "City Police",
      "timestamp": "2026-09-01T10:09:31.000Z",
      "latitude": 23.0245,
      "longitude": 72.5634,
      "confidence": 0.97,
      "evidence_url": "http://localhost:9000/sentinel-evidence/CAM-013.jpg"
    },
    {
      "sequence": 3,
      "event_id": "evt_003",
      "camera_id": "CAM-AHM-021",
      "camera_name": "Pakwan Flyover North",
      "department": "Traffic Police",
      "timestamp": "2026-09-01T10:18:07.000Z",
      "latitude": 23.0345,
      "longitude": 72.5812,
      "confidence": 0.96,
      "evidence_url": "http://localhost:9000/sentinel-evidence/CAM-021.jpg"
    },
    {
      "sequence": 4,
      "event_id": "evt_004",
      "camera_id": "CAM-AHM-034",
      "camera_name": "Gandhinagar Toll Plaza",
      "department": "Highways Authority",
      "timestamp": "2026-09-01T10:31:22.000Z",
      "latitude": 23.0890,
      "longitude": 72.6101,
      "confidence": 0.92,
      "evidence_url": "http://localhost:9000/sentinel-evidence/CAM-034.jpg"
    }
  ]
}
```

---

# 5. Camera Telemetry & Health Schema

### `GET /api/v1/streams/health`
```json
{
  "total_cameras": 50,
  "online_count": 46,
  "reconnecting_count": 3,
  "offline_count": 1,
  "telemetry": [
    {
      "camera_id": "CAM-AHM-001",
      "status": "ONLINE",
      "current_fps": 24.8,
      "pts_jitter_ms": 1.2,
      "dropped_frames_last_min": 0,
      "reconnect_attempts": 0,
      "last_heartbeat": "2026-09-01T10:32:14.000Z"
    },
    {
      "camera_id": "CAM-AHM-003",
      "status": "RECONNECTING",
      "current_fps": 0.0,
      "pts_jitter_ms": 0.0,
      "dropped_frames_last_min": 142,
      "reconnect_attempts": 2,
      "next_reconnect_seconds": 4,
      "last_heartbeat": "2026-09-01T10:30:10.000Z"
    }
  ]
}
```

---

# 6. Standardized HTTP API Error Response Format

All backend API errors return a uniform JSON error payload:

```json
{
  "error": {
    "code": 404,
    "message": "Resource Not Found",
    "details": "Vehicle registration plate 'GJ99ZZ9999' has no recorded sightings.",
    "timestamp": "2026-09-01T10:32:14.000Z"
  }
}
```

### Standard Error Status Codes & Concrete Examples

#### 1. `400 Bad Request`
```json
{
  "error": {
    "code": 400,
    "message": "Invalid Parameter",
    "details": "Plate search parameter must be at least 4 alphanumeric characters.",
    "timestamp": "2026-09-01T10:32:14.000Z"
  }
}
```

#### 2. `401 Unauthorized`
```json
{
  "error": {
    "code": 401,
    "message": "Authentication Required",
    "details": "Missing or expired JWT Bearer token in Authorization header.",
    "timestamp": "2026-09-01T10:32:14.000Z"
  }
}
```

#### 3. `403 Forbidden`
```json
{
  "error": {
    "code": 403,
    "message": "Access Denied",
    "details": "Operator role lacks permission to delete watchlist entries.",
    "timestamp": "2026-09-01T10:32:14.000Z"
  }
}
```

#### 4. `404 Not Found`
```json
{
  "error": {
    "code": 404,
    "message": "Camera Not Found",
    "details": "Camera ID 'CAM-999' is not registered in the system.",
    "timestamp": "2026-09-01T10:32:14.000Z"
  }
}
```

#### 5. `409 Conflict`
```json
{
  "error": {
    "code": 409,
    "message": "Duplicate Entry",
    "details": "Vehicle plate 'GJ01AB1234' is already active on the watchlist.",
    "timestamp": "2026-09-01T10:32:14.000Z"
  }
}
```

#### 6. `422 Unprocessable Entity`
```json
{
  "error": {
    "code": 422,
    "message": "Validation Error",
    "details": "Field 'confidence' must be a floating point number between 0.0 and 1.0.",
    "timestamp": "2026-09-01T10:32:14.000Z"
  }
}
```

#### 7. `500 Internal Server Error`
```json
{
  "error": {
    "code": 500,
    "message": "Database Operation Failed",
    "details": "PostGIS spatial query failure during distance calculation.",
    "timestamp": "2026-09-01T10:32:14.000Z"
  }
}
```

#### 8. `503 Service Unavailable`
```json
{
  "error": {
    "code": 503,
    "message": "Stream Ingestion Manager Unavailable",
    "details": "RTSP video frame buffer pool exhausted under heavy ingestion load.",
    "timestamp": "2026-09-01T10:32:14.000Z"
  }
}
```
