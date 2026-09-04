#!/usr/bin/env python3
"""
Start/stop the LOCAL MOCK Indian traffic camera source(s) (trafficdataset/)
through the SAME AIPipeline / StreamManager machinery the real Sentinel
cameras use -- this is a thin convenience entrypoint around
scripts/run_pipeline_service.py's existing PipelineService, not a second
pipeline. Every frame from a mock camera goes through the identical
YOLO -> ByteTrack -> OCR -> backend chain as cam04/cam06.

These are LOCAL MOCK CAMERAS built from a downloaded Anand, Gujarat traffic
video dataset -- they demonstrate multi-camera scale and the full detection
pipeline, they are NOT a live/government feed. See DEVELOPER_README.md
"Mock cameras" for details.

Usage:
    # one-time (or after adding new videos): build the mock registry
    .venv/bin/python scripts/generate_mock_camera_registry.py --count 3

    # run every configured mock camera
    .venv/bin/python scripts/run_mock_cameras.py

    # run specific ones
    .venv/bin/python scripts/run_mock_cameras.py --cameras MOCK_CAM01,MOCK_CAM02

    # run mock cameras TOGETHER WITH real Sentinel cameras, in ONE process
    # (two separate AIPipeline processes have been observed to crash into
    # each other on this machine at shutdown -- one process, more workers,
    # is the supported way to run real + mock simultaneously)
    .venv/bin/python scripts/run_mock_cameras.py --with-real cam04,cam06

    # adjust playback: slow down / speed up pacing, or disable looping
    .venv/bin/python scripts/run_mock_cameras.py --fps 15
    .venv/bin/python scripts/run_mock_cameras.py --no-loop --duration 30
"""
import argparse
import os
import signal
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.run_pipeline_service import PipelineService, load_registry, log  # noqa: E402

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MOCK_REGISTRY = os.path.join(REPO, "data", "trafficdataset_camera_registry.json")
REAL_REGISTRY = os.path.join(REPO, "data", "camera_registry.json")


class _Args:
    """Plain attribute bag matching what PipelineService reads off argparse
    Namespace -- built here instead of reusing run_pipeline_service's parser
    because this script's CLI surface (--with-real, --loop, --fps) is mock-
    specific and shouldn't leak into the real-camera service's own --help."""


def _by_id(entries):
    return {str(e.get("camera_id") or e.get("id")): e for e in entries}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--registry", default=MOCK_REGISTRY,
                    help="mock camera registry (default: data/trafficdataset_camera_registry.json, "
                         "generate it with scripts/generate_mock_camera_registry.py)")
    ap.add_argument("--cameras", help="comma-separated MOCK_CAM ids (default: every camera in the mock registry)")
    ap.add_argument("--with-real", metavar="cam04,cam06",
                    help="also run these REAL Sentinel camera ids, in the SAME process, alongside the mock ones "
                         "(reads --real-registry; requires SENTINEL_RTSP_* credentials in .env as usual)")
    ap.add_argument("--real-registry", default=REAL_REGISTRY)
    ap.add_argument("--loop", dest="loop", action="store_true", default=True,
                    help="loop each mock clip at end-of-file, like a continuous live feed (default: on)")
    ap.add_argument("--no-loop", dest="loop", action="store_false",
                    help="stop each mock camera at end-of-clip instead of looping (useful for bounded test runs)")
    ap.add_argument("--fps", type=float, default=None,
                    help="override real-time playback pacing in frames/sec (default: the clip's own fps, ~30)")
    ap.add_argument("--backend-url", default=os.getenv("SENTINEL_BACKEND_URL",
                                                        "http://localhost:8000/api/v1/events/ai-detection"))
    ap.add_argument("--no-backend", action="store_true", help="run pipeline without POSTing events (dry run)")
    ap.add_argument("--frame-skip", type=int, default=int(os.getenv("FRAME_SKIP", "0")))
    ap.add_argument("--device", default=os.getenv("SENTINEL_AI_DEVICE", "cpu"))
    ap.add_argument("--evidence-dir", default=os.getenv("SENTINEL_EVIDENCE_DIR", "evidence/mock"))
    ap.add_argument("--max-queue", type=int, default=500)
    ap.add_argument("--stats-interval", type=float, default=10.0)
    ap.add_argument("--duration", type=float, default=0.0, help="auto-stop after N seconds (0 = run forever)")
    ap.add_argument("--admin-user", default=os.getenv("ADMIN_USER") or os.getenv("ADMIN_USERNAME", ""))
    ap.add_argument("--admin-password", default=os.getenv("ADMIN_PASSWORD", ""))
    args = ap.parse_args()

    if not os.path.exists(args.registry):
        raise SystemExit(
            f"mock camera registry not found: {args.registry}\n"
            f"Generate it first:  .venv/bin/python scripts/generate_mock_camera_registry.py"
        )

    mock_by_id = _by_id(load_registry(args.registry))
    if args.cameras:
        ids = [c.strip() for c in args.cameras.split(",") if c.strip()]
        missing = [i for i in ids if i not in mock_by_id]
        if missing:
            raise SystemExit(f"mock camera(s) not in {args.registry}: {missing} (known: {sorted(mock_by_id)})")
        chosen_mock = [mock_by_id[i] for i in ids]
    else:
        chosen_mock = list(mock_by_id.values())
    if not chosen_mock:
        raise SystemExit("no mock cameras selected")

    real_entries = []
    if args.with_real:
        real_by_id = _by_id(load_registry(args.real_registry))
        ids = [c.strip() for c in args.with_real.split(",") if c.strip()]
        missing = [i for i in ids if i not in real_by_id]
        if missing:
            raise SystemExit(f"real camera(s) not in {args.real_registry}: {missing}")
        real_entries = [real_by_id[i] for i in ids]

    svc_args = _Args()
    for k in ("backend_url", "no_backend", "frame_skip", "device", "evidence_dir",
              "max_queue", "stats_interval", "duration", "admin_user", "admin_password"):
        setattr(svc_args, k, getattr(args, k))

    svc = PipelineService(real_entries + chosen_mock, svc_args)

    # Thread the mock-only playback knobs (--loop/--no-loop, --fps) into just
    # the MOCK_CAM* CameraRecords' `raw` dict -- StreamWorker only reads them
    # for local-file sources (ingestion/stream_manager.py _is_local_source),
    # so any real cam04/cam06 records running alongside are untouched.
    mock_ids = set(_by_id(chosen_mock))
    for record in svc.records:
        if record.camera_id in mock_ids:
            record.raw = dict(record.raw or {})
            record.raw["loop"] = args.loop
            if args.fps:
                record.raw["mock_fps_override"] = args.fps

    real_ids = sorted(r.camera_id for r in svc.records if r.camera_id not in mock_ids)
    log.info("MOCK cameras (LOCAL, trafficdataset): %s", sorted(mock_ids))
    if real_ids:
        log.info("REAL Sentinel cameras (same process): %s", real_ids)

    def _sig(_signum, _frame):
        log.info("signal received")
        svc.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)
    svc.start()


if __name__ == "__main__":
    main()
