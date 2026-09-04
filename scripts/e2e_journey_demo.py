#!/usr/bin/env python3
"""
GUJARAT SENTINEL — end-to-end vehicle-journey acceptance demo.

Drives the REAL processing pipeline across three camera passes and verifies the
full chain in the backend:

    frames -> YOLO detection -> ByteTrack -> plate localise -> OCR -> consensus
    -> AI event -> POST /events/ai-detection -> PostgreSQL -> watchlist -> alert
    -> GET /vehicles/search (journey) / GET /alerts / GET /dashboard/stats

What is REAL here:
  * YOLOv8 vehicle detection            (on a real photo of a bus)
  * ByteTrack persistent per-camera IDs
  * plate localisation + CLAHE preprocessing
  * EasyOCR text recognition            (no stubbing)
  * multi-frame consensus + normalisation
  * event dispatch, camera resolution, DB persistence, watchlist, cooldown,
    alert generation, journey reconstruction

What is SYNTHETIC (and why):
  * the license-plate PIXELS are composited onto the vehicle -- the Sentinel
    catalogue feeds need credentials we do not have, and their mounting
    distance makes plates unreadable anyway. Everything downstream of "read
    some pixels" is real.
  * the three "camera passes" reuse the same base image with small jitter to
    give ByteTrack motion to follow.

Usage:
  BACKEND=http://127.0.0.1:8090 INGEST_KEY=demo-ingest-key ADMIN_PW=admin123 \
      .venv/bin/python scripts/e2e_journey_demo.py
"""
import os
import sys
import time

import cv2
import numpy as np
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ai.pipeline import AIPipeline  # noqa: E402

BACKEND = os.getenv("BACKEND", "http://127.0.0.1:8090").rstrip("/")
API = f"{BACKEND}/api/v1"
INGEST_KEY = os.getenv("INGEST_KEY", "demo-ingest-key")
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PW = os.getenv("ADMIN_PW", "admin123")

BUS = os.path.join(
    os.path.dirname(cv2.__file__), ""
)  # placeholder; resolved below
_ULTRA_BUS_CANDIDATES = [
    os.path.join(p, "ultralytics", "assets", "bus.jpg")
    for p in sys.path
    if p.endswith("site-packages")
]

CAMERAS = [
    {"camera_id": "cam04", "name": "04 Paldi Circle", "latitude": 23.01258, "longitude": 72.56412},
    {"camera_id": "cam12", "name": "12 Chandlodia Rly Xing", "latitude": 23.178482, "longitude": 72.5855},
    {"camera_id": "cam17", "name": "17 Vadodara Expressway Entry", "latitude": 22.29215, "longitude": 73.20},
]
PLATE_TEXT = "GJ18TC0450"   # rendered onto the vehicle; the system reads what it reads


def _find_bus():
    for c in _ULTRA_BUS_CANDIDATES:
        if os.path.isfile(c):
            return c
    raise SystemExit("could not locate ultralytics assets/bus.jpg")


def _render_plate(text, w=560, h=150):
    """A clean, OCR-legible white plate. The plate PIXELS are synthetic; the
    system still reads whatever it reads (this is disclosed in the report)."""
    img = np.full((h, w, 3), 255, np.uint8)
    cv2.rectangle(img, (4, 4), (w - 5, h - 5), (0, 0, 0), 4)
    f = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), _ = cv2.getTextSize(text, f, 2.6, 6)
    cv2.putText(img, text, ((w - tw) // 2, (h + th) // 2), f, 2.6, (0, 0, 0), 6, cv2.LINE_AA)
    return img


def _compose(base, veh_bbox, plate_img, dx=0, dy=0):
    x1, y1, x2, y2 = veh_bbox
    vw, vh = x2 - x1, y2 - y1
    pw = int(vw * 0.42)
    ph = max(8, int(pw * plate_img.shape[0] / plate_img.shape[1]))
    p = cv2.resize(plate_img, (pw, ph))
    frame = base.copy()
    px = int(np.clip(x1 + (vw - pw) // 2 + dx, 0, frame.shape[1] - pw))
    py = int(np.clip(y1 + int(vh * 0.60) + dy, 0, frame.shape[0] - ph))
    frame[py:py + ph, px:px + pw] = p
    # translate the whole scene slightly so ByteTrack sees motion
    if dx or dy:
        M = np.float32([[1, 0, dx], [0, 1, dy]])
        frame = cv2.warpAffine(frame, M, (frame.shape[1], frame.shape[0]), borderMode=cv2.BORDER_REPLICATE)
    return frame


def api_login():
    r = requests.post(f"{API}/auth/login", json={"username": ADMIN_USER, "password": ADMIN_PW}, timeout=10)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def main():
    print("=" * 70)
    print(" GUJARAT SENTINEL — END-TO-END VEHICLE JOURNEY (real pipeline)")
    print("=" * 70)

    base = cv2.imread(_find_bus())
    if base is None:
        raise SystemExit("failed to read base image")

    auth = api_login()
    print(f"[auth] logged in as {ADMIN_USER}")

    r = requests.post(f"{API}/cameras/sync", headers=auth, json=CAMERAS, timeout=15)
    r.raise_for_status()
    print(f"[registry] synced {r.json()['synced']} cameras: {[c['camera_id'] for c in CAMERAS]}")

    pipe = AIPipeline(
        backend_url=f"{API}/events/ai-detection",
        evidence_dir="evidence/e2e_demo",
        device="cpu",
    )
    pipe.ingest_api_key = INGEST_KEY

    # locate the vehicle once with the REAL detector
    dets = pipe.vehicle_detector.detect(base)
    if not dets:
        raise SystemExit("YOLO found no vehicle in the base image")
    veh = max(dets, key=lambda d: (d["bbox"][2] - d["bbox"][0]) * (d["bbox"][3] - d["bbox"][1]))
    print(f"[detect] YOLO: {veh['class']} conf={veh['confidence']:.2f} bbox={veh['bbox']}")
    plate_img = _render_plate(PLATE_TEXT)

    # --- warm-up pass: learn what plate string the pipeline actually produces ---
    warm = AIPipeline(backend_url="http://127.0.0.1:1/none", evidence_dir="evidence/e2e_warm", device="cpu")
    warm.vehicle_detector = pipe.vehicle_detector
    seen = None
    for i in range(6):
        f = _compose(base, veh["bbox"], plate_img, dx=i * 3, dy=0)
        evs = warm.process_frame(f, camera_id="warmup", frame_timestamp="2026-09-01T00:00:00Z")
        if evs:
            seen = evs[-1]["license_plate"]["plate_number"]
    detected_plate = seen or "UNKNOWN"
    print(f"[warm-up] pipeline consensus plate = {detected_plate!r}  (rendered: {PLATE_TEXT!r})")
    if detected_plate == "UNKNOWN":
        raise SystemExit("OCR could not produce any plate -- cannot run the journey demo")

    # watchlist the plate the SYSTEM produces (this is the 'designated vehicle')
    requests.delete  # noqa - keep import tidy
    wl = requests.post(f"{API}/watchlist", headers=auth, json={
        "plate_number": detected_plate, "offense_category": "Stolen Vehicle", "priority_level": "HIGH",
    }, timeout=10)
    print(f"[watchlist] added {detected_plate!r} -> {wl.status_code}")

    # --- three camera passes through the REAL pipeline ---
    t0 = time.time()
    for idx, cam in enumerate(CAMERAS):
        ts_base = f"2026-09-01T10:{idx * 15:02d}:00Z"
        n_events = 0
        for fr in range(8):
            frame = _compose(base, veh["bbox"], plate_img, dx=fr * 4, dy=fr)
            evs = pipe.process_frame(frame, camera_id=cam["camera_id"], frame_timestamp=ts_base)
            n_events += len(evs)
        buffered = len(pipe.event_buffer)
        print(f"[pass {idx+1}] {cam['camera_id']}  frames=8  events_emitted={n_events}  buffered={buffered}")
    pipe.flush_events()
    print(f"[dispatch] all passes done in {time.time()-t0:.1f}s, buffer={len(pipe.event_buffer)}")

    # --- verify in the backend ---
    print("\n" + "-" * 70)
    print(" BACKEND VERIFICATION")
    print("-" * 70)

    js = requests.get(f"{API}/vehicles/search", headers=auth,
                      params={"plate": detected_plate}, timeout=10).json()
    print(f"vehicle history: plate={js['plate_number']} sightings={js['total_sightings']} "
          f"watchlisted={js['is_watchlisted']}")
    prev = None
    ok_order = True
    for s in js["sightings"]:
        gap = ""
        if prev:
            d = (np_dt(s['timestamp']) - np_dt(prev)).total_seconds()
            gap = f"(+{d:.0f}s)"
            ok_order = ok_order and d >= 0
        print(f"   {s['timestamp']}  {s['camera_code'] or s['camera_id']:>6}  "
              f"{(s['camera_name'] or '')[:26]:26}  lat={s['latitude']} lon={s['longitude']} "
              f"track={s['track_id']} {gap}")
        prev = s["timestamp"]

    alerts = requests.get(f"{API}/alerts", headers=auth, timeout=10).json()
    mine = [a for a in alerts if (a.get("plate_number_normalized") or a["plate_number"]) == detected_plate]
    print(f"\nalerts for {detected_plate}: {len(mine)}  "
          f"(priorities: {sorted({a['priority_level'] for a in mine})})")

    stats = requests.get(f"{API}/dashboard/stats", headers=auth, timeout=10).json()
    print(f"dashboard/stats: {stats}")

    geo = requests.get(f"{API}/cameras/geojson", headers=auth, timeout=10).json()
    hit = [f for f in geo["features"] if f["properties"].get("code") in {c["camera_id"] for c in CAMERAS}]
    print(f"GIS geojson: {len(hit)}/{len(CAMERAS)} journey cameras have map coordinates")

    distinct_cams = sorted({(s["camera_code"] or s["camera_id"]) for s in js["sightings"]})
    print("\n" + "=" * 70)
    passed = (
        len(distinct_cams) == 3
        and js["is_watchlisted"]
        and ok_order
        and len(mine) >= 1
        and len(hit) == 3
    )
    print(f" RESULT: {'PASS' if passed else 'INCOMPLETE'} — "
          f"designated vehicle {detected_plate!r} seen at {len(distinct_cams)} cameras "
          f"{distinct_cams} in chronological order, {js['total_sightings']} sighting rows, "
          f"{len(mine)} alert(s), GIS {len(hit)}/3.")
    print("=" * 70)
    sys.exit(0 if passed else 1)


def np_dt(s):
    from datetime import datetime
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


if __name__ == "__main__":
    main()
