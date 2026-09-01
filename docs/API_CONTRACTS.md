# SENTINEL — Inter-Module API & Data Contracts

This document defines the strict data schemas and JSON payloads governing communication between the **Ingestion Subsystem**, **AI Analytics Engine**, **Backend Services**, and **Frontend Dashboard**.

All team members must adhere strictly to these contract structures.

---

## 1. Stream Ingestion ➔ AI Engine Contract

**Protocol**: Shared Memory / IPC / Internal HTTP  
**Description**: Rishit's stream ingestion layer passes video frame metadata to Kavya's AI processing queue.

```json
{
  "contract_version": "1.0",
  "camera_id": "CAM-AHM-021",
  "frame_sequence": 10492,
  "pts": 1725186734000,
  "timestamp": "2026-09-01T10:32:14.000Z",
  "width": 1920,
  "height": 1080,
  "codec": "H.264",
  "frame_reference": "ram://frames/CAM-AHM-021_10492.raw"
}
```

---

## 2. AI Engine ➔ Backend API Contract

**Protocol**: REST HTTP POST (`/api/v1/events/ai-detection`)  
**Description**: Kavya/Prajin's AI pipeline posts detection and ANPR consensus results to Vanshal's backend.

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

## 3. Backend ➔ Frontend REST API Contract

### 3.1 Recent Vehicle Sightings Endpoint
**Endpoint**: `GET /api/v1/vehicles/events`

```json
{
  "status": "success",
  "count": 1,
  "data": [
    {
      "event_id": "evt_8f92a11b-4c3d-4912",
      "plate_number": "GJ01AB1234",
      "camera_id": "CAM-AHM-021",
      "camera_name": "Pakwan Flyover North",
      "department": "Traffic Police",
      "timestamp": "2026-09-01T10:32:14.000Z",
      "latitude": 23.0345,
      "longitude": 72.5812,
      "confidence": 0.96,
      "vehicle_type": "car",
      "watchlist_match": true,
      "alert_triggered": true,
      "evidence_url": "http://localhost:9000/sentinel-evidence/CAM-AHM-021_103214_GJ01AB1234.jpg"
    }
  ]
}
```

### 3.2 Vehicle Route & Search History Endpoint
**Endpoint**: `GET /api/v1/vehicles/search?plate=GJ01AB1234`

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
  "route": [
    {
      "sequence": 1,
      "camera_id": "CAM-AHM-007",
      "camera_name": "SG Highway South",
      "timestamp": "2026-09-01T10:02:14.000Z",
      "latitude": 23.0112,
      "longitude": 72.5510,
      "evidence_url": "http://localhost:9000/sentinel-evidence/CAM-007.jpg"
    },
    {
      "sequence": 2,
      "camera_id": "CAM-AHM-013",
      "camera_name": "Iscon Cross Road",
      "timestamp": "2026-09-01T10:09:31.000Z",
      "latitude": 23.0245,
      "longitude": 72.5634,
      "evidence_url": "http://localhost:9000/sentinel-evidence/CAM-013.jpg"
    },
    {
      "sequence": 3,
      "camera_id": "CAM-AHM-021",
      "camera_name": "Pakwan Flyover North",
      "timestamp": "2026-09-01T10:18:07.000Z",
      "latitude": 23.0345,
      "longitude": 72.5812,
      "evidence_url": "http://localhost:9000/sentinel-evidence/CAM-021.jpg"
    },
    {
      "sequence": 4,
      "camera_id": "CAM-AHM-034",
      "camera_name": "Gandhinagar Toll Plaza",
      "timestamp": "2026-09-01T10:31:22.000Z",
      "latitude": 23.0890,
      "longitude": 72.6101,
      "evidence_url": "http://localhost:9000/sentinel-evidence/CAM-034.jpg"
    }
  ]
}
```

---

## 4. Real-Time Alert WebSocket Push Contract

**Protocol**: WebSocket (`ws://localhost:8000/ws/alerts`)  
**Description**: Push notification broadcast when a detected plate matches the watchlist.

```json
{
  "alert_id": "alt_9921-bc10",
  "event_type": "CRITICAL_WATCHLIST_MATCH",
  "timestamp": "2026-09-01T10:32:14.000Z",
  "priority": "CRITICAL",
  "details": {
    "plate_number": "GJ01AB1234",
    "watchlist_category": "Stolen Vehicle",
    "owner_name": "Representative Sample Record",
    "camera_id": "CAM-AHM-021",
    "location_name": "Pakwan Flyover North",
    "latitude": 23.0345,
    "longitude": 72.5812,
    "confidence": 0.96,
    "evidence_snapshot": "http://localhost:9000/sentinel-evidence/CAM-AHM-021_103214_GJ01AB1234.jpg"
  }
}
```
