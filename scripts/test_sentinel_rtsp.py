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


_FOURCC_CODEC_MAP = {
    "h264": "H.264", "avc1": "H.264", "x264": "H.264",
    "hevc": "H.265/HEVC", "h265": "H.265/HEVC", "hvc1": "H.265/HEVC",
    "mjpg": "MJPEG",
}


def _decode_fourcc(raw: float) -> str:
    try:
        v = int(raw)
        chars = "".join(chr((v >> (8 * i)) & 0xFF) for i in range(4)).strip()
        return _FOURCC_CODEC_MAP.get(chars.lower(), chars or "?")
    except Exception:  # noqa: BLE001
        return "?"


def _measured_fps_from_pts(pts_vals: list) -> "float | None":
    """Average-interval FPS from PTS deltas -- the same method
    ingestion/stream_health.py uses, and the ONLY thing treated as
    authoritative here; CAP_PROP_FPS is reported separately, explicitly
    labeled as not authoritative."""
    deltas = [b - a for a, b in zip(pts_vals, pts_vals[1:]) if (b - a) >= 1.0]
    if not deltas:
        return None
    avg_delta_ms = sum(deltas) / len(deltas)
    return round(1000.0 / avg_delta_ms, 2) if avg_delta_ms > 0 else None


def test_camera(
    cam_id: str,
    registry: dict,
    per_read_timeout_s: float = 8.0,
    total_timeout_s: float = 20.0,
) -> dict:
    """One-shot RTSP connectivity probe (open + read a few frames, then
    close) -- NOT the production reconnect path. Bounded to at most
    `total_timeout_s` wall-clock regardless of how many of the 20 read
    attempts complete: a genuinely corrupted/degraded real feed can make a
    single cv2.read() block for OpenCV's own ~30s internal stream-timeout
    default, which with no bound here would let one bad camera stall an
    entire --all batch for many minutes. `per_read_timeout_s` bounds each
    individual read via OpenCV's own timeout properties; `total_timeout_s`
    is a hard backstop bounding the whole probe."""
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
        # This probe never invokes ReconnectSupervisor (that's the
        # production ingestion/stream_manager.py path, exercised
        # separately) -- one connection attempt, so this is always 0 by
        # construction, not a measurement of production reconnect behavior.
        "reconnect_count": 0,
        "error_reason": None,
    }

    os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
    connect_url = apply_rtsp_credentials(raw_url)
    result["auth_applied"] = connect_url != raw_url

    t0 = time.time()
    # CAP_PROP_OPEN_TIMEOUT_MSEC only takes effect if set BEFORE the actual
    # open happens -- cv2.VideoCapture(url, backend) opens synchronously
    # inside the constructor itself, so setting properties on the object
    # afterward is too late and silently has no effect. Construct empty,
    # set both timeouts, THEN open explicitly.
    per_read_ms = per_read_timeout_s * 1000.0
    cap = cv2.VideoCapture()
    cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, per_read_ms)
    cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, per_read_ms)
    cap.open(connect_url, cv2.CAP_FFMPEG)
    result["opened"] = bool(cap.isOpened())
    frames, shapes, pts_vals = 0, set(), []
    codec_detected = None
    deadline = time.time() + total_timeout_s
    if cap.isOpened():
        codec_detected = _decode_fourcc(cap.get(cv2.CAP_PROP_FOURCC))
        for _ in range(20):
            if time.time() > deadline:
                result["error_reason"] = (
                    f"probe timed out after {total_timeout_s:.0f}s "
                    f"({frames} frame(s) read before giving up)"
                )
                break
            ok, fr = cap.read()
            if ok and fr is not None:
                frames += 1
                shapes.add(tuple(fr.shape[:2]))
                pts_vals.append(cap.get(cv2.CAP_PROP_POS_MSEC))
        result["fps_prop_not_authoritative"] = round(cap.get(cv2.CAP_PROP_FPS), 2)
    cap.release()

    result["codec_detected"] = codec_detected
    result["frames_read"] = frames
    result["frame_shapes"] = [f"{w}x{h}" for (h, w) in shapes]
    result["pts_monotonic"] = pts_vals == sorted(pts_vals) if len(pts_vals) > 1 else None
    result["measured_fps_from_pts"] = _measured_fps_from_pts(pts_vals)
    result["elapsed_s"] = round(time.time() - t0, 2)

    if not result["credentials_configured"] and "401" in result["rtsp_describe"]:
        result["status"] = "AUTH_REQUIRED_NO_CREDENTIALS"
    elif result["opened"] and frames > 0:
        result["status"] = "OK"
    elif result["opened"]:
        # The RTSP session OPENED -- i.e. authentication succeeded at the
        # transport level -- but zero frames were decoded in the time
        # budget. This is NOT an auth failure; mislabeling it as one would
        # misreport the real cause. Distinct from AUTH_FAILED below.
        result["status"] = "NO_FRAMES"
        result["error_reason"] = result["error_reason"] or (
            "RTSP session opened (auth succeeded) but no frame was decoded within the time budget"
        )
    elif "401" in result["rtsp_describe"]:
        result["status"] = "AUTH_FAILED"
        result["error_reason"] = result["error_reason"] or (
            "RTSP session did not open even with credentials applied "
            "(anonymous DESCRIBE also returned 401, consistent with an auth requirement)"
        )
    else:
        result["status"] = "NETWORK_FAILED"
        result["error_reason"] = result["error_reason"] or "cv2.VideoCapture failed to open (no 401 seen either)"
    return result


def _print_result(r: dict) -> None:
    print(f"--- {r['camera']} ---")
    for k, v in r.items():
        if k == "camera":
            continue
        print(f"  {k:22} {v}")
    print()


def main():
    ap = argparse.ArgumentParser(description="Sentinel RTSP diagnostic (password never printed)")
    ap.add_argument("--camera", help="single camera id, e.g. cam04")
    ap.add_argument("--cameras", help="comma-separated camera ids")
    ap.add_argument("--all", action="store_true", help="every camera in data/camera_registry.json")
    ap.add_argument(
        "--concurrency", type=int, default=1,
        help="probe this many cameras in parallel (each opens its own independent "
             "cv2.VideoCapture -- safe to parallelize; default 1 = sequential)"
    )
    ap.add_argument("--per-read-timeout", type=float, default=8.0, help="seconds, per cv2.read() (OpenCV property)")
    ap.add_argument("--total-timeout", type=float, default=20.0, help="seconds, hard cap per camera probe")
    ap.add_argument("--json-out", default=None, help="also write all results as JSON to this file")
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

    results = []
    any_ok = False
    used_concurrency = args.concurrency > 1
    if used_concurrency:
        import concurrent.futures
        import math

        # NOT a `with` block on purpose: ThreadPoolExecutor.__exit__ calls
        # shutdown(wait=True), which blocks until every submitted task
        # finishes -- exactly what we're trying to bound. cv2's own
        # CAP_PROP_OPEN_TIMEOUT_MSEC/READ_TIMEOUT_MSEC are set (see
        # test_camera()) but were observed NOT to be reliably honored by
        # this FFmpeg build for every stream, so this batch-level wait is
        # the actual enforced bound, not a redundant belt-and-suspenders one.
        ex = concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency)
        futures = {
            ex.submit(test_camera, cam, registry, args.per_read_timeout, args.total_timeout): cam
            for cam in cams
        }
        batch_timeout = math.ceil(len(cams) / args.concurrency) * (args.total_timeout + 10) + 15
        done, not_done = concurrent.futures.wait(futures.keys(), timeout=batch_timeout)
        result_map = {}
        for fut in done:
            cam = futures[fut]
            try:
                result_map[cam] = fut.result()
            except Exception as exc:  # noqa: BLE001
                result_map[cam] = {"camera": cam, "status": "OTHER",
                                    "error_reason": f"probe raised {type(exc).__name__}: {exc}"}
        for fut in not_done:
            cam = futures[fut]
            result_map[cam] = {
                "camera": cam,
                "status": "OTHER",
                "error_reason": (
                    f"did not return within the {batch_timeout:.0f}s batch budget -- "
                    "this stream's cv2/FFmpeg open() or read() did not honor its own "
                    "configured timeout property; the underlying thread is abandoned, "
                    "not force-killed"
                ),
            }
        for cam in cams:
            r = result_map[cam]
            results.append(r)
            _print_result(r)
            any_ok = any_ok or r.get("status") == "OK"
    else:
        for cam in cams:
            r = test_camera(cam, registry, args.per_read_timeout, args.total_timeout)
            results.append(r)
            _print_result(r)
            any_ok = any_ok or r["status"] == "OK"

    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(results, f, indent=2)
        print(f"[wrote {args.json_out}]\n")

    if not all(env_rtsp_credentials()):
        print("NOTE: Sentinel RTSP authentication credentials are not configured "
              "(set SENTINEL_RTSP_USERNAME / SENTINEL_RTSP_PASSWORD).")
    sys.stdout.flush()
    if used_concurrency:
        # A camera whose probe thread is still stuck inside a blocking
        # FFmpeg call (see "not_done" above) would otherwise make normal
        # process exit hang forever waiting to join it. This is a
        # diagnostic tool, not a long-running service -- os._exit() skips
        # that join; nothing else is left to flush/clean up past the line
        # above.
        os._exit(0 if any_ok else 2)
    sys.exit(0 if any_ok else 2)


if __name__ == "__main__":
    main()
