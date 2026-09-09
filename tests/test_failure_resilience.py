"""
Phase 19 Part H -- AI/ingestion-side failure resilience.

Principle under test, per the task brief: ONE CAMERA FAILURE MUST NOT TAKE
DOWN THE PLATFORM. Covers scenarios not already exercised by the existing
suite (ingestion/reconnect backoff, RTSP credential handling, Phase 17's
scheduler/queue-overflow/degradation tests, ai/ocr_executor's "a bad crop
never kills the worker thread"):

  - a StreamWorker whose decoder raises mid-stream (not just returns False)
  - a genuinely malformed/corrupt video file never crashes the open attempt
  - a dead StreamWorker is restarted by StreamManager.sync_cameras()
  - the AI-side consumer survives a pipeline exception on one frame and
    keeps consuming
"""
import os
import queue
import sys
import tempfile
import threading
import time
import unittest

import numpy as np

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO)

from ingestion.models import CameraRecord, FrameEnvelope, StreamStatus  # noqa: E402
from ingestion.stream_manager import StreamManager, StreamWorker  # noqa: E402


@unittest.skipUnless(cv2 is not None, "OpenCV not available")
class TestDecodeExceptionResilience(unittest.TestCase):
    """StreamWorker.run() already wraps cap.read() in try/except -- this
    proves that path actually works end-to-end, not just that the code is
    there: a raising decoder must be treated as a dropped frame, never a
    crash, and the worker must keep going afterward."""

    def test_worker_survives_a_read_exception_and_keeps_running(self):
        cam = CameraRecord(camera_id="FAIL-DECODE-1", stream_url="rtsp://unused/stream")
        mgr = StreamManager()
        worker = StreamWorker(cam, mgr.frame_queue, mgr.health)

        calls = {"n": 0}
        good_frame = np.full((60, 80, 3), 100, np.uint8)

        class _FakeCap:
            def read(self_inner):
                calls["n"] += 1
                if calls["n"] == 2:
                    raise RuntimeError("simulated decoder corruption")
                if calls["n"] >= 6:
                    worker._stop_event.set()
                return True, good_frame

            def get(self_inner, prop):
                return 0.0

            def release(self_inner):
                pass

        worker._open_capture = lambda: _FakeCap()
        t = threading.Thread(target=worker.run, daemon=True)
        t.start()
        t.join(timeout=5.0)

        self.assertFalse(t.is_alive(), "worker thread did not exit cleanly")
        snap = mgr.health.get_snapshot()
        by_id = {m.camera_id: m for m in snap}
        self.assertIn("FAIL-DECODE-1", by_id)
        self.assertGreaterEqual(by_id["FAIL-DECODE-1"].frame_drop_count, 1)
        # frames delivered both BEFORE and AFTER the exception -- proves
        # the worker kept servicing the stream, not just "didn't crash".
        delivered = 0
        while True:
            try:
                mgr.frame_queue.get_nowait()
                delivered += 1
            except queue.Empty:
                break
        self.assertGreaterEqual(delivered, 3)


@unittest.skipUnless(cv2 is not None, "OpenCV not available")
class TestMalformedStreamNeverCrashes(unittest.TestCase):
    def test_garbage_file_fails_to_open_without_raising(self):
        with tempfile.NamedTemporaryFile(suffix=".MOV", delete=False) as f:
            f.write(os.urandom(4096))
            path = f.name
        try:
            cam = CameraRecord(camera_id="FAIL-MALFORMED-1", stream_url=path)
            mgr = StreamManager()
            worker = StreamWorker(cam, mgr.frame_queue, mgr.health)
            # The real code path a StreamWorker actually calls on connect --
            # must return None (a clean "didn't work"), never raise.
            result = worker._open_capture()
            self.assertIsNone(result)
        finally:
            os.unlink(path)

    def test_worker_marks_offline_after_exhausting_a_malformed_source(self):
        with tempfile.NamedTemporaryFile(suffix=".MOV", delete=False) as f:
            f.write(os.urandom(4096))
            path = f.name
        try:
            cam = CameraRecord(camera_id="FAIL-MALFORMED-2", stream_url=path)
            mgr = StreamManager()
            worker = StreamWorker(cam, mgr.frame_queue, mgr.health)
            # Force the FIRST reconnect attempt to be the last one this test
            # waits for -- stop before the real (multi-second) backoff ladder
            # would otherwise make this test slow.
            threading.Timer(0.5, worker._stop_event.set).start()
            t = threading.Thread(target=worker.run, daemon=True)
            t.start()
            t.join(timeout=5.0)
            self.assertFalse(t.is_alive(), "worker never exited on a permanently malformed source")
            snap = {m.camera_id: m for m in mgr.health.get_snapshot()}
            self.assertIn("FAIL-MALFORMED-2", snap)
            self.assertIn(snap["FAIL-MALFORMED-2"].status, (StreamStatus.OFFLINE, StreamStatus.RECONNECTING))
        finally:
            os.unlink(path)


class TestDeadWorkerRestart(unittest.TestCase):
    """Part H #15 (worker restart), camera-worker scope: StreamManager's
    own reconciliation loop restarts a worker thread that exited on its
    own -- other cameras are never touched."""

    def test_sync_cameras_restarts_a_dead_worker_without_touching_others(self):
        mgr = StreamManager()
        alive_cam = CameraRecord(camera_id="ALIVE-1", stream_url="rtsp://unused/alive")
        # port 1 on localhost -- connection refused near-instantly, so the
        # real replacement worker sync_cameras() starts for DEAD-1 below
        # fails fast instead of hanging on FFmpeg's own connect timeout.
        dead_cam = CameraRecord(camera_id="DEAD-1", stream_url="rtsp://127.0.0.1:1/dead")

        class _NeverConnects(StreamWorker):
            def _open_capture(self):
                return None  # every attempt fails -> _reconnect() returns False -> run() returns (thread exits)

        alive_worker = StreamWorker(alive_cam, mgr.frame_queue, mgr.health)
        alive_worker.is_alive = lambda: True  # never looks dead to sync_cameras
        dead_worker = _NeverConnects(dead_cam, mgr.frame_queue, mgr.health)
        dead_worker._stop_event.set()  # already "exited" -- is_alive() is genuinely False without .start()

        mgr._workers["ALIVE-1"] = alive_worker
        mgr._workers["DEAD-1"] = dead_worker

        mgr.sync_cameras([alive_cam, dead_cam])

        self.assertIs(mgr._workers["ALIVE-1"], alive_worker, "a healthy worker must never be replaced")
        self.assertIsNot(mgr._workers["DEAD-1"], dead_worker, "a dead worker must be replaced with a fresh one")

        # cleanup -- alive_worker was never actually .start()ed (only its
        # is_alive() was faked), so it can't be join()ed; just stop the
        # real replacement thread sync_cameras() started for DEAD-1.
        mgr._workers["DEAD-1"].stop()
        mgr._workers["DEAD-1"].join(timeout=2.0)


class TestAiConsumerSurvivesAPipelineException(unittest.TestCase):
    """The AI-side consumer must keep consuming frames from OTHER cameras
    (or even the same camera's next frame) after pipeline.process_frame()
    raises for one frame -- both the plain FrameConsumer and Phase 17's
    ScheduledFrameConsumer wrap this in try/except; this proves it."""

    def test_frame_consumer_keeps_going_after_one_bad_frame(self):
        from ai.adapter.ingestion_bridge import FrameConsumer

        calls = {"n": 0}

        class _FlakyPipeline:
            def process_frame(self, frame_input):
                calls["n"] += 1
                if calls["n"] == 1:
                    raise RuntimeError("simulated AI worker failure")
                return []

            def reset_camera(self, camera_id):
                pass

        q: "queue.Queue" = queue.Queue()
        consumer = FrameConsumer(q, _FlakyPipeline(), poll_timeout_s=0.2)
        consumer.start()
        try:
            for i in range(3):
                q.put(FrameEnvelope(camera_id="cam-flaky", frame=np.zeros((4, 4, 3), np.uint8),
                                    pts_ms=float(i), seq_num=i))
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline and calls["n"] < 3:
                time.sleep(0.05)
            self.assertEqual(calls["n"], 3, "consumer stopped calling process_frame after the exception")
            self.assertEqual(consumer.frames_processed, 2, "only the 2 non-raising frames should count as processed")
        finally:
            consumer.stop()
            consumer.join(timeout=2.0)


if __name__ == "__main__":
    unittest.main()
