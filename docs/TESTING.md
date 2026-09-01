# SENTINEL — System Testing & Quality Assurance Guide

This document outlines the testing strategy for verifying all subsystems of the **SENTINEL** platform: Unit Testing, Inter-Module Integration Testing, End-to-End Hero Feature Validation, and Government Feed Resilience Testing.

---

# 1. Unit Testing Matrix

Unit tests validate isolated algorithms, data parsing, and model functions without external network dependencies.

| Module | Subsystem | Test Description | Target Framework | Command |
| :--- | :--- | :--- | :--- | :--- |
| **Ingestion** | `catalogue_ingest.py` | Parse valid & malformed `/api/ingest` JSON payloads | `pytest` | `pytest tests/unit/test_ingest.py` |
| **Ingestion** | `reconnect.py` | Verify exponential backoff sequence (`2s -> 4s -> 8s -> 16s -> 30s`) | `pytest` | `pytest tests/unit/test_backoff.py` |
| **AI** | `ocr_engine.py` | Validate OCR plate normalization regex on raw strings | `pytest` | `pytest tests/unit/test_ocr_regex.py` |
| **AI** | `consensus.py` | Multi-frame voting algorithm accuracy across 5 frame predictions | `pytest` | `pytest tests/unit/test_consensus.py` |
| **Tracking** | `track_association.py` | ByteTrack ID matching with license plate detection bounding boxes | `pytest` | `pytest tests/unit/test_association.py` |
| **Backend** | `watchlist_engine.py` | Watchlist exact and pattern match lookup logic | `pytest` | `pytest tests/unit/test_watchlist.py` |
| **Backend** | `alert_cooldown.py` | Verify alert suppression for identical plate within 5-min window | `pytest` | `pytest tests/unit/test_cooldown.py` |
| **Frontend** | `StatCard.jsx` | Render metric numbers and trend badges correctly | `Jest / RTL` | `npm run test:unit` |

---

# 2. Integration Testing Pipeline

Integration tests verify data pass-through across subsystem boundaries.

```text
RTSP Stream ──► AI Detection Queue ──► FastAPI Ingest ──► PostGIS DB ──► Watchlist Match ──► WebSocket Broadcast ──► React Dashboard
```

### Key Integration Tests (`tests/integration/`)

#### 1. Ingestion ➔ AI Interface Test (`test_ingest_to_ai.py`)
- Verifies that raw frames captured from OpenCV/FFmpeg are successfully pushed to Kavya's AI processing queue with PTS timestamps intact.

#### 2. AI ➔ Backend REST Ingest Test (`test_ai_to_backend.py`)
- Mocks an AI event payload and posts to `/api/v1/events/ai-detection`.
- Verifies database record creation in `vehicle_events` and evidence image saving in MinIO storage.

#### 3. Backend ➔ Frontend WebSocket Test (`test_backend_to_frontend_ws.py`)
- Connects a WebSocket client to `ws://localhost:8000/ws/alerts`.
- Triggers a watchlist match in the backend and asserts sub-second reception of the alert payload over the socket.

---

# 3. End-to-End (E2E) Hero Feature Test

The End-to-End test validates the primary hackathon demonstration workflow:

```text
[Simulated Vehicle Transit] ──► ANPR Detection ──► Watchlist Hit ──► Real-Time Alert ──► GIS Route ──► Investigation Search
```

### Step-by-Step E2E Verification Protocol:

1. **Target Setup**: Insert target plate `GJ01AB1234` into the `watchlist` table under category `Stolen Vehicle`.
2. **Stream Playback**: Inject sample test video clip containing `GJ01AB1234` passing CAM-007, CAM-013, CAM-021, and CAM-034.
3. **Automated Verification**:
   - Confirm AI pipeline identifies `GJ01AB1234` across all 4 camera views.
   - Confirm `alerts` database table contains a new entry for `GJ01AB1234`.
   - Confirm WebSocket client receives real-time alert toast.
4. **UI Verification**:
   - Search `GJ01AB1234` in the Investigation page (`/investigation`).
   - Confirm chronological timeline displays 4 camera sightings in order.
   - Confirm GIS Map (`/map`) draws connected polyline vectors between CAM-007 ➔ CAM-013 ➔ CAM-021 ➔ CAM-034.
   - Confirm evidence modal displays full snapshot and license plate crop.

---

# 4. Government Feed Resilience Testing

Dedicated resilience tests to guarantee system stability against real-world CCTV network degradation:

### 1. RTSP Stream Disconnect & Recovery Test
- **Action**: Abruptly terminate the RTSP server connection during stream capture.
- **Expected Behavior**: Stream Ingestion service catches network failure, switches camera status to `RECONNECTING`, and executes exponential backoff (`2s -> 4s -> 8s -> 16s -> 30s`).
- **Pass Criteria**: Service automatically re-establishes connection when stream server restarts without worker thread crash.

### 2. Mixed Codec Handling Test (H.264 / H.265)
- **Action**: Feed alternating H.264 and H.265 video streams into `/api/ingest`.
- **Expected Behavior**: Decoder handles codec switches seamlessly without memory leaks or color space distortion.

### 3. PTS Timestamping vs Variable FPS Test
- **Action**: Inject video feed with artificial frame drops and jitter (varying 5 FPS to 30 FPS).
- **Expected Behavior**: AI pipeline correctly orders events using PTS timestamps rather than wall-clock time or fixed frame rates.

### 4. Non-Fatal Decoder Join Warning Test
- **Action**: Start video stream mid-GOP (Group of Pictures) without initial IDR keyframe.
- **Expected Behavior**: System ignores initial corrupt macroblocks, waits for next keyframe, and logs non-fatal warning without crashing process.
