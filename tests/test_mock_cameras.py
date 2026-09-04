"""
Tests for the LOCAL MOCK Indian traffic camera source (trafficdataset/).

Covers the mock-camera-specific pieces added on top of the existing,
UNMODIFIED ingestion / AI / backend stack:
  - registry generation (scripts/generate_mock_camera_registry.py)
  - local-file real-time pacing + clean EOF looping (ingestion/stream_manager.py)
  - StreamManager -> AI bridge consuming a mock (local file) source, through
    the exact same FrameConsumer real cameras use

Most tests use small synthetic clips (same technique already used by
tests/test_ingestion_bridge.py's TestRealStreamWorkerToBridge) so they run
fast and don't require the real ~1.7GB trafficdataset/ folder to be present.
A couple of tests additionally probe the real trafficdataset/ folder and the
generated registry when present, and are skipped otherwise.

None of this touches data/camera_registry.json, cam04/cam06, or any RTSP
credential -- see TestRealRegistryUntouched.
"""
import json
import os
import queue
import shutil
import sys
import tempfile
import time
import unittest

import numpy as np

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO)

from ingestion.models import CameraRecord  # noqa: E402
from ingestion.stream_manager import StreamManager, StreamWorker, _is_local_source  # noqa: E402

import scripts.generate_mock_camera_registry as genreg  # noqa: E402
from scripts.run_pipeline_service import to_camera_record  # noqa: E402

TRAFFICDATASET_VIDEOS = os.path.join(REPO, "trafficdataset", "Videos", "Videos")
REAL_REGISTRY = os.path.join(REPO, "data", "camera_registry.json")
MOCK_REGISTRY = os.path.join(REPO, "data", "trafficdataset_camera_registry.json")


def _write_clip(path, n_frames=20, fps=10.0, size=(160, 120)):
    """A tiny synthetic clip -- same technique test_ingestion_bridge.py
    already uses. Fast and deterministic; doesn't need trafficdataset/."""
    w, h = size
    vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"MJPG"), fps, (w, h))
    if not vw.isOpened():  # pragma: no cover
        raise RuntimeError("cannot open VideoWriter in this environment")
    for i in range(n_frames):
        frame = np.full((h, w, 3), 30, np.uint8)
        cv2.rectangle(frame, (10 + (i * 3) % 100, 40), (60 + (i * 3) % 100, 90), (200, 200, 200), -1)
        vw.write(frame)
    vw.release()
    return path


@unittest.skipUnless(cv2 is not None, "OpenCV not available")
class TestIsLocalSource(unittest.TestCase):
    """The single gate that keeps every mock-only behavior away from real
    Sentinel (RTSP) / HLS cameras."""

    def test_rtsp_is_not_local(self):
        self.assertFalse(_is_local_source("rtsp://1.2.3.4:8554/stream/cam04"))

    def test_https_hls_is_not_local(self):
        self.assertFalse(_is_local_source("https://cctv.corp8.cloud/cam04/index.m3u8"))

    def test_plain_file_path_is_local(self):
        self.assertTrue(_is_local_source("/x/trafficdataset/Videos/Videos/video1.MOV"))

    def test_empty_or_none_is_not_local(self):
        self.assertFalse(_is_local_source(None))
        self.assertFalse(_is_local_source(""))


@unittest.skipUnless(cv2 is not None, "OpenCV not available")
class TestRegistryGeneration(unittest.TestCase):
    """scripts/generate_mock_camera_registry.py against synthetic clips --
    never touches the real trafficdataset/ or data/camera_registry.json."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.videos_dir = os.path.join(self.tmp, "Videos", "Videos")
        os.makedirs(self.videos_dir)
        for i in (1, 2, 3):
            _write_clip(os.path.join(self.videos_dir, f"video{i}.MOV"), n_frames=15, fps=10.0)
        self.out = os.path.join(self.tmp, "registry.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _generate(self, extra_args):
        argv = sys.argv
        sys.argv = ["generate_mock_camera_registry.py", "--videos-dir", self.videos_dir,
                    "--out", self.out] + extra_args
        try:
            genreg.main()
        finally:
            sys.argv = argv
        with open(self.out) as f:
            return json.load(f)

    def test_discover_videos_sorted_numerically(self):
        found = genreg.discover_videos(self.videos_dir)
        names = [os.path.basename(p) for p in found]
        self.assertEqual(names, ["video1.MOV", "video2.MOV", "video3.MOV"])

    def test_probe_reports_real_metadata(self):
        meta = genreg.probe(os.path.join(self.videos_dir, "video1.MOV"))
        self.assertTrue(meta["ok"])
        self.assertEqual(meta["width"], 160)
        self.assertEqual(meta["height"], 120)
        self.assertAlmostEqual(meta["fps"], 10.0, delta=0.5)

    def test_probe_reports_unreadable_file_honestly(self):
        bad = os.path.join(self.tmp, "not_a_video.MOV")
        with open(bad, "w") as f:
            f.write("not a real video file")
        meta = genreg.probe(bad)
        self.assertFalse(meta["ok"])

    def test_generated_registry_has_required_fields(self):
        registry = self._generate(["--count", "2"])
        self.assertEqual(len(registry), 2)
        e = registry[0]
        for field in ("camera_code", "camera_id", "name", "source_video", "source_type",
                      "latitude", "longitude", "location", "status", "rtsp_url"):
            self.assertIn(field, e, f"missing required field {field}")
        self.assertEqual(e["camera_code"], "MOCK_CAM01")
        self.assertEqual(e["source_type"], "mock")
        self.assertEqual(e["status"], "ONLINE")
        self.assertTrue(os.path.isabs(e["rtsp_url"]))
        self.assertTrue(os.path.isfile(e["rtsp_url"]))

    def test_generated_registry_entries_load_as_camera_records(self):
        """Must Just Work with the existing, UNMODIFIED
        run_pipeline_service.py loader -- no mock-specific loading code."""
        registry = self._generate(["--count", "1"])
        record = to_camera_record(registry[0])
        self.assertEqual(record.camera_id, "MOCK_CAM01")
        self.assertTrue(_is_local_source(record.stream_url))
        self.assertTrue(os.path.isfile(record.stream_url))

    def test_explicit_videos_selection(self):
        registry = self._generate(["--videos", "video2.MOV,video3.MOV"])
        sources = [os.path.basename(e["source_video"]) for e in registry]
        self.assertEqual(sources, ["video2.MOV", "video3.MOV"])

    def test_count_is_configurable_not_hardcoded(self):
        registry = self._generate(["--count", "1"])
        self.assertEqual(len(registry), 1)

    @unittest.skipUnless(
        __import__("importlib").util.find_spec("av") is not None,
        "optional `av` dependency not installed -- browser-preview remux is skipped, not failed",
    )
    def test_browser_preview_remux_is_a_real_playable_mp4(self):
        """The dashboard embeds this file directly in a <video> tag -- it
        must be a genuine H.264-in-MP4 remux of the source clip, not just
        the .MOV file renamed (QuickTime containers generally don't play in
        browsers even though the H.264 codec inside is standard)."""
        registry = self._generate(["--count", "1"])
        preview = registry[0].get("preview_mp4")
        self.assertIsNotNone(preview, "no preview_mp4 written even though `av` is installed")
        self.assertTrue(os.path.isfile(preview))
        cap = cv2.VideoCapture(preview)
        self.assertTrue(cap.isOpened())
        ok, frame = cap.read()
        cap.release()
        self.assertTrue(ok)
        self.assertEqual(frame.shape[:2], (120, 160))  # matches the synthetic source clip

    def test_never_defaults_to_the_real_or_bus_photo_registries(self):
        real = os.path.abspath(REAL_REGISTRY)
        old_mock = os.path.abspath(os.path.join(REPO, "data", "mock_camera_registry.json"))
        default_out = os.path.abspath(genreg.DEFAULT_OUT)
        self.assertNotEqual(default_out, real)
        self.assertNotEqual(default_out, old_mock)


@unittest.skipUnless(cv2 is not None, "OpenCV not available")
class TestLoopingAndPacing(unittest.TestCase):
    """Real StreamWorker (the exact class real Sentinel cameras use) against
    a real, tiny, synthetic local file -- behavior is gated purely on the
    source URL shape (_is_local_source), never on a special camera type."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # 10 frames @ 10fps ~= 1s of video -- short enough to force several
        # loops within a bounded test, long enough to measure pacing.
        self.path = _write_clip(os.path.join(self.tmp, "clip.avi"), n_frames=10, fps=10.0)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run_worker(self, seconds, loop=True, fps_override=None):
        mgr = StreamManager(max_queue_size=1000)
        raw = {"loop": loop}
        if fps_override:
            raw["mock_fps_override"] = fps_override
        cam = CameraRecord(camera_id="MOCK_TEST", name="test clip", stream_url=self.path, raw=raw)
        worker = StreamWorker(cam, mgr.frame_queue, mgr.health)
        worker.start()
        time.sleep(seconds)
        worker.stop()
        worker.join(timeout=10)
        frames = []
        while True:
            try:
                frames.append(mgr.frame_queue.get_nowait())
            except queue.Empty:
                break
        return worker, frames

    def test_local_source_is_detected_on_the_worker(self):
        mgr = StreamManager()
        cam = CameraRecord(camera_id="MOCK_TEST", stream_url=self.path)
        worker = StreamWorker(cam, mgr.frame_queue, mgr.health)
        self.assertTrue(worker._is_local)

    def test_rtsp_worker_is_never_flagged_local(self):
        mgr = StreamManager()
        cam = CameraRecord(camera_id="cam04", stream_url="rtsp://host/stream/cam04")
        worker = StreamWorker(cam, mgr.frame_queue, mgr.health)
        self.assertFalse(worker._is_local)
        self.assertIsNone(worker._source_fps)

    def test_loops_past_a_single_clip_duration(self):
        worker, frames = self._run_worker(seconds=2.5, loop=True)
        self.assertGreaterEqual(worker._loop_count, 1, "clip did not loop at all")
        self.assertGreater(len(frames), 10, "fewer frames than one full clip -- looping isn't feeding more")

    def test_no_loop_never_calls_the_fast_loop_path(self):
        # loop=False means EOF falls through to the ordinary _reconnect()
        # path instead of _loop_local_source() -- loop_count must stay 0.
        worker, _frames = self._run_worker(seconds=1.5, loop=False)
        self.assertEqual(worker._loop_count, 0)

    def test_seq_num_resets_on_loop_like_a_real_reconnect(self):
        """This is what makes FrameConsumer._check_reconnect() reset that
        camera's tracker automatically on a loop boundary -- no new pipeline
        code needed for 'reset video-specific state safely'."""
        worker, frames = self._run_worker(seconds=2.5, loop=True)
        seqs = [f.seq_num for f in frames if f.camera_id == "MOCK_TEST"]
        self.assertGreater(len(seqs), 10)
        self.assertTrue(any(seqs[i] <= seqs[i - 1] for i in range(1, len(seqs))),
                         "seq_num never went non-monotonic -- loop-reset isn't happening")

    def test_pacing_is_roughly_real_time_not_flat_out(self):
        """10 frames @ 10fps ~= 1s/clip. Draining ~25 frames (several loops)
        must take noticeably longer than an unpaced decode of a 10-frame
        MJPG clip (which would finish in a few ms) -- proves pacing is
        actually throttling reads to real time."""
        mgr = StreamManager(max_queue_size=1000)
        cam = CameraRecord(camera_id="MOCK_PACE", stream_url=self.path, raw={"loop": True})
        worker = StreamWorker(cam, mgr.frame_queue, mgr.health)
        t0 = time.monotonic()
        worker.start()
        collected = 0
        deadline = t0 + 8.0
        while collected < 25 and time.monotonic() < deadline:
            try:
                mgr.frame_queue.get(timeout=0.5)
                collected += 1
            except queue.Empty:
                continue
        elapsed = time.monotonic() - t0
        worker.stop()
        worker.join(timeout=5)
        self.assertGreaterEqual(collected, 25, "did not receive enough frames to judge pacing")
        self.assertGreater(elapsed, 1.5,
                            f"frames arrived too fast ({elapsed:.2f}s for 25 frames @10fps) -- pacing isn't active")

    def test_fps_override_changes_pacing_speed(self):
        """--fps overrides the source clip's own fps for playback speed."""
        mgr = StreamManager(max_queue_size=1000)
        cam = CameraRecord(camera_id="MOCK_FAST", stream_url=self.path,
                            raw={"loop": True, "mock_fps_override": 100.0})
        worker = StreamWorker(cam, mgr.frame_queue, mgr.health)
        t0 = time.monotonic()
        worker.start()
        collected = 0
        deadline = t0 + 5.0
        while collected < 25 and time.monotonic() < deadline:
            try:
                mgr.frame_queue.get(timeout=0.5)
                collected += 1
            except queue.Empty:
                continue
        elapsed = time.monotonic() - t0
        worker.stop()
        worker.join(timeout=5)
        self.assertGreaterEqual(collected, 25)
        self.assertLess(elapsed, 1.5, f"fps override did not speed up pacing ({elapsed:.2f}s)")


@unittest.skipUnless(cv2 is not None, "OpenCV not available")
class TestMockStreamManagerToAIBridge(unittest.TestCase):
    """StreamManager.sync_cameras() onboarding a mock camera, frames flowing
    through the exact same FrameConsumer real cameras use -- no mock-specific
    consumption path exists."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = _write_clip(os.path.join(self.tmp, "clip.avi"), n_frames=12, fps=15.0)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_streammanager_onboards_and_frames_reach_the_pipeline(self):
        from ai.adapter.ingestion_bridge import process_queue_once

        mgr = StreamManager(max_queue_size=500)
        cam = CameraRecord(camera_id="MOCK_CAM_TEST", name="Mock bridge test",
                            stream_url=self.path, raw={"loop": False})
        mgr.sync_cameras([cam])
        self.assertIn("MOCK_CAM_TEST", mgr.active_camera_ids())

        class _Pipe:
            def __init__(self):
                self.seen = []

            def process_frame(self, fi):
                self.seen.append(fi)
                return []

            def reset_camera(self, cid):
                pass

        pipe = _Pipe()
        deadline = time.time() + 8
        while len(pipe.seen) < 5 and time.time() < deadline:
            process_queue_once(mgr.frame_queue, pipe, max_frames=50, timeout_s=0.5)
        mgr.stop_all(join_timeout_s=5)

        self.assertGreaterEqual(len(pipe.seen), 5, "not enough frames reached the AI bridge")
        self.assertTrue(all(fi.camera_id == "MOCK_CAM_TEST" for fi in pipe.seen))
        self.assertTrue(all(fi.frame is not None for fi in pipe.seen))


@unittest.skipUnless(
    os.path.isdir(TRAFFICDATASET_VIDEOS),
    "trafficdataset/ not present in this checkout (large local dataset, gitignored)",
)
class TestRealTrafficdataset(unittest.TestCase):
    """Sanity checks against the actual downloaded Anand traffic clips, when
    present. Skipped in environments (e.g. CI) without the ~1.7GB dataset."""

    def test_at_least_one_usable_video(self):
        found = genreg.discover_videos(TRAFFICDATASET_VIDEOS)
        self.assertGreater(len(found), 0)
        meta = genreg.probe(found[0])
        self.assertTrue(meta["ok"])
        self.assertEqual(meta["width"], 1920)
        self.assertEqual(meta["height"], 1080)

    def test_generated_mock_registry_present_and_valid(self):
        if not os.path.exists(MOCK_REGISTRY):
            self.skipTest("data/trafficdataset_camera_registry.json not generated yet "
                           "(run scripts/generate_mock_camera_registry.py)")
        with open(MOCK_REGISTRY) as f:
            registry = json.load(f)
        self.assertGreater(len(registry), 0)
        for e in registry:
            self.assertTrue(str(e["camera_code"]).startswith("MOCK_CAM"))
            self.assertTrue(os.path.isfile(e["rtsp_url"]), f"missing source video for {e['camera_code']}")
            self.assertEqual(e["source_type"], "mock")


class TestRealRegistryUntouched(unittest.TestCase):
    """The real Sentinel catalogue and credentials must never be touched by
    any mock-camera code."""

    def test_real_registry_has_no_mock_entries(self):
        with open(REAL_REGISTRY) as f:
            entries = json.load(f)
        ids = {str(e.get("camera_id") or e.get("id")) for e in entries}
        mock_ids = {i for i in ids if i.upper().startswith("MOCK")}
        self.assertEqual(mock_ids, set(), "real camera_registry.json must never contain MOCK_ entries")
        self.assertIn("cam04", ids)
        self.assertIn("cam06", ids)

    def test_no_credentials_in_mock_camera_scripts(self):
        """Static guard against a literal credential ever being embedded in
        the mock-camera scripts (they never touch RTSP auth at all)."""
        for fname in ("generate_mock_camera_registry.py", "run_mock_cameras.py"):
            src = open(os.path.join(REPO, "scripts", fname)).read()
            for banned in ("SENTINEL_RTSP_PASSWORD=", "rtsp://103", "LR2B"):
                self.assertNotIn(banned, src, f"{fname} must not embed real credentials")


if __name__ == "__main__":
    unittest.main()
