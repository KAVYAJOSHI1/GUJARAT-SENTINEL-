#!/usr/bin/env python3
"""
Sentinel RTSP connectivity diagnostic.

Attempts an authenticated RTSP connection to one (or a few) Sentinel cameras
and reports connection / auth / codec / frame-read status. The password is
NEVER printed.

Credentials come from the environment:
    SENTINEL_RTSP_USERNAME
    SENTINEL_RTSP_PASSWORD

Usage:
    .venv/bin/python scripts/test_sentinel_rtsp.py --camera cam04
    .venv/bin/python scripts/test_sentinel_rtsp.py --cameras cam04,cam06
    SENTINEL_RTSP_BASE=rtsp://host:8554/stream .venv/bin/python scripts/test_sentinel_rtsp.py --all
"""
import argparse
import json
import os
import socket
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import cv2  # noqa: E402

from ingestion.rtsp_auth import (  # noqa: E402
    apply_rtsp_credentials,
    env_rtsp_credentials,
    redact_rtsp_url,
)

REGISTRY = os.path.join(os.path.dirname(__file__), "..", "data", "camera_registry.json")
DEFAULT_BASE = os.getenv("SENTINEL_RTSP_BASE", "rtsp://103.250.160.189:8554/stream")


def _load_registry():
    try:
        with open(REGISTRY) as f:
            return {c["camera_id"]: c for c in json.load(f)}
    except Exception:
        return {}


def _rtsp_describe_probe(url: str, timeout: float = 6.0) -> str:
    """TCP-level RTSP DESCRIBE probe -> first response line (or an error).

    DESCRIBE is what actually triggers the ``401 Unauthorized`` on this server;
    OPTIONS usually answers ``200`` even unauthenticated. No credentials are
    sent here on purpose -- this only tells us whether auth is required.
    """
    from urllib.parse import urlsplit

    p = urlsplit(url)
    host, port = p.hostname, p.port or 554
    base = url.split("@")[-1]
    base = f"{p.scheme}://{host}:{port}{p.path}" if "@" in url else url
    try:
        with socket.create_connection((host, port), timeout=timeout) as s:
            s.settimeout(timeout)
            s.sendall(
                f"DESCRIBE {base} RTSP/1.0\r\nCSeq: 1\r\nAccept: application/sdp\r\n\r\n".encode()
            )
            data = s.recv(400)
        return data.split(b"\r\n")[0].decode("latin1", "replace")
    except Exception as exc:  # noqa: BLE001
        return f"probe error: {exc}"


def test_camera(cam_id: str, registry: dict) -> dict:
    entry = registry.get(cam_id, {})
    raw_url = entry.get("rtsp_url") or f"{DEFAULT_BASE}/{cam_id}"
    codec_hint = entry.get("codec")
    res_hint = entry.get("resolution")

    result = {
        "camera": cam_id,
        "url": redact_rtsp_url(raw_url),
        "codec_hint": codec_hint,
        "resolution_hint": res_hint,
        "rtsp_describe": _rtsp_describe_probe(raw_url),
        "credentials_configured": all(env_rtsp_credentials()),
    }

    os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
    connect_url = apply_rtsp_credentials(raw_url)
    result["auth_applied"] = connect_url != raw_url

    t0 = time.time()
    cap = cv2.VideoCapture(connect_url, cv2.CAP_FFMPEG)
    result["opened"] = bool(cap.isOpened())
    frames, shapes, pts_vals = 0, set(), []
    if cap.isOpened():
        for _ in range(20):
            ok, fr = cap.read()
            if ok and fr is not None:
                frames += 1
                shapes.add(tuple(fr.shape[:2]))
                pts_vals.append(cap.get(cv2.CAP_PROP_POS_MSEC))
        result["fps_prop"] = round(cap.get(cv2.CAP_PROP_FPS), 2)
    cap.release()

    result["frames_read"] = frames
    result["frame_shapes"] = [f"{w}x{h}" for (h, w) in shapes]
    result["pts_monotonic"] = pts_vals == sorted(pts_vals) if len(pts_vals) > 1 else None
    result["elapsed_s"] = round(time.time() - t0, 2)

    if not result["credentials_configured"] and "401" in result["rtsp_describe"]:
        result["status"] = "AUTH_REQUIRED_NO_CREDENTIALS"
    elif result["opened"] and frames > 0:
        result["status"] = "OK"
    elif "401" in result["rtsp_describe"]:
        result["status"] = "AUTH_FAILED"
    else:
        result["status"] = "UNREACHABLE"
    return result


def main():
    ap = argparse.ArgumentParser(description="Sentinel RTSP diagnostic (password never printed)")
    ap.add_argument("--camera", help="single camera id, e.g. cam04")
    ap.add_argument("--cameras", help="comma-separated camera ids")
    ap.add_argument("--all", action="store_true", help="every camera in data/camera_registry.json")
    args = ap.parse_args()

    registry = _load_registry()
    if args.all:
        cams = list(registry) or [f"cam{i:02d}" for i in range(1, 7)]
    elif args.cameras:
        cams = [c.strip() for c in args.cameras.split(",") if c.strip()]
    elif args.camera:
        cams = [args.camera]
    else:
        cams = ["cam04", "cam06"]

    u, p = env_rtsp_credentials()
    print(f"credentials configured: username={'yes' if u else 'NO'}  password={'yes' if p else 'NO'}")
    print(f"rtsp base: {DEFAULT_BASE}\n")

    any_ok = False
    for cam in cams:
        r = test_camera(cam, registry)
        any_ok = any_ok or r["status"] == "OK"
        print(f"--- {cam} ---")
        for k, v in r.items():
            if k == "camera":
                continue
            print(f"  {k:22} {v}")
        print()

    if not all(env_rtsp_credentials()):
        print("NOTE: Sentinel RTSP authentication credentials are not configured "
              "(set SENTINEL_RTSP_USERNAME / SENTINEL_RTSP_PASSWORD).")
    sys.exit(0 if any_ok else 2)


if __name__ == "__main__":
    main()
