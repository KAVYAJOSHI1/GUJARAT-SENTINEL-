#!/usr/bin/env python3
"""
Generate LOCAL mock "own camera" demo videos + a matching camera registry.

Why this exists: the live Sentinel feeds (cam04/cam06) are wide overhead
junction cameras — plates are genuinely unreadable there, so they can never
show the OCR -> consensus -> watchlist -> alert half of the pipeline, and a
hackathon demo should not depend on venue internet / RTSP credentials at all.
This script builds a small set of local video files with a clearly LEGIBLE
plate on a real vehicle photo (same technique already verified in
scripts/e2e_journey_demo.py) and a matching data/mock_camera_registry.json,
so the existing, unmodified pipeline can run against them exactly like any
other camera (StreamWorker opens a local file path the same way it opens an
RTSP URL -- no new ingestion code needed).

These are clearly-labelled MOCK videos, not a claim of a live feed.

Usage:
    .venv/bin/python scripts/make_mock_demo_videos.py
    .venv/bin/python scripts/make_mock_demo_videos.py --plate GJ18TC0450 --frames 200
"""
import argparse
import glob
import json
import os
import sys

import cv2
import numpy as np

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO)
OUT_DIR = os.path.join(REPO, "demo_assets", "mock_videos")
REGISTRY_PATH = os.path.join(REPO, "data", "mock_camera_registry.json")

# Three "own" demo cameras -- placed at real, plausible Gujarat locations, but
# clearly separate from the Sentinel cam01-cam30 registry (different id space).
MOCK_CAMERAS = [
    {"camera_id": "mockcam01", "name": "Mock Cam 1 - Society Gate", "latitude": 23.0300, "longitude": 72.5800},
    {"camera_id": "mockcam02", "name": "Mock Cam 2 - Ring Road Junction", "latitude": 23.0500, "longitude": 72.6000},
    {"camera_id": "mockcam03", "name": "Mock Cam 3 - Highway Toll", "latitude": 23.0700, "longitude": 72.6200},
]


def _find_bus_photo():
    for p in sys.path + [os.path.join(REPO, ".venv", "lib")]:
        for c in glob.glob(os.path.join(p, "**", "ultralytics", "assets", "bus.jpg"), recursive=True):
            return c
    raise SystemExit("could not locate a base vehicle photo (ultralytics assets/bus.jpg)")


def _render_plate(text, w=560, h=150):
    img = np.full((h, w, 3), 255, np.uint8)
    cv2.rectangle(img, (4, 4), (w - 5, h - 5), (0, 0, 0), 4)
    f = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), _ = cv2.getTextSize(text, f, 2.6, 6)
    cv2.putText(img, text, ((w - tw) // 2, (h + th) // 2), f, 2.6, (0, 0, 0), 6, cv2.LINE_AA)
    return img


def make_video(path, base, plate_img, veh_bbox, n_frames, fps, direction=1):
    h, w = base.shape[:2]
    vw_ = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"MJPG"), fps, (w, h))
    x1, y1, x2, y2 = veh_bbox
    vw, vh = x2 - x1, y2 - y1
    pw = int(vw * 0.42)
    ph = max(8, int(pw * plate_img.shape[0] / plate_img.shape[1]))
    plate_resized = cv2.resize(plate_img, (pw, ph))
    for i in range(n_frames):
        frame = base.copy()
        dx = direction * (i % 60) * 2
        px = int(np.clip(x1 + (vw - pw) // 2 + dx, 0, w - pw))
        py = int(np.clip(y1 + int(vh * 0.60), 0, h - ph))
        frame[py:py + ph, px:px + pw] = plate_resized
        M = np.float32([[1, 0, dx * 0.5], [0, 1, 0]])
        frame = cv2.warpAffine(frame, M, (w, h), borderMode=cv2.BORDER_REPLICATE)
        vw_.write(frame)
    vw_.release()


def main():
    ap = argparse.ArgumentParser(description="Generate local mock demo camera videos + registry")
    ap.add_argument("--plate", default="GJ18TC0450", help="plate text to render (Indian format)")
    ap.add_argument("--frames", type=int, default=200, help="frames per video (~20s @ 10fps)")
    ap.add_argument("--fps", type=float, default=10.0)
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    base = cv2.imread(_find_bus_photo())
    if base is None:
        raise SystemExit("failed to read base vehicle photo")

    # Locate the vehicle once with the real detector so the plate lands on it.
    from ai.detection.vehicle_detector import VehicleDetector  # noqa: E402

    det = VehicleDetector(device="cpu")
    dets = det.detect(base)
    if not dets:
        raise SystemExit("YOLO found no vehicle in the base photo")
    veh = max(dets, key=lambda d: (d["bbox"][2] - d["bbox"][0]) * (d["bbox"][3] - d["bbox"][1]))
    plate_img = _render_plate(args.plate)

    registry = []
    for i, cam in enumerate(MOCK_CAMERAS):
        out_path = os.path.join(OUT_DIR, f"{cam['camera_id']}.avi")
        make_video(out_path, base, plate_img, veh["bbox"], args.frames, args.fps, direction=1 if i % 2 == 0 else -1)
        entry = dict(cam)
        entry["rtsp_url"] = out_path
        entry["codec"] = "MJPG (local mock file)"
        entry["status"] = "ONLINE"
        registry.append(entry)
        print(f"wrote {out_path}  ({args.frames} frames, plate={args.plate})")

    with open(REGISTRY_PATH, "w") as f:
        json.dump(registry, f, indent=2)
    print(f"\nwrote {REGISTRY_PATH}")
    print("\nRun the pipeline against these mock cameras with the EXISTING, unmodified service:")
    print(f"  .venv/bin/python scripts/run_pipeline_service.py "
          f"--registry {REGISTRY_PATH} --cameras mockcam01,mockcam02,mockcam03 "
          f"--backend-url http://localhost:8000/api/v1/events/ai-detection")


if __name__ == "__main__":
    main()
