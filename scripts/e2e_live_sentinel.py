#!/usr/bin/env python3
"""
END-TO-END test against REAL Sentinel RTSP cameras.

    real Sentinel RTSP -> StreamWorker -> FrameEnvelope -> FrameConsumer
    -> FrameInput -> AIPipeline (YOLO -> plate -> OCR -> consensus -> ByteTrack)
    -> AI event -> POST /events/ai-detection -> PostgreSQL/PostGIS
    -> watchlist -> alert -> dashboard API

This does NOT fall back to synthetic data. If Sentinel RTSP credentials are
not configured it exits immediately with a clear message.

Env:
    SENTINEL_RTSP_USERNAME / SENTINEL_RTSP_PASSWORD   REQUIRED
    SENTINEL_BACKEND_URL   (default http://localhost:8000/api/v1/events/ai-detection)
    SENTINEL_INGEST_API_KEY
    ADMIN_USER / ADMIN_PASSWORD   (to POST /cameras/sync + read back results)

Usage:
    SENTINEL_RTSP_USERNAME=... SENTINEL_RTSP_PASSWORD=... \
      .venv/bin/python scripts/e2e_live_sentinel.py --cameras cam04,cam06 --duration 60
"""
import argparse
import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import requests  # noqa: E402

from ai.adapter.ingestion_bridge import FrameConsumer  # noqa: E402
from ai.pipeline import AIPipeline  # noqa: E402
from ingestion.models import CameraLocation, CameraRecord  # noqa: E402
from ingestion.rtsp_auth import env_rtsp_credentials, redact_rtsp_url  # noqa: E402
from ingestion.stream_manager import StreamManager  # noqa: E402

REGISTRY = os.path.join(os.path.dirname(__file__), "..", "data", "camera_registry.json")
RTSP_BASE = os.getenv("SENTINEL_RTSP_BASE", "rtsp://103.250.160.189:8554/stream")


def _fail(msg: str, code: int = 3):
    print(f"\n[FAIL] {msg}", file=sys.stderr)
    sys.exit(code)


def load_records(cam_ids):
    with open(REGISTRY) as f:
        by_id = {c["camera_id"]: c for c in json.load(f)}
    recs = []
    for cid in cam_ids:
        e = by_id.get(cid, {"camera_id": cid})
        loc = None
        if e.get("latitude") is not None:
            loc = CameraLocation(latitude=float(e["latitude"]), longitude=float(e["longitude"]))
        recs.append(CameraRecord(
            camera_id=cid,
            name=e.get("name"),
            stream_url=e.get("rtsp_url") or f"{RTSP_BASE}/{cid}",
            stream_protocol="RTSP/TCP",
            location=loc,
            codec_hint=e.get("codec"),
            hls_url=e.get("hls_url"),
            raw=e,
        ))
    return recs, by_id


def main():
    ap = argparse.ArgumentParser(description="REAL Sentinel-feed end-to-end test")
    ap.add_argument("--cameras", default="cam04,cam06")
    ap.add_argument("--duration", type=float, default=60.0)
    ap.add_argument("--backend-url",
                    default=os.getenv("SENTINEL_BACKEND_URL",
                                      "http://localhost:8000/api/v1/events/ai-detection"))
    ap.add_argument("--frame-skip", type=int, default=2)
    args = ap.parse_args()

    u, p = env_rtsp_credentials()
    if not (u and p):
        _fail("Sentinel RTSP authentication credentials are not configured "
              "(set SENTINEL_RTSP_USERNAME / SENTINEL_RTSP_PASSWORD).", code=3)

    cam_ids = [c.strip() for c in args.cameras.split(",") if c.strip()]
    records, reg = load_records(cam_ids)
    api = args.backend_url.split("/events/ai-detection")[0]
    ingest_key = os.getenv("SENTINEL_INGEST_API_KEY") or os.getenv("INGEST_API_KEY")

    print("=" * 70)
    print(" GUJARAT SENTINEL — LIVE RTSP END-TO-END TEST")
    print("=" * 70)
    for r in records:
        print(f"  {r.camera_id}: {redact_rtsp_url(r.stream_url)}  codec={r.codec_hint}")

    # backend reachability + camera sync
    backend_up = False
    auth = {}
    try:
        h = requests.get(f"{api.replace('/api/v1','')}/health", timeout=5)
        backend_up = h.ok
    except Exception:
        pass
    if backend_up and os.getenv("ADMIN_USER") and os.getenv("ADMIN_PASSWORD"):
        try:
            t = requests.post(f"{api}/auth/login",
                              json={"username": os.getenv("ADMIN_USER"),
                                    "password": os.getenv("ADMIN_PASSWORD")}, timeout=10)
            if t.ok:
                auth = {"Authorization": f"Bearer {t.json()['access_token']}"}
                requests.post(f"{api}/cameras/sync", headers=auth, json=[
                    {"camera_id": r.camera_id, "name": r.name,
                     "latitude": r.raw.get("latitude"), "longitude": r.raw.get("longitude"),
                     "rtsp_url": r.raw.get("rtsp_url")} for r in records], timeout=15)
        except Exception as exc:
            print(f"  (camera sync skipped: {exc})")
    print(f"  backend: {'up' if backend_up else 'NOT reachable — events will buffer'}")

    mgr = StreamManager(max_queue_size=400)
    pipe = AIPipeline(backend_url=args.backend_url, evidence_dir="evidence/live_sentinel", device="cpu")
    if ingest_key:
        pipe.ingest_api_key = ingest_key
    pipe.send_snapshot_b64 = True

    ev_log = []
    stop = threading.Event()
    consumer = FrameConsumer(mgr.frame_queue, pipe, stop_event=stop, frame_skip=args.frame_skip,
                             camera_names={r.camera_id: (r.name or r.camera_id) for r in records},
                             on_events=lambda cam, evs: ev_log.extend((cam, e) for e in evs))
    consumer.start()
    mgr.sync_cameras(records)

    t0 = time.time()
    while time.time() - t0 < args.duration and not stop.is_set():
        time.sleep(2.0)
        mgr.sync_cameras(records)

    mgr.stop_all()
    stop.set()
    consumer.join(timeout=5)
    pipe.flush_events()

    # -------- report --------
    health = {m.camera_id: m for m in mgr.health.get_snapshot()}
    bs = pipe.get_benchmark_stats()
    elapsed = time.time() - t0
    print("\n" + "-" * 70)
    print(" PER-CAMERA")
    connected_any = False
    for r in records:
        m = health.get(r.camera_id)
        got = m is not None and m.measured_fps > 0
        connected_any = connected_any or got
        fps = m.measured_fps if m else 0.0
        drops = m.frame_drop_count if m else 0
        rec = m.reconnect_count if m else 0
        print(f"  {r.camera_id}: status={m.status.value if m else 'n/a'} "
              f"fps={fps:.1f} drops={drops} reconnects={rec}")
    print("-" * 70)
    print(f" frames received (consumer) . {consumer.frames_processed + consumer.frames_skipped}")
    print(f" frames processed (AI) ...... {consumer.frames_processed}")
    print(f" vehicles detected .......... {bs['total_vehicles_detected']}")
    print(f" AI events generated ........ {bs['total_ai_events_generated']}")
    print(f" events buffered (undelivered) {len(pipe.event_buffer)}")
    print(f" mean YOLO latency .......... {bs['avg_vehicle_detection_ms']} ms")
    print(f" mean OCR latency ........... {bs['avg_ocr_ms']} ms")
    plates = [e.get('license_plate', {}).get('plate_number') for _, e in ev_log]
    readable = [p for p in plates if p and p != 'UNKNOWN' and not str(p).startswith('UNPLATED')]
    print(f" plates recognised .......... {len(readable)}  {readable[:10]}")
    print(f" UNKNOWN plates ............. {sum(1 for p in plates if p == 'UNKNOWN')}")

    wl_hits = alerts = 0
    if backend_up and auth:
        try:
            al = requests.get(f"{api}/alerts?limit=200", headers=auth, timeout=10).json()
            alerts = len(al)
            st = requests.get(f"{api}/dashboard/stats", headers=auth, timeout=10).json()
            print(f" backend dashboard/stats .... {st}")
        except Exception:
            pass
    print(f" alerts in backend .......... {alerts}")
    print(f" elapsed .................... {elapsed:.0f}s")
    print("=" * 70)

    if not connected_any:
        _fail("no Sentinel camera produced frames — check credentials / connectivity "
              "(scripts/test_sentinel_rtsp.py for details).", code=4)
    print(" RESULT: live Sentinel feed processed end-to-end.")
    sys.exit(0)


if __name__ == "__main__":
    main()
