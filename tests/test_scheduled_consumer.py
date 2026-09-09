"""
PHASE 17 -- ai/scheduled_consumer.py: fair-scheduled alternative to
ai.adapter.ingestion_bridge.FrameConsumer for the DEFAULT single-consumer
(SENTINEL_AI_WORKERS=1) path.

Central claim under test: this fixes the FIFO-starvation bug (measured in
SCALABILITY.md Sec 3 -- only ~5/30 cameras ever got a processed frame)
WITHOUT adding a second thread doing pipeline work and WITHOUT changing
per-frame processing cost -- i.e. same throughput, fair order.
"""
import queue
import threading
import time
import unittest

import numpy as np

from ai.modes import ProcessingMode
from ai.sampling import SamplingConfig
from ai.scheduled_consumer import ScheduledFrameConsumer
from ai.scheduler import CameraPriority
from ingestion.models import FrameEnvelope


class _RecordingPipeline:
    """Stands in for AIPipeline -- records which camera_ids it processed,
    in order, and can simulate real per-frame cost via a sleep."""

    def __init__(self, per_frame_cost_s: float = 0.0):
        self.seen_camera_ids = []
        self.per_frame_cost_s = per_frame_cost_s
        self._lock = threading.Lock()

    def process_frame(self, frame_input, mode=None):
        if self.per_frame_cost_s:
            time.sleep(self.per_frame_cost_s)
        with self._lock:
            self.seen_camera_ids.append(frame_input.camera_id)
        return []

    def reset_camera(self, camera_id):
        pass

    def get_metrics(self):
        return {"resource_usage": {"cpu_percent": 10.0}, "event_queue_depth": 0, "event_queue_maxsize": 500}


def _envelope(camera_id, seq=1):
    return FrameEnvelope(camera_id=camera_id, frame=np.zeros((8, 8, 3), np.uint8), pts_ms=float(seq), seq_num=seq)


class TestFairnessUnderFlood(unittest.TestCase):
    """The direct analogue of SCALABILITY.md Sec 3's finding: one camera
    flooding the shared frame_queue must not starve the others."""

    def test_all_cameras_get_served_despite_one_flooding_camera(self):
        q: "queue.Queue" = queue.Queue(maxsize=2000)
        pipeline = _RecordingPipeline(per_frame_cost_s=0.01)
        consumer = ScheduledFrameConsumer(q, pipeline, poll_timeout_s=0.2)
        consumer.start()
        try:
            normal_cams = [f"norm{i}" for i in range(5)]
            # flood the queue with ONE camera's frames, interleaved with a
            # handful of frames from 5 other cameras -- the classic FIFO-
            # starvation setup this module exists to fix.
            for i in range(200):
                q.put(_envelope("flooder", seq=i))
                if i % 10 == 0:
                    for c in normal_cams:
                        q.put(_envelope(c, seq=i))

            deadline = time.monotonic() + 8.0
            while time.monotonic() < deadline and pipeline.seen_camera_ids.count("flooder") < 5:
                time.sleep(0.1)

            seen = set(pipeline.seen_camera_ids)
            for c in normal_cams:
                self.assertIn(c, seen, f"{c} was starved by the flooding camera")
        finally:
            consumer.stop()
            consumer.join(timeout=3.0)


class TestPriorityAndModeWiring(unittest.TestCase):
    def test_critical_camera_configured_with_alert_mode_is_processed(self):
        q: "queue.Queue" = queue.Queue()
        pipeline = _RecordingPipeline()
        consumer = ScheduledFrameConsumer(q, pipeline, poll_timeout_s=0.2)
        consumer.configure_camera("alert-cam", priority=CameraPriority.CRITICAL, mode=ProcessingMode.ALERT)
        consumer.start()
        try:
            q.put(_envelope("alert-cam"))
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline and "alert-cam" not in pipeline.seen_camera_ids:
                time.sleep(0.05)
            self.assertIn("alert-cam", pipeline.seen_camera_ids)
            self.assertEqual(consumer.scheduler.get_priority("alert-cam"), CameraPriority.CRITICAL)
            self.assertEqual(consumer.modes.get_mode("alert-cam"), ProcessingMode.ALERT)
        finally:
            consumer.stop()
            consumer.join(timeout=3.0)

    def test_explicit_priority_survives_router_seeding(self):
        """The router seeds a default priority from the camera's mode on
        first sighting -- it must never clobber an explicit priority set
        via configure_camera() beforehand."""
        q: "queue.Queue" = queue.Queue()
        pipeline = _RecordingPipeline()
        consumer = ScheduledFrameConsumer(q, pipeline, poll_timeout_s=0.2)
        consumer.configure_camera("cam01", priority=CameraPriority.HIGH)  # explicit, before any frame arrives
        consumer.start()
        try:
            for i in range(3):
                q.put(_envelope("cam01", seq=i))
            time.sleep(0.3)
            self.assertEqual(consumer.scheduler.get_priority("cam01"), CameraPriority.HIGH)
        finally:
            consumer.stop()
            consumer.join(timeout=3.0)


class TestAdaptiveSamplingIntegration(unittest.TestCase):
    def test_rate_limited_camera_drops_are_counted_not_silent(self):
        q: "queue.Queue" = queue.Queue()
        pipeline = _RecordingPipeline()
        consumer = ScheduledFrameConsumer(q, pipeline, poll_timeout_s=0.2)
        consumer.configure_camera("slow-cam", sampling=SamplingConfig(target_fps=1.0, min_fps=1.0, max_fps=1.0))
        consumer.start()
        try:
            for i in range(20):
                q.put(_envelope("slow-cam", seq=i))
            time.sleep(0.5)
            self.assertGreater(consumer.frames_skipped, 0)
            snap = consumer.scheduler.snapshot()
            self.assertGreater(
                snap["cameras"].get("slow-cam", {}).get("frames_dropped_total", 0), 0,
            )
        finally:
            consumer.stop()
            consumer.join(timeout=3.0)


class TestMetricsShape(unittest.TestCase):
    def test_get_metrics_shape(self):
        q: "queue.Queue" = queue.Queue()
        pipeline = _RecordingPipeline()
        consumer = ScheduledFrameConsumer(q, pipeline, poll_timeout_s=0.2)
        m = consumer.get_metrics()
        self.assertIn("scheduler", m)
        self.assertIn("load_state", m)
        self.assertEqual(m["load_state"], "HEALTHY")


if __name__ == "__main__":
    unittest.main()
