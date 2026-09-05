"""
Phase 7 -- POST/GET /api/v1/pipeline/status.

The AI pipeline reports AIPipeline.get_metrics() here; the dashboard reads
it back. Missing metrics stay NULL (never a fabricated 0).
"""
from conftest import bearer

# a realistic slice of AIPipeline.get_metrics()
SNAPSHOT = {
    "service_id": "default",
    "num_workers": 1,
    "processed_frames": 4821,
    "processed_fps": 1.3,
    "total_vehicles_detected": 903,
    "total_ai_events_generated": 274,
    "events_sent_ok": 270,
    "events_dropped": 0,
    "event_queue_depth": 1,
    "event_queue_max_depth": 12,
    "yolo_latency_ms": {"count": 900, "avg_ms": 48.0, "p50_ms": 44.0, "p95_ms": 96.0},
    "ocr_latency_ms": {"count": 800, "avg_ms": 180.0, "p50_ms": 168.0, "p95_ms": 402.0},
    "cpu_percent": 320.0,
    "rss_mb": 4400.0,
    "frames_by_camera": {"cam04": 2500, "cam06": 2321, "cam09": 0},
    "events_by_camera": {"cam04": 150, "cam06": 124},
}


def test_push_requires_ingest_auth(client):
    assert client.post("/api/v1/pipeline/status", json=SNAPSHOT).status_code == 401


def test_get_requires_jwt(client):
    assert client.get("/api/v1/pipeline/status").status_code == 401


def test_push_then_read_roundtrip(client, operator_user):
    _, token = operator_user
    push = client.post(
        "/api/v1/pipeline/status", json=SNAPSHOT,
        headers={"X-Ingest-Key": "test-ingest-key"},
    )
    assert push.status_code == 200

    got = client.get("/api/v1/pipeline/status", headers=bearer(token))
    assert got.status_code == 200
    b = got.json()
    assert b["processed_fps"] == 1.3
    assert b["events_generated"] == 274
    assert b["events_delivered"] == 270
    assert b["yolo_p50_ms"] == 44.0
    assert b["ocr_p95_ms"] == 402.0
    # cam09 has 0 frames -> not counted as "processing"
    assert b["cameras_processing"] == 2
    assert b["age_seconds"] is not None and b["age_seconds"] >= 0


def test_get_returns_null_when_never_reported(client, operator_user):
    _, token = operator_user
    got = client.get("/api/v1/pipeline/status", headers=bearer(token))
    assert got.status_code == 200
    assert got.json() is None


def test_missing_metrics_stay_null_not_zero(client, operator_user):
    _, token = operator_user
    client.post(
        "/api/v1/pipeline/status",
        json={"service_id": "default", "processed_fps": 0.9},  # only one field
        headers={"X-Ingest-Key": "test-ingest-key"},
    )
    b = client.get("/api/v1/pipeline/status", headers=bearer(token)).json()
    assert b["processed_fps"] == 0.9
    assert b["yolo_p50_ms"] is None
    assert b["events_generated"] is None
    assert b["cpu_percent"] is None


def test_push_is_an_upsert(client, operator_user):
    _, token = operator_user
    for fps in (1.0, 2.0, 3.0):
        client.post(
            "/api/v1/pipeline/status",
            json={"service_id": "default", "processed_fps": fps},
            headers={"X-Ingest-Key": "test-ingest-key"},
        )
    b = client.get("/api/v1/pipeline/status", headers=bearer(token)).json()
    assert b["processed_fps"] == 3.0
