"""
PHASE 3 — FrameEnvelope -> FrameInput -> AI pipeline bridge.

  * envelope_to_frame_input(): field-by-field mapping, nothing invented/dropped
  * FrameConsumer / process_queue_once: real StreamManager frame queue feeds the
    AI pipeline
  * a real ingestion.StreamWorker reading a locally generated video file feeds
    the bridge end to end (no Sentinel credentials required)
"""
import os
import queue
import tempfile
import threading
import time
import unittest

import numpy as np

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None

from ai.adapter.frame_interface import FrameInput
from ai.adapter.ingestion_bridge import (
    FrameConsumer,
    envelope_to_frame_input,
    process_queue_once,
)
from ingestion.models import CameraRecord, FrameEnvelope
from ingestion.stream_manager import StreamManager, StreamWorker


class _RecordingPipeline:
    """Stands in for AIPipeline: records the FrameInputs it is handed."""

    def __init__(self):
        self.seen = []
        self.resets = []

    def process_frame(self, frame_input):
        self.seen.append(frame_input)
        return []

    def reset_camera(self, camera_id):
        self.resets.append(camera_id)


def _envelope(camera_id="cam04", seq=1, pts=123.0):
    return FrameEnvelope(
        camera_id=camera_id,
        frame=np.full((72, 128, 3), 100, np.uint8),
        pts_ms=pts,
        seq_num=seq,
    )


class TestEnvelopeMapping(unittest.TestCase):
    def test_all_fields_mapped(self):
        env = _envelope("cam12", seq=7, pts=456.0)
        fi = envelope_to_frame_input(env, camera_name="12 Bhat Circle")
        self.assertIsInstance(fi, FrameInput)
        self.assertEqual(fi.camera_id, "cam12")
        self.assertIs(fi.frame, env.frame)
        self.assertEqual(fi.pts, 456.0)
        self.assertEqual(fi.metadata["seq_num"], 7)
        self.assertEqual(fi.metadata["pts_ms"], 456.0)
        self.assertEqual(fi.metadata["resolution"], "128x72")
        self.assertEqual(fi.metadata["camera_name"], "12 Bhat Circle")
        self.assertEqual(fi.metadata["source"], "ingestion.stream_manager")
        # timestamp is a usable ISO-8601 UTC string
        self.assertRegex(fi.get_event_timestamp(), r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_timestamp_reconstructed_from_received_at(self):
        env = _envelope()
        env.received_at_s = time.monotonic() - 3600.0  # frame read ~1h ago
        fi = envelope_to_frame_input(env)
        got = fi.get_event_timestamp()
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.assertLess(got, now, "reconstructed frame time should be in the past")


class TestQueueConsumer(unittest.TestCase):
    def test_process_queue_once_drains_stream_manager_queue(self):
        mgr = StreamManager()
        pipe = _RecordingPipeline()
        for i in range(1, 6):
            mgr.frame_queue.put(_envelope("cam04", seq=i, pts=float(i * 40)))
        summary = process_queue_once(mgr.frame_queue, pipe, max_frames=10)
        self.assertEqual(summary["frames_processed"], 5)
        self.assertEqual([fi.camera_id for fi in pipe.seen], ["cam04"] * 5)
        self.assertEqual([fi.metadata["seq_num"] for fi in pipe.seen], [1, 2, 3, 4, 5])
        self.assertEqual([fi.pts for fi in pipe.seen], [40.0, 80.0, 120.0, 160.0, 200.0])

    def test_seq_num_rollback_triggers_camera_reset(self):
        q = queue.Queue()
        pipe = _RecordingPipeline()
        for s in (1, 2, 3):
            q.put(_envelope("cam04", seq=s))
        for s in (1, 2):  # reconnect: seq restarts
            q.put(_envelope("cam04", seq=s))
        process_queue_once(q, pipe, max_frames=10)
        self.assertIn("cam04", pipe.resets)

    def test_two_cameras_do_not_cross_reset(self):
        q = queue.Queue()
        pipe = _RecordingPipeline()
        q.put(_envelope("cam04", seq=1))
        q.put(_envelope("cam12", seq=1))
        q.put(_envelope("cam04", seq=2))
        q.put(_envelope("cam12", seq=2))
        process_queue_once(q, pipe, max_frames=10)
        self.assertEqual(pipe.resets, [])

    def test_frame_skip_samples_per_camera(self):
        q = queue.Queue()
        pipe = _RecordingPipeline()
        for i in range(1, 10):
            q.put(_envelope("cam04", seq=i))
        stop = threading.Event()
        c = FrameConsumer(q, pipe, stop_event=stop, poll_timeout_s=0.1, frame_skip=2)
        c.start()
        deadline = time.time() + 5
        while q.qsize() and time.time() < deadline:
            time.sleep(0.05)
        stop.set()
        c.join(timeout=3)
        # frame_skip=2 -> process 1 of every 3 -> frames 1,4,7 of 9
        self.assertEqual(len(pipe.seen), 3)
        self.assertEqual(c.frames_skipped, 6)


class _OneShotWorker(StreamWorker):
    """Real StreamWorker, but a file EOF stops it instead of re-looping the
    clip forever (keeps the test bounded). Local-file sources now loop by
    default for MOCK cameras (see ingestion/stream_manager.py
    StreamWorker._loop_local_source) -- both that hook and the older
    _reconnect() fallback are overridden here so this test's plain local
    clip still terminates cleanly at EOF instead of looping forever."""

    def _reconnect(self) -> bool:
        if getattr(self, "_connected_once", False):
            return False
        self._connected_once = True
        return super()._reconnect()

    def _loop_local_source(self) -> bool:
        return False


@unittest.skipUnless(cv2 is not None, "OpenCV not available")
class TestRealStreamWorkerToBridge(unittest.TestCase):
    """A real ingestion.StreamWorker decoding a locally written video file,
    feeding FrameEnvelopes through the bridge into the AI pipeline. No
    Sentinel credentials."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "clip.avi")
        vw = cv2.VideoWriter(self.path, cv2.VideoWriter_fourcc(*"MJPG"), 10.0, (160, 120))
        self.assertTrue(vw.isOpened(), "cannot open VideoWriter in this environment")
        for i in range(24):
            frame = np.full((120, 160, 3), 30, np.uint8)
            cv2.rectangle(frame, (10 + i * 4, 40), (60 + i * 4, 90), (200, 200, 200), -1)
            vw.write(frame)
        vw.release()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_streamworker_frames_reach_the_ai_pipeline(self):
        mgr = StreamManager(max_queue_size=500)
        cam = CameraRecord(camera_id="cam-local-test", name="local clip", stream_url=self.path)
        worker = _OneShotWorker(cam, mgr.frame_queue, mgr.health)

        worker.start()
        worker.join(timeout=15)
        self.assertFalse(worker.is_alive(), "worker did not terminate at EOF")

        # everything the real worker decoded is now sitting in the queue
        pipe = _RecordingPipeline()
        summary = process_queue_once(mgr.frame_queue, pipe, max_frames=1000, timeout_s=0.5)

        self.assertGreater(summary["frames_processed"], 5, "no frames reached the AI pipeline")
        fi = pipe.seen[0]
        self.assertIsInstance(fi, FrameInput)
        self.assertEqual(fi.camera_id, "cam-local-test")
        self.assertEqual(fi.metadata["resolution"], "160x120")
        self.assertIsInstance(fi.metadata["seq_num"], int)
        # seq_num monotonic within the single connection; PTS non-decreasing
        seqs = [f.metadata["seq_num"] for f in pipe.seen]
        self.assertEqual(seqs, sorted(seqs))
        ptss = [f.pts for f in pipe.seen if f.pts is not None]
        self.assertEqual(ptss, sorted(ptss))


if __name__ == "__main__":
    unittest.main(verbosity=2)
