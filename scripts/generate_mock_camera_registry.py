#!/usr/bin/env python3
"""
Generate a MOCK camera registry from the local `trafficdataset/` folder.

Why this exists: the user provided a real, downloaded Anand-Gujarat traffic
video dataset (104 clips, 1920x1080 @ 30fps H.264, see DEVELOPER_README.md
"Mock cameras" section) to demonstrate multi-camera scale without depending
on the real Sentinel RTSP feed. This script does NOT touch the real
Sentinel registry (data/camera_registry.json) or its cam01-cam30 entries --
it only ever reads video files and writes a *separate* registry file.

Each selected video becomes one MOCK_CAM0N entry with a distinct, clearly-
labelled demo location around Anand, Gujarat. The output registry uses the
exact same entry shape scripts/run_pipeline_service.py already reads
(`camera_id`, `name`, `rtsp_url`, `latitude`, `longitude`, `status`, ...) so
the existing, UNMODIFIED pipeline service can run against it directly --
no new registry-loading code, no parallel AI pipeline.

Usage:
    .venv/bin/python scripts/generate_mock_camera_registry.py
    .venv/bin/python scripts/generate_mock_camera_registry.py --count 5
    .venv/bin/python scripts/generate_mock_camera_registry.py --count 1 --videos video7

The number of active mock cameras is configurable (--count, default 3) --
this dataset has 104 usable clips, but demoing 104 fake cameras would be
absurd; a small, honestly-labelled set is what actually helps a demo.
"""
import argparse
import glob
import json
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_VIDEOS_DIR = os.path.join(REPO, "trafficdataset", "Videos", "Videos")
DEFAULT_OUT = os.path.join(REPO, "data", "trafficdataset_camera_registry.json")
PREVIEW_DIR = os.path.join(REPO, "trafficdataset", "_previews")

# Anand, Gujarat city-centre reference point. Each mock camera gets a small,
# deterministic offset from here so markers don't stack exactly on top of
# each other on the GIS map -- these are demo coordinates, not surveyed
# junction locations (see IMPORTANT note in DEVELOPER_README.md).
ANAND_LAT, ANAND_LON = 22.5645, 72.9289
OFFSETS = [
    (0.0000, 0.0000), (0.0035, 0.0020), (-0.0030, 0.0040), (0.0055, -0.0025),
    (-0.0045, -0.0030), (0.0020, 0.0060), (-0.0060, 0.0010), (0.0010, -0.0055),
]


def _natural_key(path: str):
    m = re.search(r"video(\d+)\.MOV$", path, re.IGNORECASE)
    return int(m.group(1)) if m else path


def discover_videos(videos_dir: str) -> list:
    paths = glob.glob(os.path.join(videos_dir, "video*.MOV"))
    paths += glob.glob(os.path.join(videos_dir, "video*.mov"))
    paths = sorted(set(paths), key=_natural_key)
    return paths


def probe(path: str) -> dict:
    """Best-effort video metadata via OpenCV (no ffprobe binary in this env).
    Never raises -- an unreadable file is reported, not silently trusted."""
    try:
        import cv2
    except ImportError:
        return {"ok": False, "error": "opencv not installed"}
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        cap.release()
        return {"ok": False, "error": "could not open"}
    ok, _ = cap.read()
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    if not ok or w <= 0 or h <= 0:
        return {"ok": False, "error": "unreadable / zero-size frame"}
    return {"ok": True, "width": w, "height": h, "fps": round(fps, 2), "frames": n,
             "duration_s": round(n / fps, 1) if fps else None}


def make_browser_preview(camera_code: str, video_path: str) -> str | None:
    """Losslessly remux the source clip's H.264 stream into a standard
    H.264-in-MP4 file (trafficdataset/_previews/<code>.mp4) so the dashboard
    can actually embed it in a <video> tag -- the source .MOV files use a
    QuickTime container browsers generally won't play, even though the
    codec inside (H.264) is perfectly standard. This is a pure repackage
    (av.mux, no re-encode): fast, and the pixels are untouched -- the
    dashboard still shows the genuine source footage, just in a container a
    browser will accept. Returns the preview path, or None if the optional
    `av` dependency isn't installed (playback then falls back to serving
    the raw .MOV, which may or may not play depending on the browser)."""
    try:
        import av
    except ImportError:
        print(f"  (skipping browser-preview remux for {camera_code}: `pip install av` for in-dashboard playback)")
        return None

    os.makedirs(PREVIEW_DIR, exist_ok=True)
    out_path = os.path.join(PREVIEW_DIR, f"{camera_code}.mp4")
    inp = av.open(video_path)
    try:
        vstream = inp.streams.video[0]
        out = av.open(out_path, "w")
        try:
            ostream = out.add_stream_from_template(vstream)
            for packet in inp.demux(vstream):
                if packet.dts is None:
                    continue
                packet.stream = ostream
                out.mux(packet)
        finally:
            out.close()
    finally:
        inp.close()
    return out_path


def build_entry(index: int, video_path: str, meta: dict) -> dict:
    cam_code = f"MOCK_CAM{index:02d}"
    dlat, dlon = OFFSETS[(index - 1) % len(OFFSETS)]
    lat, lon = round(ANAND_LAT + dlat, 6), round(ANAND_LON + dlon, 6)
    location_name = f"Anand Traffic Junction – Mock Camera {index:02d}"
    return {
        # Same keys scripts/run_pipeline_service.py's to_camera_record()
        # already reads for the real registry -- no loader changes needed.
        "camera_id": cam_code,
        "camera_code": cam_code,
        "name": location_name,
        "rtsp_url": os.path.abspath(video_path),
        "source_video": os.path.relpath(video_path, REPO),
        "source_type": "mock",
        "latitude": lat,
        "longitude": lon,
        "location": location_name,
        "location_desc": f"{location_name}, Anand, Gujarat (LOCAL MOCK SOURCE, not a live government feed)",
        "resolved_address": f"{location_name}, Anand, Gujarat (MOCK)",
        "status": "ONLINE",
        "codec": "H.264 (local mock file)",
        "resolution": f"{meta.get('width')}x{meta.get('height')}" if meta.get("ok") else None,
        "source_fps": meta.get("fps") if meta.get("ok") else None,
        "duration_s": meta.get("duration_s") if meta.get("ok") else None,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--videos-dir", default=DEFAULT_VIDEOS_DIR)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--count", type=int, default=3, help="how many MOCK_CAM* entries to create (default 3)")
    ap.add_argument("--videos", help="comma-separated explicit filenames (e.g. video1.MOV,video7.MOV) "
                                      "instead of taking the first --count in order")
    args = ap.parse_args()

    if not os.path.isdir(args.videos_dir):
        raise SystemExit(f"trafficdataset videos dir not found: {args.videos_dir}\n"
                          f"(expected e.g. trafficdataset/Videos/Videos/video1.MOV)")

    available = discover_videos(args.videos_dir)
    if not available:
        raise SystemExit(f"no video*.MOV files found under {args.videos_dir}")

    if args.videos:
        wanted = [v.strip() for v in args.videos.split(",") if v.strip()]
        by_name = {os.path.basename(p): p for p in available}
        missing = [v for v in wanted if v not in by_name]
        if missing:
            raise SystemExit(f"requested video(s) not found: {missing}")
        chosen = [by_name[v] for v in wanted]
    else:
        if args.count < 1:
            raise SystemExit("--count must be >= 1")
        chosen = available[: args.count]

    print(f"trafficdataset: {len(available)} clip(s) available under {args.videos_dir}")
    print(f"selecting {len(chosen)} for mock cameras (of {len(available)} available)\n")

    registry = []
    skipped = []
    for i, path in enumerate(chosen, start=1):
        meta = probe(path)
        if not meta.get("ok"):
            skipped.append((path, meta.get("error")))
            print(f"  SKIP {os.path.basename(path)}: {meta.get('error')}")
            continue
        entry = build_entry(i, path, meta)
        preview = make_browser_preview(entry["camera_code"], path)
        if preview:
            entry["preview_mp4"] = preview
        registry.append(entry)
        print(f"  {entry['camera_code']}  <-  {os.path.basename(path)}  "
              f"({entry['resolution']} @ {entry['source_fps']}fps, {entry['duration_s']}s)  "
              f"@ ({entry['latitude']}, {entry['longitude']})"
              f"{'  [browser preview ready]' if preview else ''}")

    if not registry:
        raise SystemExit("no usable videos -- nothing written")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(registry, f, indent=2)

    print(f"\nwrote {len(registry)} mock camera(s) -> {args.out}")
    if skipped:
        print(f"skipped {len(skipped)} unusable file(s): {[os.path.basename(p) for p, _ in skipped]}")
    ids = ",".join(e["camera_code"] for e in registry)
    print("\nRun these with the existing pipeline service:")
    print(f"  .venv/bin/python scripts/run_mock_cameras.py --cameras {ids}")
    print("\nOr run them together with the real Sentinel cameras in ONE process:")
    print(f"  .venv/bin/python scripts/run_pipeline_service.py "
          f"--registry data/camera_registry.json,{os.path.relpath(args.out, REPO)} "
          f"--cameras cam04,cam06,{ids}")


if __name__ == "__main__":
    sys.exit(main())
